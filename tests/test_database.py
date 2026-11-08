"""Opt-in integration tests against a disposable database with the migrations installed.
Set THEFAD_TEST_DATABASE_URL only for a synthetic local database. Each test rolls back.
"""
import os
import re

import psycopg
import pytest
from psycopg.rows import dict_row

pytestmark = pytest.mark.skipif(not os.getenv('THEFAD_TEST_DATABASE_URL'), reason='requires disposable PostgreSQL fixture')


@pytest.fixture
def conn():
    with psycopg.connect(os.environ['THEFAD_TEST_DATABASE_URL'], row_factory=dict_row) as connection:
        connection.execute('SET search_path=thefad,public')
        connection.execute("SET TIME ZONE 'Asia/Manila'")
        try:
            yield connection
        finally:
            connection.rollback()


def freeze(conn, when):
    """Change function clocks inside the rolled-back test transaction only."""
    definitions=conn.execute("SELECT p.oid,pg_get_functiondef(p.oid) AS body FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='thefad' AND p.prokind IN ('f','p')").fetchall()
    for row in definitions:
        body=re.sub(r'LOCALTIMESTAMP(?:\(0\))?', "TIMESTAMP '"+when+"'", row['body'], flags=re.I)
        body=re.sub(r'\bCURRENT_DATE\b', "DATE '"+when[:10]+"'", body)
        if body != row['body']: conn.execute(body)


def staff(conn):
    return conn.execute("INSERT INTO users(username,first_name,last_name,user_type,password_hash,email,hired_on,hourly_rate) VALUES('sql_test','Test','Staff','AD',crypt('TestPassword123',gen_salt('bf')),'sql-test@example.test','2026-01-01',100) RETURNING user_id").fetchone()['user_id']


def test_pool_replaces_a_closed_idle_connection(conn, monkeypatch):
    import db
    from app import create_app

    app = create_app(testing=True)
    app.config['DATABASE_URL'] = os.environ['THEFAD_TEST_DATABASE_URL']
    # Restore the module globals after testing the pool used by the application.
    monkeypatch.setattr(db, 'pool', db.pool)
    monkeypatch.setattr(db, 'SCHEMA', db.SCHEMA)
    monkeypatch.setattr(db, 'SHOP_TIMEZONE', db.SHOP_TIMEZONE)
    db.init_db(app)
    try:
        db.pool.wait(timeout=5)
        with db.pool.connection() as pooled:
            backend_pid = pooled.info.backend_pid
        assert conn.execute('SELECT pg_terminate_backend(%s) AS stopped', (backend_pid,)).fetchone()['stopped']
        # This must succeed on its first attempt without executing the routine twice.
        assert isinstance(db.call_function('fn_list_categories'), list)
    finally:
        db.pool.close()


def test_late_clock_in_closes_at_fixed_end_and_locks_access(conn):
    uid=staff(conn)
    freeze(conn,'2026-11-09 10:00:00')
    conn.execute('CALL sp_clock_in(%s,\'09:00\',15,24,NULL)',(uid,))
    row=conn.execute('SELECT * FROM daily_time_record WHERE user_id=%s',(uid,)).fetchone()
    assert row['status']=='Late' and row['scheduled_end'].hour==17
    assert conn.execute('SELECT * FROM fn_staff_access(%s)',(uid,)).fetchone()['allowed']
    freeze(conn,'2026-11-09 17:00:00')
    # Redefine the time-dependent functions from their original migration for the second clock.
    from pathlib import Path
    sql=Path('sql/05_attendance_audit.sql').read_text()
    sql=re.sub(r'LOCALTIMESTAMP(?:\(0\))?', "TIMESTAMP '2026-11-09 17:00:00'", sql, flags=re.I)
    # Replace only the closure routine, preserving the test record.
    match=re.search(r'CREATE OR REPLACE FUNCTION thefad.fn_close_expired_shifts\(\).*?\n\$\$;',sql,re.S)
    conn.execute(match.group())
    conn.execute('SELECT fn_close_expired_shifts()')
    row=conn.execute('SELECT * FROM daily_time_record WHERE user_id=%s',(uid,)).fetchone()
    assert row['time_out'].hour==17 and row['total_hours']==7
    assert not conn.execute('SELECT * FROM fn_staff_access(%s)',(uid,)).fetchone()['allowed']


@pytest.mark.parametrize('when',['2026-11-09 08:59:59','2026-11-09 17:00:00','2026-11-08 10:00:00'])
def test_clock_in_rejects_outside_schedule(conn,when):
    uid=staff(conn); freeze(conn,when)
    with pytest.raises(psycopg.Error,match='scheduled shift'):
        conn.execute('CALL sp_clock_in(%s,\'09:00\',15,24,NULL)',(uid,))


def test_duplicate_clock_in_rejected(conn):
    uid=staff(conn); freeze(conn,'2026-11-09 10:00:00')
    conn.execute('CALL sp_clock_in(%s,\'09:00\',15,24,NULL)',(uid,))
    with pytest.raises(psycopg.Error): conn.execute('CALL sp_clock_in(%s,\'09:00\',15,24,NULL)',(uid,))


def test_pin_lockout_hash_and_audit_redaction(conn):
    uid=staff(conn)
    conn.execute('CALL sp_set_management_pin(%s,%s,%s)',(uid,'TestPassword123','654321'))
    pin=conn.execute('SELECT pin_hash FROM management_pin WHERE user_id=%s',(uid,)).fetchone()['pin_hash']
    assert pin!='654321' and pin.startswith('$2')
    assert conn.execute("SELECT * FROM fn_verify_management_pin('sql_test','654321')").fetchone()['verified']
    for _ in range(5): assert not conn.execute("SELECT * FROM fn_verify_management_pin('sql_test','000000')").fetchone()['verified']
    assert not conn.execute("SELECT * FROM fn_verify_management_pin('sql_test','654321')").fetchone()['verified']
    rows=conn.execute("SELECT before_data,after_data FROM change_audit WHERE entity='users' AND after_data->>'username'='sql_test'").fetchall()
    assert rows and all('password_hash' not in (r['after_data'] or {}) for r in rows)


def test_audit_cannot_be_modified(conn):
    staff(conn)
    with pytest.raises(psycopg.Error,match='cannot be edited'):
        conn.execute("DELETE FROM change_audit WHERE actor='system'")


def test_overtime_extends_only_end_and_closes_with_completed_payroll(conn):
    uid=staff(conn); freeze(conn,'2026-11-09 18:00:00')
    pid=conn.execute("CALL sp_allow_overtime(%s,%s,'2026-11-09','17:00','19:00',15,'Stock count',NULL)",(uid,uid)).fetchone()['p_permit_id']
    conn.execute('CALL sp_overtime_in(%s,NULL)',(uid,))
    conn.execute("CALL sp_update_overtime(%s,'17:00','20:00',15,'Extended stock count')",(pid,))
    row=conn.execute('SELECT * FROM daily_time_record WHERE user_id=%s',(uid,)).fetchone()
    assert row['scheduled_end'].hour==20 and row['time_in'].hour==18
    payroll=conn.execute("SELECT * FROM fn_payroll('2026-11-09','2026-11-09') WHERE user_id=%s",(uid,)).fetchone()
    assert payroll['gross_pay']==0
    conn.execute("UPDATE daily_time_record SET time_out=scheduled_end,total_hours=2 WHERE user_id=%s",(uid,))
    payroll=conn.execute("SELECT * FROM fn_payroll('2026-11-09','2026-11-09') WHERE user_id=%s",(uid,)).fetchone()
    assert payroll['gross_pay']==200 and payroll['overtime_hours']==2


def test_unused_discount_and_refund_report(conn):
    row=conn.execute("CALL sp_create_discount('SQL test',10,'2026-11-01','2026-11-30','NONE',NULL,NULL)").fetchone()
    conn.execute('CALL sp_delete_unused_discount(%s)',(row['p_discount_id'],))
    assert conn.execute('SELECT * FROM discount WHERE discount_id=%s',(row['p_discount_id'],)).fetchone() is None
    conn.execute("SELECT * FROM fn_refund_report('2026-11-01','2026-11-30')").fetchall()


def test_sale_totals_and_cancellation_restore_stock(conn):
    import json
    uid=staff(conn)
    product=conn.execute('SELECT product_id,current_stock FROM product WHERE is_active AND current_stock>3 ORDER BY product_id LIMIT 1').fetchone()
    sale=conn.execute("CALL sp_create_sale(%s,'Delivery','Cash','Test Customer','09000000000','Test address',%s::jsonb,NULL)",(uid,json.dumps([{'product_id':product['product_id'],'quantity':2}]))).fetchone()['p_sale_id']
    totals=conn.execute('SELECT s.total_amount,(SELECT sum(quantity*unit_price_at_sale) FROM sale_item WHERE sale_id=s.sale_id) item_total FROM sales s WHERE sale_id=%s',(sale,)).fetchone()
    assert totals['total_amount']==totals['item_total']
    assert conn.execute('SELECT current_stock FROM product WHERE product_id=%s',(product['product_id'],)).fetchone()['current_stock']==product['current_stock']-2
    conn.execute("CALL sp_update_order_status(%s,%s,'Cancelled',NULL,NULL)",(uid,sale))
    assert conn.execute('SELECT current_stock FROM product WHERE product_id=%s',(product['product_id'],)).fetchone()['current_stock']==product['current_stock']
