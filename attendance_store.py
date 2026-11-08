"""Attendance rules in the application, using existing PostgreSQL tables for persistence.

No attendance stored routine, trigger, or new database object is required. A saved
scheduled_end column is used when present; older schemas keep the regular schedule
unchanged until open regular shifts close.
"""
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

import psycopg
from psycopg import sql
from flask import current_app

import db
from rules import shop_now


class AttendanceError(ValueError):
    """A safe message for an invalid attendance action."""


def _table(name):
    return sql.SQL('{}.{}').format(sql.Identifier(db.SCHEMA), sql.Identifier(name))


def _columns(cur, name):
    cur.execute('SELECT column_name FROM information_schema.columns WHERE table_schema=%s AND table_name=%s',
                (db.SCHEMA, name))
    return {row['column_name'] for row in cur.fetchall()}


def _schedule(cur):
    c = current_app.config
    r = dict(shift_start=c['SHIFT_START'], shift_end=c['SHIFT_END'], grace=c['GRACE_MINUTES'],
             work_days=c['WORK_DAYS'])
    if _columns(cur, 'shift_setting'):
        cur.execute(sql.SQL('SELECT shift_start, shift_end, grace_minutes FROM {} WHERE setting_id=1').format(_table('shift_setting')))
        row = cur.fetchone()
        if row:
            r.update(shift_start=row['shift_start'], shift_end=row['shift_end'], grace=row['grace_minutes'])
    start = datetime.combine(datetime.min.date(), r['shift_start'])
    end = datetime.combine(datetime.min.date(), r['shift_end'])
    if end <= start:
        raise AttendanceError('The shift schedule is invalid. Ask an admin to correct it.')
    r['shift_hours'] = (end-start).total_seconds()/3600
    return r


def _load(cur, user_id, now):
    # Serialize schedule changes, starts, and automatic closure across web workers.
    cur.execute("SELECT pg_advisory_xact_lock(hashtext('thefad.attendance.schedule'))")
    cur.execute(sql.SQL("SELECT user_id, user_type, COALESCE((to_jsonb(u)->>'is_active')::boolean, true) AS active FROM {} u WHERE user_id=%s FOR UPDATE").format(_table('users')), (user_id,))
    user = cur.fetchone()
    if not user:
        return None
    schedule = _schedule(cur)
    columns = _columns(cur, 'daily_time_record')
    if not {'dtr_id', 'user_id', 'time_in', 'time_out', 'total_hours', 'status'} <= columns:
        raise AttendanceError('Attendance data is incomplete. Contact an administrator.')
    cur.execute(sql.SQL("""SELECT dtr_id, user_id, time_in, time_out, total_hours, status,
            COALESCE(to_jsonb(t)->>'shift_type','Regular') AS shift_type,
            NULLIF(to_jsonb(t)->>'permit_id','')::int AS permit_id,
            NULLIF(to_jsonb(t)->>'scheduled_end','')::timestamp AS scheduled_end,
            to_jsonb(t)->>'note' AS note
        FROM {} t WHERE user_id=%s AND (time_out IS NULL OR time_in >= %s)
        ORDER BY time_in DESC, dtr_id DESC FOR UPDATE""").format(_table('daily_time_record')), (user_id, now - timedelta(days=30)))
    rows = cur.fetchall()
    permits = []
    if _columns(cur, 'overtime_permit'):
        cur.execute(sql.SQL('SELECT * FROM {} WHERE user_id=%s AND work_date >= %s ORDER BY work_date').format(_table('overtime_permit')),
                    (user_id, min([now.date()] + [r['time_in'].date() for r in rows if r['time_out'] is None])))
        permits = cur.fetchall()
    by_id = {p['permit_id']: p for p in permits}
    for row in rows:
        if row['time_out'] is not None:
            continue
        end = row['scheduled_end']
        if end is None and row['shift_type'] == 'Overtime':
            permit = by_id.get(row['permit_id'])
            if not permit:
                raise AttendanceError('An open overtime record has no permit. Ask an admin to correct it.')
            end = datetime.combine(permit['work_date'], permit['end_time'])
        if end is None:
            end = datetime.combine(row['time_in'].date(), schedule['shift_end'])
        # Legacy records started after the configured end need a valid zero-hour close.
        if end <= row['time_in']:
            end = row['time_in'] + timedelta(seconds=1)
        row['scheduled_end'] = end
        if now >= end:
            hours = (Decimal(str((end-row['time_in']).total_seconds())) / Decimal(3600)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
            if hours > 24:
                raise AttendanceError('An open shift exceeds 24 hours. Ask an admin to correct it.')
            updates = [sql.SQL('time_out=%s'), sql.SQL('total_hours=%s')]
            values = [end, hours]
            if 'note' in columns:
                updates.append(sql.SQL('note=%s'))
                values.append('; '.join(filter(None, [row['note'], 'Automatically closed at scheduled end']))[:200])
            values.append(row['dtr_id'])
            cur.execute(sql.SQL('UPDATE {} SET {} WHERE dtr_id=%s AND time_out IS NULL').format(
                _table('daily_time_record'), sql.SQL(', ').join(updates)), values)
            row.update(time_out=end, total_hours=hours)
    for row in rows:
        row['overtime_hours'] = (row['total_hours'] or 0) if row['shift_type'] == 'Overtime' else 0
    for permit in permits:
        linked = next((row for row in rows if row['permit_id'] == permit['permit_id']), None)
        permit.update(dtr_id=linked['dtr_id'] if linked else None,
                      time_in=linked['time_in'] if linked else None,
                      time_out=linked['time_out'] if linked else None)
    start = datetime.combine(now.date(), schedule['shift_start'])
    end = datetime.combine(now.date(), schedule['shift_end'])
    work_days = {int(day) for day in schedule['work_days'].split(',') if day.strip()}
    opened = [row for row in rows if row['time_out'] is None]
    regular_today = any(row['shift_type'] == 'Regular' and row['time_in'].date() == now.date() for row in rows)
    current = next((row for row in opened if row['time_in'] <= now < row['scheduled_end']), None)
    return dict(active=user['active'], user_type=user['user_type'], allowed=bool(user['active'] and current),
                can_clock_in=bool(user['active'] and now.isoweekday() in work_days and start <= now < end
                                  and not regular_today and not opened),
                shop_now=now, shift_end=next((r['scheduled_end'] for r in opened if r['shift_type']=='Regular'), end),
                rows=rows[:30], permits=[p for p in permits if p['work_date'] >= now.date()],
                schedule=schedule, columns=columns, open_rows=opened)


def _execute(action):
    try:
        with db._cursor() as cur:
            return action(cur)
    except AttendanceError as exc:
        raise db.DbError(str(exc)) from exc
    except psycopg.Error as exc:
        raise db.DbError(db._message(exc)) from exc
    except Exception as exc:
        if isinstance(exc, db.DbError):
            raise
        raise db.DbError('Cannot reach the database. Try again in a moment.') from exc


def get_access(user_id, now=None):
    return _execute(lambda cur: _load(cur, user_id, now or shop_now()))


def clock_in(user_id, overtime=False, now=None):
    now = now or shop_now()
    def action(cur):
        state = _load(cur, user_id, now)
        if not state or not state['active']:
            raise AttendanceError('Staff account is inactive.')
        cols = state['columns']
        if overtime:
            permit = next((p for p in state['permits'] if p['work_date'] == now.date()), None)
            if not permit or not {'shift_type', 'permit_id'} <= cols:
                raise AttendanceError('No usable overtime permission is available. Ask an admin.')
            start = datetime.combine(permit['work_date'], permit['start_time'])
            end = datetime.combine(permit['work_date'], permit['end_time'])
            if not start <= now < end or permit['dtr_id'] or state['open_rows']:
                raise AttendanceError('Overtime must be unused, within its approved window, and your other shift must be closed.')
            grace = permit['grace_minutes']
        else:
            if not state['can_clock_in']:
                raise AttendanceError('Clock in is available once per workday during the scheduled shift.')
            start = datetime.combine(now.date(), state['schedule']['shift_start'])
            end = state['shift_end']
            grace = state['schedule']['grace']
        names = ['user_id', 'time_in', 'status']
        values = [user_id, now, 'Late' if now > start + timedelta(minutes=grace) else 'Present']
        if 'shift_type' in cols:
            names.append('shift_type'); values.append('Overtime' if overtime else 'Regular')
        if overtime:
            names.append('permit_id'); values.append(permit['permit_id'])
        if 'scheduled_end' in cols:
            names.append('scheduled_end'); values.append(end)
        cur.execute(sql.SQL('INSERT INTO {} ({}) VALUES ({}) RETURNING dtr_id').format(
            _table('daily_time_record'), sql.SQL(', ').join(map(sql.Identifier, names)),
            sql.SQL(', ').join(sql.Placeholder() for _ in values)), values)
        return cur.fetchone()['dtr_id']
    return _execute(action)


def close_expired(now=None):
    now = now or shop_now()
    def users(cur):
        cur.execute(sql.SQL('SELECT DISTINCT user_id FROM {} WHERE time_out IS NULL ORDER BY user_id').format(_table('daily_time_record')))
        return [r['user_id'] for r in cur.fetchall()]
    failures = False
    for user_id in _execute(users):
        try:
            get_access(user_id, now)
        except db.DbError as exc:
            current_app.logger.warning('Could not close attendance for staff %s: %s', user_id, exc)
            failures = True
    if failures:
        raise db.DbError('Some attendance records could not be closed; see the server log.')


def save_schedule(start, end, grace):
    def action(cur):
        cur.execute("SELECT pg_advisory_xact_lock(hashtext('thefad.attendance.schedule'))")
        duration = datetime.combine(datetime.min.date(), end) - datetime.combine(datetime.min.date(), start)
        if not timedelta(hours=1) <= duration <= timedelta(hours=12) or not 0 <= grace <= 120:
            raise AttendanceError('A shift must be 1–12 hours and grace must be 0–120 minutes.')
        if not _columns(cur, 'shift_setting'):
            raise AttendanceError('Schedule storage is not available in this database. Contact an administrator.')
        cols = _columns(cur, 'daily_time_record')
        # Legacy records lack a saved deadline, so changing the schedule would alter their end.
        if 'scheduled_end' not in cols:
            cur.execute(sql.SQL("SELECT 1 FROM {} t WHERE time_out IS NULL AND COALESCE(to_jsonb(t)->>'shift_type','Regular')='Regular' LIMIT 1").format(_table('daily_time_record')))
        else:
            cur.execute(sql.SQL("SELECT 1 FROM {} t WHERE time_out IS NULL AND COALESCE(to_jsonb(t)->>'shift_type','Regular')='Regular' AND scheduled_end IS NULL LIMIT 1").format(_table('daily_time_record')))
        if cur.fetchone():
            raise AttendanceError('Wait until open regular shifts close before changing the schedule.')
        cur.execute(sql.SQL('INSERT INTO {} (setting_id,shift_start,shift_end,grace_minutes) VALUES (1,%s,%s,%s) ON CONFLICT (setting_id) DO UPDATE SET shift_start=EXCLUDED.shift_start,shift_end=EXCLUDED.shift_end,grace_minutes=EXCLUDED.grace_minutes,updated_at=LOCALTIMESTAMP(0)').format(_table('shift_setting')), (start,end,grace))
    return _execute(action)


def save_overtime(admin_id, user_id, work_date, start, end, grace, note, permit_id=None, now=None):
    now = now or shop_now()
    def action(cur):
        state = _load(cur, user_id, now)
        if not state or not state['active']:
            raise AttendanceError('Choose an active staff member.')
        if not _columns(cur, 'overtime_permit') or not {'shift_type', 'permit_id'} <= state['columns']:
            raise AttendanceError('Overtime storage is not available in this database.')
        duration = datetime.combine(work_date, end) - datetime.combine(work_date, start)
        if not timedelta(0) < duration <= timedelta(hours=8):
            raise AttendanceError('Choose an overtime window of up to 8 hours.')
        grace_value = state['schedule']['grace'] if grace is None else grace
        if not 0 <= grace_value <= 120:
            raise AttendanceError('Grace period must be between 0 and 120 minutes.')
        work_days = {int(x) for x in state['schedule']['work_days'].split(',') if x.strip()}
        if (work_date.isoweekday() in work_days and start < state['schedule']['shift_end']
                and end > state['schedule']['shift_start']):
            raise AttendanceError('Overtime cannot overlap the regular shift.')
        if permit_id is None:
            if work_date < now.date():
                raise AttendanceError('Choose today or a later date.')
            cur.execute(sql.SQL('SELECT 1 FROM {} WHERE user_id=%s AND work_date=%s').format(_table('overtime_permit')), (user_id, work_date))
            if cur.fetchone():
                raise AttendanceError('That person already has overtime on that day. Edit it instead.')
            fields = _columns(cur, 'overtime_permit')
            names = ['user_id','work_date','start_time','end_time','grace_minutes','note']
            values = [user_id,work_date,start,end,grace_value,note or None]
            if 'created_by' in fields:
                names.append('created_by'); values.append(admin_id)
            cur.execute(sql.SQL('INSERT INTO {} ({}) VALUES ({}) RETURNING permit_id').format(
                _table('overtime_permit'), sql.SQL(', ').join(map(sql.Identifier, names)),
                sql.SQL(', ').join(sql.Placeholder() for _ in values)), values)
            return cur.fetchone()['permit_id']
        cur.execute(sql.SQL('SELECT * FROM {} WHERE permit_id=%s AND user_id=%s FOR UPDATE').format(_table('overtime_permit')), (permit_id,user_id))
        permit = cur.fetchone()
        if not permit:
            raise AttendanceError('Overtime not found.')
        if permit['work_date'] != work_date:
            raise AttendanceError('The overtime date cannot be changed.')
        cur.execute(sql.SQL("SELECT time_out FROM {} t WHERE NULLIF(to_jsonb(t)->>'permit_id','')::int=%s FOR UPDATE").format(_table('daily_time_record')), (permit_id,))
        linked = cur.fetchall()
        if linked and (any(row['time_out'] is not None for row in linked)
                       or now >= datetime.combine(work_date, permit['end_time'])
                       or start != permit['start_time'] or end <= permit['end_time'] or len(note.strip()) < 3):
            raise AttendanceError('Running overtime can only be extended before it ends, with the same start and a reason.')
        cur.execute(sql.SQL('UPDATE {} SET start_time=%s,end_time=%s,grace_minutes=%s,note=%s WHERE permit_id=%s').format(_table('overtime_permit')),
                    (start,end,grace_value,note or None,permit_id))
        if linked and 'scheduled_end' in state['columns']:
            cur.execute(sql.SQL('UPDATE {} SET scheduled_end=%s WHERE permit_id=%s AND time_out IS NULL').format(_table('daily_time_record')),
                        (datetime.combine(work_date,end),permit_id))
        return permit_id
    return _execute(action)


def cancel_overtime(permit_id, user_id, now=None):
    def action(cur):
        state = _load(cur, user_id, now or shop_now())
        if not state:
            raise AttendanceError('Staff account not found.')
        cur.execute(sql.SQL("SELECT 1 FROM {} t WHERE NULLIF(to_jsonb(t)->>'permit_id','')::int=%s").format(_table('daily_time_record')), (permit_id,))
        if cur.fetchone():
            raise AttendanceError('This overtime has already started, so it cannot be cancelled.')
        cur.execute(sql.SQL('DELETE FROM {} WHERE permit_id=%s AND user_id=%s').format(_table('overtime_permit')), (permit_id,user_id))
        if not cur.rowcount:
            raise AttendanceError('Overtime not found.')
    return _execute(action)
