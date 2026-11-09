/** Clock in/out and overtime for the signed-in user; admins also manage everyone, overtime and the schedule. */
import * as db from '../db.js';
import * as attendanceStore from '../attendance_store.js';
import { flash } from '../flash.js';
import { renderPage } from '../render.js';
import { shiftRules, shopNow } from '../rules.js';
import {
  addHours, combine, hoursBetween, isoDate, shopDate, shopTimestamp, todayIso,
} from '../time.js';
import { ValidationError } from '../utils.js';
import { loginRequired, roleRequired } from './auth.js';

const hhmm = (time) => String(time || '').slice(0, 5);
const parseLocalInput = (text) => {
  const value = String(text || '');
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(value)) throw new ValidationError('Choose a valid date and time.');
  return new Date(`${value.slice(0, 16)}:00+08:00`);
};
const parseTimeInput = (text, label) => {
  const value = String(text || '');
  if (!/^\d{2}:\d{2}(:\d{2})?$/.test(value)) throw new ValidationError(`${label} must be a time.`);
  return value.length === 5 ? `${value}:00` : value;
};

function overtimeState(permit, regularOpen, now) {
  const start = combine(permit.work_date, permit.start_time);
  const end = combine(permit.work_date, permit.end_time);
  const graceUntil = addHours(start, permit.grace_minutes / 60);
  let state;
  if (permit.dtr_id && permit.time_out === null) state = 'open';
  else if (permit.dtr_id) state = 'done';
  else if (now >= end) state = 'over';
  else if (now < start) state = 'early';
  else if (regularOpen) state = 'wait';
  else state = 'ready';
  return { state, start, end, grace_until: graceUntil, late: state === 'ready' && now > graceUntil };
}

async function activeStaff() {
  return (await db.callFunction('fn_list_staff')).filter((member) => member.is_active);
}

async function range(req, back = 6, ahead = 0) {
  const today = shopNow();
  const fallbackStart = new Date(today.getTime() - back * 86400000);
  const fallbackEnd = new Date(today.getTime() + ahead * 86400000);
  let start = req.query.start || '';
  let end = req.query.end || '';
  if (!/^\d{4}-\d{2}-\d{2}$/.test(start) || !/^\d{4}-\d{2}-\d{2}$/.test(end)) {
    if (start || end) flash(req, 'error', 'Enter dates as year-month-day.');
    start = isoDate(fallbackStart);
    end = isoDate(fallbackEnd);
  }
  return [new Date(`${start}T00:00:00+08:00`), new Date(`${end}T00:00:00+08:00`)];
}

function parseShiftForm(body) {
  try {
    const userId = Number.parseInt(String(body.user_id || ''), 10);
    if (!Number.isInteger(userId)) throw new Error();
    return [userId, parseLocalInput(body.time_in), parseLocalInput(body.time_out), String(body.note || '').trim()];
  } catch {
    throw new ValidationError('Choose a staff member and enter both times.');
  }
}

async function saveShift(dtrId, userId, timeIn, timeOut, note) {
  const rules = await shiftRules(null);
  await db.callProcedure('sp_save_shift', dtrId, userId, shopTimestamp(timeIn), shopTimestamp(timeOut),
    note, rules.shift_start, rules.grace, rules.shift_hours, rules.max_hours, null);
}

export default function register(router) {
  router.get('/attendance', 'attendance.index', loginRequired, async (req, res) => {
    const rules = await shiftRules(req);
    const shift = Number(rules.shift_hours);
    const { rows, permits, shop_now: now, shift_end: shiftEnd, can_clock_in: canClockIn } = req.staffAccess;
    const openRow = rows.find((row) => row.shift_type === 'Regular' && row.time_out === null) || null;
    let st = {};
    if (openRow) {
      const worked = hoursBetween(openRow.time_in, now);
      st = { worked, pct: Math.min(100, Math.max(0, Math.round((worked / shift) * 100))), opens_at: openRow.scheduled_end || shiftEnd };
    }
    const todayDone = rows.some((row) => row.shift_type === 'Regular' && isoDate(row.time_in) === isoDate(now));
    const todayPermit = permits.find((permit) => isoDate(permit.work_date) === isoDate(now)) || null;
    const ot = todayPermit ? overtimeState(todayPermit, Boolean(openRow), now) : null;
    const upcoming = permits.filter((permit) => isoDate(permit.work_date) > isoDate(now));
    return renderPage(req, res, 'attendance.html', {
      rows, open_row: openRow, st, shift, today_done: todayDone, permit: todayPermit, ot, upcoming,
      tab: 'mine', can_clock_in: canClockIn, shift_end: shiftEnd,
    });
  });

  router.post('/attendance/clock-in', 'attendance.clock_in', loginRequired, async (req, res) => {
    try {
      await attendanceStore.clockIn(req.session.user_id);
      flash(req, 'success', 'Clocked in.');
    } catch (error) {
      flash(req, 'error', error.message);
    }
    res.redirect('/attendance/');
  });

  router.post('/attendance/clock-out', 'attendance.clock_out', loginRequired, (req, res) => {
    const { rows, shop_now: now } = req.staffAccess;
    const closed = rows.some((row) => row.shift_type === 'Regular' && isoDate(row.time_in) === isoDate(now) && row.time_out);
    if (closed) flash(req, 'success', 'Your shift has closed.');
    else flash(req, 'info', 'Your shift closes automatically at the scheduled end.');
    res.redirect('/attendance/');
  });

  router.post('/attendance/overtime-in', 'attendance.overtime_in', loginRequired, async (req, res) => {
    try {
      await attendanceStore.clockIn(req.session.user_id, true);
      flash(req, 'success', 'Overtime started.');
    } catch (error) {
      flash(req, 'error', error.message);
    }
    res.redirect('/attendance/');
  });

  router.post('/attendance/overtime-out', 'attendance.overtime_out', loginRequired, (req, res) => {
    flash(req, 'info', 'Overtime closes automatically at the approved end.');
    res.redirect('/attendance/');
  });

  // ---------------------------------------------------------------- admin: everyone
  router.get('/attendance/everyone', 'attendance.everyone', roleRequired('AD'), async (req, res) => {
    const rules = await shiftRules(req);
    const [start, end] = await range(req);
    const userId = req.query.user_id ? Number(req.query.user_id) : null;
    let rows = [];
    let staff = [];
    try {
      rows = await db.callFunction('fn_attendance_board', shopDate(start), shopDate(end), userId, rules.work_days);
      staff = await activeStaff();
    } catch (error) {
      flash(req, 'error', error.message);
    }
    const regular = rows.filter((row) => row.shift_type === 'Regular');
    const counts = {};
    for (const status of ['Present', 'Late', 'Absent']) counts[status] = regular.filter((row) => row.status === status).length;
    const hours = regular.reduce((sum, row) => sum + Number(row.total_hours || 0), 0);
    const overtime = rows.reduce((sum, row) => sum + Number(row.overtime_hours || 0), 0);
    const today = shopNow();
    const presets = [
      ['Today', today, today],
      ['Last 7 days', new Date(today.getTime() - 6 * 86400000), today],
      ['This month', combine(isoDate(today).slice(0, 8) + '01', '00:00'), today],
    ];
    return renderPage(req, res, 'attendance_everyone.html', {
      rows, staff, start, end, user_id: userId, counts, hours, overtime, presets, tab: 'everyone',
    });
  });

  router.get('/attendance/shift', 'attendance.new_shift', roleRequired('AD'), async (req, res) => {
    const staff = await activeStaff();
    const day = req.query.date || todayIso();
    const rules = await shiftRules(req);
    const shift = {
      user_id: req.query.user_id ? Number(req.query.user_id) : null,
      note: '',
      time_in: `${day}T${hhmm(rules.shift_start)}`,
      time_out: `${day}T${hhmm(rules.shift_end)}`,
    };
    return renderPage(req, res, 'shift_form.html', { shift, staff, tab: 'everyone' });
  });

  router.post('/attendance/shift', 'attendance.new_shift', roleRequired('AD'), async (req, res) => {
    const staff = await activeStaff();
    try {
      const [userId, timeIn, timeOut, note] = parseShiftForm(req.body);
      await saveShift(null, userId, timeIn, timeOut, note);
      flash(req, 'success', 'Shift added.');
      return res.redirect(`/attendance/everyone?start=${isoDate(timeIn)}&end=${isoDate(timeIn)}`);
    } catch (error) {
      flash(req, 'error', error.message);
      return renderPage(req, res, 'shift_form.html', { shift: req.body, staff, tab: 'everyone' }, 400);
    }
  });

  router.get('/attendance/shift/:dtr_id(\\d+)', 'attendance.edit_shift', roleRequired('AD'), async (req, res) => {
    const dtrId = Number(req.params.dtr_id);
    const staff = await activeStaff();
    const row = await db.callFunctionOne('fn_get_shift', dtrId);
    if (!row) {
      return renderPage(req, res, 'error.html', { code: 404, heading: 'Page not found', message: 'Check the address or use the menu.' }, 404);
    }
    const shift = {
      dtr_id: dtrId,
      user_id: row.user_id,
      note: row.note || '',
      time_in: row.time_in.strftime('%Y-%m-%dT%H:%M'),
      time_out: row.time_out ? row.time_out.strftime('%Y-%m-%dT%H:%M') : '',
    };
    return renderPage(req, res, 'shift_form.html', { shift, staff, tab: 'everyone' });
  });

  router.post('/attendance/shift/:dtr_id(\\d+)', 'attendance.edit_shift', roleRequired('AD'), async (req, res) => {
    const dtrId = Number(req.params.dtr_id);
    const staff = await activeStaff();
    try {
      const [userId, timeIn, timeOut, note] = parseShiftForm(req.body);
      await saveShift(dtrId, userId, timeIn, timeOut, note);
      flash(req, 'success', 'Shift saved.');
      return res.redirect(`/attendance/everyone?start=${isoDate(timeIn)}&end=${isoDate(timeIn)}`);
    } catch (error) {
      flash(req, 'error', error.message);
      return renderPage(req, res, 'shift_form.html', {
        shift: { ...req.body, dtr_id: dtrId }, staff, tab: 'everyone',
      }, 400);
    }
  });

  // ---------------------------------------------------------------- admin: overtime
  router.get('/attendance/overtime', 'attendance.overtime', roleRequired('AD'), async (req, res) => {
    const [start, end] = await range(req, 7, 30);
    let rows = [];
    try {
      rows = await db.callFunction('fn_list_overtime', shopDate(start), shopDate(end));
    } catch (error) {
      flash(req, 'error', error.message);
    }
    return renderPage(req, res, 'overtime.html', { rows, start, end, tab: 'overtime' });
  });

  router.get('/attendance/overtime/new', 'attendance.new_overtime', roleRequired('AD'), async (req, res) => {
    const rules = await shiftRules(req);
    const staff = await activeStaff();
    const day = shopNow();
    const shiftEnd = combine(day, rules.shift_end);
    const permit = {
      work_date: isoDate(day),
      start_time: hhmm(rules.shift_end),
      end_time: addHours(shiftEnd, 2).strftime('%H:%M'),
      grace_minutes: rules.grace,
      note: '',
    };
    return renderPage(req, res, 'overtime_form.html', {
      permit, staff, editing: false, default_grace: rules.grace, tab: 'overtime',
    });
  });

  router.post('/attendance/overtime/new', 'attendance.new_overtime', roleRequired('AD'), async (req, res) => {
    const rules = await shiftRules(req);
    const staff = await activeStaff();
    try {
      const start = parseTimeInput(req.body.start_time, 'Overtime start');
      const end = parseTimeInput(req.body.end_time, 'Overtime end');
      const grace = String(req.body.grace_minutes || '').trim();
      if (grace && !/^\d+$/.test(grace)) throw new ValidationError('Grace must be a whole number.');
      const workDate = parseLocalInput(req.body.work_date);
      await attendanceStore.saveOvertime(req.session.user_id, Number(req.body.user_id), workDate,
        start, end, grace ? Number(grace) : null, String(req.body.note || '').trim());
      flash(req, 'success', 'Overtime allowed.');
      return res.redirect('/attendance/overtime');
    } catch (error) {
      flash(req, 'error', error.message);
      return renderPage(req, res, 'overtime_form.html', {
        permit: req.body, staff, editing: false, default_grace: rules.grace, tab: 'overtime',
      }, 400);
    }
  });

  router.get('/attendance/overtime/:permit_id(\\d+)', 'attendance.edit_overtime', roleRequired('AD'), async (req, res) => {
    const permitId = Number(req.params.permit_id);
    const rules = await shiftRules(req);
    const row = await db.callFunctionOne('fn_get_overtime', permitId);
    if (!row) {
      return renderPage(req, res, 'error.html', { code: 404, heading: 'Page not found', message: 'Check the address or use the menu.' }, 404);
    }
    const permit = {
      ...row,
      start_time: hhmm(row.start_time),
      end_time: hhmm(row.end_time),
      work_date: isoDate(row.work_date),
      note: row.note || '',
    };
    return renderPage(req, res, 'overtime_form.html', {
      permit, staff: [], editing: true, default_grace: rules.grace, tab: 'overtime',
    });
  });

  router.post('/attendance/overtime/:permit_id(\\d+)', 'attendance.edit_overtime', roleRequired('AD'), async (req, res) => {
    const permitId = Number(req.params.permit_id);
    const rules = await shiftRules(req);
    const row = await db.callFunctionOne('fn_get_overtime', permitId);
    if (!row) {
      return renderPage(req, res, 'error.html', { code: 404, heading: 'Page not found', message: 'Check the address or use the menu.' }, 404);
    }
    try {
      const start = parseTimeInput(req.body.start_time, 'Overtime start');
      const end = parseTimeInput(req.body.end_time, 'Overtime end');
      const grace = String(req.body.grace_minutes || '').trim();
      if (grace && !/^\d+$/.test(grace)) throw new ValidationError('Grace must be a whole number.');
      await attendanceStore.saveOvertime(req.session.user_id, row.user_id, row.work_date, start, end,
        grace ? Number(grace) : null, String(req.body.note || '').trim(), permitId);
      flash(req, 'success', 'Overtime saved.');
      return res.redirect('/attendance/overtime');
    } catch (error) {
      flash(req, 'error', error.message);
      return renderPage(req, res, 'overtime_form.html', {
        permit: {
          ...req.body, permit_id: permitId, full_name: row.full_name,
          work_date: isoDate(row.work_date), started: row.started,
        },
        staff: [], editing: true, default_grace: rules.grace, tab: 'overtime',
      }, 400);
    }
  });

  router.post('/attendance/overtime/:permit_id(\\d+)/cancel', 'attendance.cancel_overtime', roleRequired('AD'), async (req, res) => {
    const permitId = Number(req.params.permit_id);
    try {
      const row = await db.callFunctionOne('fn_get_overtime', permitId);
      if (!row) {
        return renderPage(req, res, 'error.html', { code: 404, heading: 'Page not found', message: 'Check the address or use the menu.' }, 404);
      }
      await attendanceStore.cancelOvertime(permitId, row.user_id);
      flash(req, 'success', 'Overtime cancelled.');
    } catch (error) {
      flash(req, 'error', error.message);
    }
    return res.redirect('/attendance/overtime');
  });

  // ---------------------------------------------------------------- admin: shift schedule
  router.get('/attendance/schedule', 'attendance.schedule', roleRequired('AD'), async (req, res) => {
    const rules = await shiftRules(req);
    const s = {
      shift_start: hhmm(rules.shift_start),
      shift_end: hhmm(rules.shift_end),
      grace_minutes: rules.grace,
    };
    return renderPage(req, res, 'schedule.html', { s, tab: 'schedule' });
  });

  router.post('/attendance/schedule', 'attendance.schedule', roleRequired('AD'), async (req, res) => {
    try {
      const start = parseTimeInput(req.body.shift_start, 'Time in');
      const end = parseTimeInput(req.body.shift_end, 'Time out');
      const grace = Number.parseInt(String(req.body.grace_minutes || ''), 10);
      if (!Number.isInteger(grace)) throw new ValidationError('Enter the time in, the time out and the grace period in minutes.');
      await attendanceStore.saveSchedule(start, end, grace);
      flash(req, 'success', 'Schedule saved.');
      return res.redirect('/attendance/schedule');
    } catch (error) {
      flash(req, 'error', error.message);
      return renderPage(req, res, 'schedule.html', { s: req.body, tab: 'schedule' }, 400);
    }
  });
}
