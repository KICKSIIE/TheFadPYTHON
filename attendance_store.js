/**
 * Attendance rules in the application, using existing PostgreSQL tables for persistence.
 *
 * No attendance stored routine, trigger or new database object is required. A saved scheduled_end column
 * is used when present; older schemas keep the regular schedule unchanged until open regular shifts close.
 */
import { config } from './config.js';
import * as db from './db.js';
import {
  addDays, addHours, addMinutes, addSeconds, combine, isoDate, isoweekday, hoursBetween, shopNow, roundHours,
} from './time.js';

export class AttendanceError extends Error {}

const SCHEMA = config.dbSchema;
const table = (name) => `"${SCHEMA}"."${name}"`;

async function columns(client, name) {
  const result = await client.query(
    'SELECT column_name FROM information_schema.columns WHERE table_schema=$1 AND table_name=$2',
    [SCHEMA, name],
  );
  return new Set(result.rows.map((row) => row.column_name));
}

async function schedule(client) {
  const rules = {
    shift_start: config.shiftStart,
    shift_end: config.shiftEnd,
    grace: config.graceMinutes,
    work_days: config.workDays,
  };
  if ((await columns(client, 'shift_setting')).size) {
    const result = await client.query(`SELECT shift_start, shift_end, grace_minutes FROM ${table('shift_setting')} WHERE setting_id=1`);
    if (result.rows.length) {
      rules.shift_start = result.rows[0].shift_start;
      rules.shift_end = result.rows[0].shift_end;
      rules.grace = result.rows[0].grace_minutes;
    }
  }
  const start = combine('2000-01-01', rules.shift_start);
  const end = combine('2000-01-01', rules.shift_end);
  if (end <= start) throw new AttendanceError('The shift schedule is invalid. Ask an admin to correct it.');
  rules.shift_hours = hoursBetween(start, end);
  return rules;
}

async function load(client, userId, now) {
  // Serialize schedule changes, starts and automatic closure across web workers.
  await client.query("SELECT pg_advisory_xact_lock(hashtext('thefad.attendance.schedule'))");
  const userResult = await client.query(
    `SELECT user_id, user_type, COALESCE((to_jsonb(u)->>'is_active')::boolean, true) AS active
       FROM ${table('users')} u WHERE user_id=$1 FOR UPDATE`,
    [userId],
  );
  const user = userResult.rows[0];
  if (!user) return null;

  const rules = await schedule(client);
  const cols = await columns(client, 'daily_time_record');
  if (!['dtr_id', 'user_id', 'time_in', 'time_out', 'total_hours', 'status'].every((name) => cols.has(name))) {
    throw new AttendanceError('Attendance data is incomplete. Contact an administrator.');
  }

  const rowsResult = await client.query(
    `SELECT dtr_id, user_id, time_in, time_out, total_hours, status,
            COALESCE(to_jsonb(t)->>'shift_type','Regular') AS shift_type,
            NULLIF(to_jsonb(t)->>'permit_id','')::int AS permit_id,
            NULLIF(to_jsonb(t)->>'scheduled_end','')::timestamp AS scheduled_end,
            to_jsonb(t)->>'note' AS note
       FROM ${table('daily_time_record')} t
      WHERE user_id=$1 AND (time_out IS NULL OR time_in >= $2)
      ORDER BY time_in DESC, dtr_id DESC FOR UPDATE`,
    [userId, addDays(now, -30)],
  );
  const rows = rowsResult.rows;

  let permits = [];
  if ((await columns(client, 'overtime_permit')).size) {
    const earliest = [now, ...rows.filter((row) => row.time_out === null).map((row) => row.time_in)]
      .reduce((min, value) => (value < min ? value : min));
    const permitResult = await client.query(
      `SELECT * FROM ${table('overtime_permit')} WHERE user_id=$1 AND work_date >= $2 ORDER BY work_date`,
      [userId, isoDate(earliest)],
    );
    permits = permitResult.rows;
  }

  const byId = new Map(permits.map((permit) => [permit.permit_id, permit]));
  for (const row of rows) {
    if (row.time_out !== null) continue;
    let end = row.scheduled_end;
    if (!end && row.shift_type === 'Overtime') {
      const permit = byId.get(row.permit_id);
      if (!permit) throw new AttendanceError('An open overtime record has no permit. Ask an admin to correct it.');
      end = combine(permit.work_date, permit.end_time);
    }
    if (!end) end = combine(row.time_in, rules.shift_end);
    // Legacy records started after the configured end need a valid zero-hour close.
    if (end <= row.time_in) end = addSeconds(row.time_in, 1);
    row.scheduled_end = end;
    if (now >= end) {
      const hours = roundHours(hoursBetween(row.time_in, end));
      if (hours > 24) throw new AttendanceError('An open shift exceeds 24 hours. Ask an admin to correct it.');
      const updates = ['time_out=$1', 'total_hours=$2'];
      const values = [end, hours];
      if (cols.has('note')) {
        updates.push(`note=$${values.length + 1}`);
        values.push([row.note, 'Automatically closed at scheduled end'].filter(Boolean).join('; ').slice(0, 200));
      }
      values.push(row.dtr_id);
      await client.query(
        `UPDATE ${table('daily_time_record')} SET ${updates.join(', ')} WHERE dtr_id=$${values.length} AND time_out IS NULL`,
        values,
      );
      row.time_out = end;
      row.total_hours = hours;
    }
  }

  for (const row of rows) {
    row.overtime_hours = row.shift_type === 'Overtime' ? (row.total_hours || 0) : 0;
  }
  for (const permit of permits) {
    const linked = rows.find((row) => row.permit_id === permit.permit_id) || null;
    permit.dtr_id = linked ? linked.dtr_id : null;
    permit.time_in = linked ? linked.time_in : null;
    permit.time_out = linked ? linked.time_out : null;
  }

  const start = combine(now, rules.shift_start);
  const end = combine(now, rules.shift_end);
  const workDays = new Set(String(rules.work_days).split(',').map((day) => day.trim()).filter(Boolean).map(Number));
  const opened = rows.filter((row) => row.time_out === null);
  const regularToday = rows.some((row) => row.shift_type === 'Regular' && isoDate(row.time_in) === isoDate(now));
  const current = opened.find((row) => row.time_in <= now && now < row.scheduled_end) || null;
  const shiftEnd = opened.find((row) => row.shift_type === 'Regular')?.scheduled_end || end;

  return {
    active: user.active,
    user_type: user.user_type,
    allowed: Boolean(user.active && current),
    can_clock_in: Boolean(user.active && workDays.has(isoweekday(now)) && start <= now && now < end
      && !regularToday && opened.length === 0),
    shop_now: now,
    shift_end: shiftEnd,
    rows: rows.slice(0, 30),
    permits: permits.filter((permit) => isoDate(permit.work_date) >= isoDate(now)),
    schedule: rules,
    columns: cols,
    open_rows: opened,
  };
}

async function execute(action) {
  try {
    return await db.withClient(action);
  } catch (error) {
    if (error instanceof AttendanceError) throw new db.DbError(error.message);
    throw error;
  }
}

export function getAccess(userId, now = null) {
  return execute((client) => load(client, userId, now || shopNow()));
}

export function clockIn(userId, overtime = false, now = null) {
  const moment = now || shopNow();
  return execute(async (client) => {
    const state = await load(client, userId, moment);
    if (!state || !state.active) throw new AttendanceError('Staff account is inactive.');
    const cols = state.columns;
    let start;
    let end;
    let grace;
    let permit = null;

    if (overtime) {
      permit = state.permits.find((entry) => isoDate(entry.work_date) === isoDate(moment)) || null;
      if (!permit || !cols.has('shift_type') || !cols.has('permit_id')) {
        throw new AttendanceError('No usable overtime permission is available. Ask an admin.');
      }
      start = combine(permit.work_date, permit.start_time);
      end = combine(permit.work_date, permit.end_time);
      if (!(start <= moment && moment < end) || permit.dtr_id || state.open_rows.length) {
        throw new AttendanceError('Overtime must be unused, within its approved window, and your other shift must be closed.');
      }
      grace = permit.grace_minutes;
    } else {
      if (!state.can_clock_in) throw new AttendanceError('Clock in is available once per workday during the scheduled shift.');
      start = combine(moment, state.schedule.shift_start);
      end = state.shift_end;
      grace = state.schedule.grace;
    }

    const names = ['user_id', 'time_in', 'status'];
    const values = [userId, moment, moment > addMinutes(start, grace) ? 'Late' : 'Present'];
    if (cols.has('shift_type')) { names.push('shift_type'); values.push(overtime ? 'Overtime' : 'Regular'); }
    if (overtime) { names.push('permit_id'); values.push(permit.permit_id); }
    if (cols.has('scheduled_end')) { names.push('scheduled_end'); values.push(end); }

    const marks = values.map((_, index) => `$${index + 1}`).join(', ');
    const result = await client.query(
      `INSERT INTO ${table('daily_time_record')} (${names.join(', ')}) VALUES (${marks}) RETURNING dtr_id`,
      values,
    );
    return result.rows[0].dtr_id;
  });
}

export async function closeExpired(now = null) {
  const moment = now || shopNow();
  const userIds = await execute(async (client) => {
    const result = await client.query(
      `SELECT DISTINCT user_id FROM ${table('daily_time_record')} WHERE time_out IS NULL ORDER BY user_id`,
    );
    return result.rows.map((row) => row.user_id);
  });
  let failures = false;
  for (const userId of userIds) {
    try {
      await getAccess(userId, moment);
    } catch (error) {
      console.warn(`Could not close attendance for staff ${userId}: ${error.message}`);
      failures = true;
    }
  }
  if (failures) throw new db.DbError('Some attendance records could not be closed; see the server log.');
}

export function saveSchedule(start, end, grace) {
  return execute(async (client) => {
    await client.query("SELECT pg_advisory_xact_lock(hashtext('thefad.attendance.schedule'))");
    const duration = hoursBetween(combine('2000-01-01', start), combine('2000-01-01', end));
    if (!(duration >= 1 && duration <= 12) || !(grace >= 0 && grace <= 120)) {
      throw new AttendanceError('A shift must be 1–12 hours and grace must be 0–120 minutes.');
    }
    if (!(await columns(client, 'shift_setting')).size) {
      throw new AttendanceError('Schedule storage is not available in this database. Contact an administrator.');
    }
    const cols = await columns(client, 'daily_time_record');
    // Legacy records lack a saved deadline, so changing the schedule would alter their end.
    const check = cols.has('scheduled_end')
      ? `SELECT 1 FROM ${table('daily_time_record')} t WHERE time_out IS NULL AND COALESCE(to_jsonb(t)->>'shift_type','Regular')='Regular' AND scheduled_end IS NULL LIMIT 1`
      : `SELECT 1 FROM ${table('daily_time_record')} t WHERE time_out IS NULL AND COALESCE(to_jsonb(t)->>'shift_type','Regular')='Regular' LIMIT 1`;
    if ((await client.query(check)).rows.length) {
      throw new AttendanceError('Wait until open regular shifts close before changing the schedule.');
    }
    await client.query(
      `INSERT INTO ${table('shift_setting')} (setting_id, shift_start, shift_end, grace_minutes)
       VALUES (1, $1, $2, $3)
       ON CONFLICT (setting_id) DO UPDATE SET shift_start=EXCLUDED.shift_start,
         shift_end=EXCLUDED.shift_end, grace_minutes=EXCLUDED.grace_minutes, updated_at=LOCALTIMESTAMP(0)`,
      [start, end, grace],
    );
  });
}

export function saveOvertime(adminId, userId, workDate, start, end, grace, note, permitId = null, now = null) {
  const moment = now || shopNow();
  return execute(async (client) => {
    const state = await load(client, userId, moment);
    if (!state || !state.active) throw new AttendanceError('Choose an active staff member.');
    if (!(await columns(client, 'overtime_permit')).size || !state.columns.has('shift_type') || !state.columns.has('permit_id')) {
      throw new AttendanceError('Overtime storage is not available in this database.');
    }
    const duration = hoursBetween(combine(workDate, start), combine(workDate, end));
    if (!(duration > 0 && duration <= 8)) throw new AttendanceError('Choose an overtime window of up to 8 hours.');
    const graceValue = grace === null || grace === undefined ? state.schedule.grace : grace;
    if (!(graceValue >= 0 && graceValue <= 120)) throw new AttendanceError('Grace period must be between 0 and 120 minutes.');

    const workDays = new Set(String(state.schedule.work_days).split(',').map((x) => x.trim()).filter(Boolean).map(Number));
    const shiftStart = combine(workDate, state.schedule.shift_start);
    const shiftEnd = combine(workDate, state.schedule.shift_end);
    if (workDays.has(isoweekday(workDate)) && combine(workDate, start) < shiftEnd && combine(workDate, end) > shiftStart) {
      throw new AttendanceError('Overtime cannot overlap the regular shift.');
    }

    if (permitId === null || permitId === undefined) {
      if (isoDate(workDate) < isoDate(moment)) throw new AttendanceError('Choose today or a later date.');
      const existing = await client.query(
        `SELECT 1 FROM ${table('overtime_permit')} WHERE user_id=$1 AND work_date=$2`,
        [userId, isoDate(workDate)],
      );
      if (existing.rows.length) throw new AttendanceError('That person already has overtime on that day. Edit it instead.');
      const fields = await columns(client, 'overtime_permit');
      const names = ['user_id', 'work_date', 'start_time', 'end_time', 'grace_minutes', 'note'];
      const values = [userId, isoDate(workDate), start, end, graceValue, note || null];
      if (fields.has('created_by')) { names.push('created_by'); values.push(adminId); }
      const marks = values.map((_, index) => `$${index + 1}`).join(', ');
      const inserted = await client.query(
        `INSERT INTO ${table('overtime_permit')} (${names.join(', ')}) VALUES (${marks}) RETURNING permit_id`,
        values,
      );
      return inserted.rows[0].permit_id;
    }

    const permitResult = await client.query(
      `SELECT * FROM ${table('overtime_permit')} WHERE permit_id=$1 AND user_id=$2 FOR UPDATE`,
      [permitId, userId],
    );
    const permit = permitResult.rows[0];
    if (!permit) throw new AttendanceError('Overtime not found.');
    if (isoDate(permit.work_date) !== isoDate(workDate)) throw new AttendanceError('The overtime date cannot be changed.');

    const linkedResult = await client.query(
      `SELECT time_out FROM ${table('daily_time_record')} t WHERE NULLIF(to_jsonb(t)->>'permit_id','')::int=$1 FOR UPDATE`,
      [permitId],
    );
    const linked = linkedResult.rows;
    if (linked.length && (linked.some((row) => row.time_out !== null)
      || moment >= combine(workDate, permit.end_time)
      || combine(workDate, start).getTime() !== combine(workDate, permit.start_time).getTime()
      || combine(workDate, end) <= combine(workDate, permit.end_time)
      || String(note || '').trim().length < 3)) {
      throw new AttendanceError('Running overtime can only be extended before it ends, with the same start and a reason.');
    }
    await client.query(
      `UPDATE ${table('overtime_permit')} SET start_time=$1, end_time=$2, grace_minutes=$3, note=$4 WHERE permit_id=$5`,
      [start, end, graceValue, note || null, permitId],
    );
    if (linked.length && state.columns.has('scheduled_end')) {
      await client.query(
        `UPDATE ${table('daily_time_record')} SET scheduled_end=$1 WHERE permit_id=$2 AND time_out IS NULL`,
        [combine(workDate, end), permitId],
      );
    }
    return permitId;
  });
}

export function cancelOvertime(permitId, userId, now = null) {
  return execute(async (client) => {
    const state = await load(client, userId, now || shopNow());
    if (!state) throw new AttendanceError('Staff account not found.');
    const used = await client.query(
      `SELECT 1 FROM ${table('daily_time_record')} t WHERE NULLIF(to_jsonb(t)->>'permit_id','')::int=$1`,
      [permitId],
    );
    if (used.rows.length) throw new AttendanceError('This overtime has already started, so it cannot be cancelled.');
    const deleted = await client.query(
      `DELETE FROM ${table('overtime_permit')} WHERE permit_id=$1 AND user_id=$2`,
      [permitId, userId],
    );
    if (!deleted.rowCount) throw new AttendanceError('Overtime not found.');
  });
}
