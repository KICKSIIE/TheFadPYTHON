"""Backend attendance against disposable schemas with no attendance routines/triggers."""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time
from decimal import Decimal
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

import attendance_store
import db
from app import create_app

pytestmark = pytest.mark.skipif(not os.getenv('THEFAD_TEST_DATABASE_URL'), reason='requires disposable PostgreSQL fixture')


@pytest.fixture(params=['minimal', 'legacy', 'snapshot'])
def store(request, monkeypatch):
    schema = 'attendance_test_' + uuid4().hex
    admin = psycopg.connect(os.environ['THEFAD_TEST_DATABASE_URL'], autocommit=True)
    admin.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    prefix = sql.Identifier(schema)
    admin.execute(sql.SQL('CREATE TABLE {}.users (user_id int PRIMARY KEY, user_type varchar, is_active boolean)').format(prefix))
    extra = '' if request.param == 'minimal' else ', shift_type varchar, permit_id int, note varchar(200)'
    if request.param == 'snapshot':
        extra += ', scheduled_end timestamp'
    admin.execute(sql.SQL('CREATE TABLE {}.daily_time_record (dtr_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY, user_id int, time_in timestamp, time_out timestamp, total_hours numeric, status varchar ' + extra + ')').format(prefix))
    admin.execute(sql.SQL("INSERT INTO {}.users VALUES (1,'AD',true),(2,'CA',true)").format(prefix))
    if request.param != 'minimal':
        admin.execute(sql.SQL('CREATE TABLE {}.shift_setting (setting_id int PRIMARY KEY, shift_start time, shift_end time, grace_minutes int, updated_at timestamp)').format(prefix))
        admin.execute(sql.SQL("INSERT INTO {}.shift_setting VALUES (1,'09:00','17:00',15,now())").format(prefix))
        admin.execute(sql.SQL('CREATE TABLE {}.overtime_permit (permit_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,user_id int,work_date date,start_time time,end_time time,grace_minutes int,note varchar)').format(prefix))
    monkeypatch.setattr(db, 'pool', db.pool)
    monkeypatch.setattr(db, 'SCHEMA', db.SCHEMA)
    monkeypatch.setattr(db, 'SHOP_TIMEZONE', db.SHOP_TIMEZONE)
    app = create_app(testing=True)
    app.config.update(DATABASE_URL=os.environ['THEFAD_TEST_DATABASE_URL'], DB_SCHEMA=schema)
    db.init_db(app)
    db.pool.wait(timeout=5)
    try:
        with app.app_context():
            yield request.param, admin, prefix
    finally:
        db.pool.close()
        admin.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(prefix))
        admin.close()


def test_fixed_shift_window_and_clock_out_without_database_routines(store):
    kind, conn, prefix = store
    at = lambda hour, minute=0: datetime(2026, 11, 9, hour, minute)
    assert not attendance_store.get_access(1, at(8,59))['can_clock_in']
    assert attendance_store.get_access(1, at(9))['can_clock_in']
    attendance_store.clock_in(1, now=at(10))
    assert attendance_store.get_access(1, at(10))['allowed']
    with pytest.raises(db.DbError, match='once per workday'):
        attendance_store.clock_in(1, now=at(11))
    assert attendance_store.get_access(1, at(16,59))['allowed']
    assert not attendance_store.get_access(1, at(17))['allowed']
    row = conn.execute(sql.SQL('SELECT time_in,time_out,total_hours,status FROM {}.daily_time_record').format(prefix)).fetchone()
    assert row == (at(10), at(17), Decimal('7.00'), 'Late')
    assert not attendance_store.get_access(1, at(17))['can_clock_in']
    assert not attendance_store.get_access(1, datetime(2026,11,8,10))['can_clock_in']


def test_only_one_concurrent_clock_in(store):
    kind, conn, prefix = store
    def clock():
        from app import create_app
        app = create_app(testing=True)
        with app.app_context():
            try:
                return attendance_store.clock_in(1, now=datetime(2026,11,9,9))
            except db.DbError:
                return None
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: clock(), range(2)))
    assert sum(x is not None for x in results) == 1
    assert conn.execute(sql.SQL('SELECT count(*) FROM {}.daily_time_record').format(prefix)).fetchone()[0] == 1


def test_schedule_changes_preserve_open_shift_end(store):
    kind, conn, prefix = store
    if kind == 'minimal':
        pytest.skip('minimal schema has no schedule table')
    attendance_store.clock_in(1, now=datetime(2026,11,9,9))
    if kind == 'legacy':
        with pytest.raises(db.DbError, match='open regular shifts'):
            attendance_store.save_schedule(time(9),time(18),15)
    else:
        attendance_store.save_schedule(time(9),time(18),15)
    state = attendance_store.get_access(1, datetime(2026,11,9,17))
    assert not state['allowed']
    assert conn.execute(sql.SQL('SELECT time_out FROM {}.daily_time_record').format(prefix)).fetchone()[0] == datetime(2026,11,9,17)


def test_overtime_fixed_end_without_routines(store):
    kind, conn, prefix = store
    if kind == 'minimal':
        pytest.skip('minimal schema has no overtime tables')
    conn.execute(sql.SQL("INSERT INTO {}.overtime_permit (user_id,work_date,start_time,end_time,grace_minutes) VALUES (1,'2026-11-09','17:00','19:00',15)").format(prefix))
    with pytest.raises(db.DbError, match='approved window'):
        attendance_store.clock_in(1, overtime=True, now=datetime(2026,11,9,16,59))
    attendance_store.clock_in(1, overtime=True, now=datetime(2026,11,9,17,30))
    assert attendance_store.get_access(1, datetime(2026,11,9,18))['allowed']
    attendance_store.close_expired(datetime(2026,11,9,19))
    assert not attendance_store.get_access(1, datetime(2026,11,9,19))['allowed']
    row = conn.execute(sql.SQL('SELECT time_out,total_hours,status FROM {}.daily_time_record').format(prefix)).fetchone()
    assert row == (datetime(2026,11,9,19),Decimal('1.50'),'Late')


def test_active_role_is_checked_in_backend(store):
    kind, conn, prefix = store
    attendance_store.clock_in(1, now=datetime(2026,11,9,9))
    conn.execute(sql.SQL("UPDATE {}.users SET user_type='CA' WHERE user_id=1").format(prefix))
    assert attendance_store.get_access(1,datetime(2026,11,9,10))['user_type'] == 'CA'
    conn.execute(sql.SQL('UPDATE {}.users SET is_active=false WHERE user_id=1').format(prefix))
    assert not attendance_store.get_access(1,datetime(2026,11,9,10))['active']


def test_overtime_can_be_extended_before_it_ends_without_database_routines(store):
    kind, conn, prefix = store
    if kind == 'minimal':
        pytest.skip('minimal schema has no overtime tables')
    day = datetime(2026,11,9).date()
    permit = attendance_store.save_overtime(1, 2, day, time(17), time(19), 15, 'Stock', now=datetime(2026,11,9,10))
    with pytest.raises(db.DbError, match='already has overtime'):
        attendance_store.save_overtime(1, 2, day, time(17), time(20), 15, '', now=datetime(2026,11,9,10))
    attendance_store.clock_in(2, overtime=True, now=datetime(2026,11,9,17,30))
    with pytest.raises(db.DbError, match='only be extended'):
        attendance_store.save_overtime(1, 2, day, time(17,30), time(20), 15, 'More stock', permit_id=permit, now=datetime(2026,11,9,18))
    attendance_store.save_overtime(1, 2, day, time(17), time(20), 15, 'More stock', permit_id=permit, now=datetime(2026,11,9,18))
    assert attendance_store.get_access(2, datetime(2026,11,9,19))['allowed']
    assert not attendance_store.get_access(2, datetime(2026,11,9,20))['allowed']
    row = conn.execute(sql.SQL('SELECT time_out,total_hours FROM {}.daily_time_record').format(prefix)).fetchone()
    assert row == (datetime(2026,11,9,20), Decimal('2.50'))


def test_database_error_does_not_allow_access(store):
    _, conn, prefix = store
    conn.execute(sql.SQL('DROP TABLE {}.daily_time_record').format(prefix))
    with pytest.raises(db.DbError):
        attendance_store.get_access(1,datetime(2026,11,9,10))


def test_worker_continues_after_bad_overtime_record(store):
    kind, conn, prefix = store
    if kind == 'minimal':
        pytest.skip('minimal schema has no overtime records')
    conn.execute(sql.SQL("INSERT INTO {}.daily_time_record(user_id,time_in,status,shift_type,permit_id) VALUES (1,'2026-11-09 17:00','Present','Overtime',999),(2,'2026-11-09 09:00','Present','Regular',NULL)").format(prefix))
    with pytest.raises(db.DbError, match='Some attendance records'):
        attendance_store.close_expired(datetime(2026,11,9,20))
    row = conn.execute(sql.SQL('SELECT time_out FROM {}.daily_time_record WHERE user_id=2').format(prefix)).fetchone()
    assert row[0] == datetime(2026,11,9,17)
