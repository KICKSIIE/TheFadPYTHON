/** Management POSTs need a valid admin approval PIN (same rule as the Python app). */
import * as db from './db.js';
import { flash } from './flash.js';
import { renderPage } from './render.js';
import { checkLogin } from './modules/auth.js';

const GUARDED_BLUEPRINTS = new Set(['admin_products', 'admin_staff', 'admin_promos', 'refunds', 'inventory']);
const CLOCK_ENDPOINTS = new Set([
  'attendance.clock_in', 'attendance.clock_out', 'attendance.overtime_in', 'attendance.overtime_out',
]);

export async function approvalGuard(req, res, next) {
  delete req.session.approval_actor;
  if (req.method !== 'POST' || !req.session.user_id) return next();
  const blueprint = req.endpoint ? req.endpoint.split('.')[0] : '';
  const guarded = GUARDED_BLUEPRINTS.has(blueprint)
    || (blueprint === 'attendance' && !CLOCK_ENDPOINTS.has(req.endpoint));
  if (!guarded) return next();

  if (!(await checkLogin(req, res))) return undefined;
  if (blueprint !== 'inventory' && req.session.user_type !== 'AD') {
    return renderPage(req, res, 'error.html', {
      code: 403, heading: 'You do not have access to this page',
      message: 'This page is for admins. Ask an admin if you need it.',
    }, 403);
  }
  const username = req.session.user_type === 'AD'
    ? req.session.username
    : String(req.body.approval_username || '').trim();
  let verified;
  try {
    verified = await db.callFunctionOne('fn_verify_management_pin', username, String(req.body.approval_pin || ''));
  } catch {
    return renderPage(req, res, 'unavailable.html', {}, 503);
  }
  if (!verified || !verified.verified) {
    flash(req, 'error', 'A valid admin approval PIN is required. Set your PIN in Account & security.');
    return renderPage(req, res, 'error.html', {
      code: 403, heading: 'Admin approval required',
      message: 'Return to the form and enter a valid approval PIN. Your change was not saved.',
    }, 403);
  }
  req.session.approval_actor = username;
  return next();
}
