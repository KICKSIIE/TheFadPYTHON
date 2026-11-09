/** Shift schedule (saved by an admin in the database) and stock defaults (config.js). */
import { config } from './config.js';
import * as db from './db.js';
import { shopNow } from './time.js';

export { shopNow };

/** Regular shift time in / out / grace, from the database; config values until one is saved. */
export async function shiftRules(req) {
  if (req && req._shiftRules) return req._shiftRules;
  const rules = {
    shift_start: config.shiftStart,
    shift_end: config.shiftEnd,
    grace: config.graceMinutes,
    shift_hours: config.shiftHours,
    max_hours: config.maxShiftHours,
    work_days: config.workDays,
  };
  const access = req && req.staffAccess;
  if (access && access.schedule) {
    Object.assign(rules, access.schedule);
    if (req) req._shiftRules = rules;
    return rules;
  }
  try {
    const row = await db.callFunctionOne('fn_get_shift_setting');
    if (row) {
      rules.shift_start = row.shift_start;
      rules.shift_end = row.shift_end;
      rules.grace = row.grace_minutes;
      rules.shift_hours = row.shift_hours;
    }
  } catch { /* keep the configured defaults */ }
  if (req) req._shiftRules = rules;
  return rules;
}

export function lowStockDefault() {
  return config.lowStockDefault;
}
