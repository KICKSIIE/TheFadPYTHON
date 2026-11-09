/** Sign-in, sign-out, the admin PIN page and the login/role gates every staff page uses. */
import { config } from '../config.js';
import * as db from '../db.js';
import * as attendanceStore from '../attendance_store.js';
import { flash } from '../flash.js';
import { renderPage } from '../render.js';

const SIGN_IN_EXEMPT = new Set([
  'attendance.index', 'attendance.clock_in', 'attendance.clock_out', 'attendance.overtime_in',
  'attendance.overtime_out', 'auth.account',
]);

function resetSession(req) {
  // Keep express-session's own `cookie` property so the session can still be saved.
  for (const key of Object.keys(req.session)) {
    if (key !== 'cookie') delete req.session[key];
  }
}

function startSession(req, user) {
  resetSession(req);
  req.session.user_id = user.user_id;
  req.session.username = user.username;
  req.session.user_type = user.user_type;
  const full = `${user.first_name || ''} ${user.last_name || ''}`.trim();
  req.session.display_name = full || user.username;
}

/**
 * Confirms the visitor is signed in, active and (unless exempt) on a shift.
 * Returns true when the request may continue; false when it has already been answered.
 */
export async function checkLogin(req, res) {
  if (!req.session.user_id) {
    flash(req, 'info', 'Sign in to continue.');
    res.redirect(`/login?next=${encodeURIComponent(req.originalUrl)}`);
    return false;
  }
  if (!req.session.username || !req.session.user_type) {        // stale cookie from an older version
    resetSession(req);
    flash(req, 'info', 'Please sign in again.');
    res.redirect(`/login?next=${encodeURIComponent(req.originalUrl)}`);
    return false;
  }
  let access;
  try {
    access = await attendanceStore.getAccess(req.session.user_id);
  } catch (error) {
    console.warn('Attendance verification failed:', error.message);
    renderPage(req, res, 'unavailable.html', {}, 503);
    return false;
  }
  if (!access || !access.active) {
    resetSession(req);
    res.redirect('/login');
    return false;
  }
  if (access.user_type) req.session.user_type = access.user_type;
  if (config.navUnlocked) access.allowed = true;               // prototype navigation copy
  req.staffAccess = access;
  if (!SIGN_IN_EXEMPT.has(req.endpoint) && !access.allowed) {
    flash(req, 'info', 'Clock in to a scheduled shift or approved overtime before using the staff system.');
    res.redirect('/attendance/');
    return false;
  }
  return true;
}

export function loginRequired(req, res, next) {
  return checkLogin(req, res).then((ok) => { if (ok) next(); });
}

export function roleRequired(...roles) {
  return (req, res, next) => checkLogin(req, res).then((ok) => {
    if (!ok) return;
    if (!roles.includes(req.session.user_type)) {
      return renderPage(req, res, 'error.html', {
        code: 403,
        heading: 'You do not have access to this page',
        message: 'This page is for admins. Ask an admin if you need it.',
      }, 403);
    }
    return next();
  });
}

const safeNext = (target) => Boolean(target) && target.startsWith('/') && !target.startsWith('//') && !String(target).includes('\\');

export default function register(router) {
  router.get('/staff', 'auth.staff', (req, res) => {
    res.redirect(req.session.user_id ? '/attendance/' : '/login');
  });

  router.get('/login', 'auth.login', (req, res) => {
    const next = String(req.query.next || '');
    if (req.session.user_id) return res.redirect('/attendance/');
    return renderPage(req, res, 'login.html', { next, username: '' });
  });

  router.post('/login', 'auth.login', async (req, res) => {
    const next = String(req.body.next || req.query.next || '');
    const username = String(req.body.username || '').trim();
    const password = String(req.body.password || '');
    if (!username || !password) {
      flash(req, 'error', 'Enter both your username and password.');
      return renderPage(req, res, 'login.html', { next, username }, 400);
    }
    let user;
    try {
      user = await db.callFunctionOne('fn_login_user', username, password);
    } catch (error) {
      console.warn('Sign-in database check failed:', error.message);
      flash(req, 'error', 'Sign-in is temporarily unavailable. Check the database connection and setup, then try again.');
      return renderPage(req, res, 'login.html', { next, username }, 503);
    }
    if (!user) {
      flash(req, 'error', 'Incorrect username or password.');
      return renderPage(req, res, 'login.html', { next, username }, 401);
    }
    if (config.mfaEnabled) {
      resetSession(req);
      req.session.pending_user = {
        user_id: user.user_id, username: user.username, first_name: user.first_name,
        last_name: user.last_name, user_type: user.user_type,
      };
      return res.redirect('/verify-otp');
    }
    startSession(req, user);
    return res.redirect(safeNext(next) ? next : '/attendance/');
  });

  router.get('/verify-otp', 'auth.verify_otp', (req, res) => {
    if (!req.session.pending_user) return res.redirect('/login');
    flash(req, 'info', 'The OTP step is not built yet (phase 2).');
    return renderPage(req, res, 'login.html', { next: '', username: '' });
  });

  router.post('/logout', 'auth.logout', (req, res) => {
    resetSession(req);
    flash(req, 'success', 'You have been signed out.');
    res.redirect('/login');
  });

  router.get('/account', 'auth.account', loginRequired, (req, res) => {
    if (req.session.user_type !== 'AD') {
      return renderPage(req, res, 'error.html', {
        code: 403, heading: 'You do not have access to this page',
        message: 'This page is for admins. Ask an admin if you need it.',
      }, 403);
    }
    return renderPage(req, res, 'account.html', {});
  });

  router.post('/account', 'auth.account', loginRequired, async (req, res) => {
    if (req.session.user_type !== 'AD') {
      return renderPage(req, res, 'error.html', {
        code: 403, heading: 'You do not have access to this page',
        message: 'This page is for admins. Ask an admin if you need it.',
      }, 403);
    }
    try {
      const pin = String(req.body.new_pin || '');
      if (pin !== String(req.body.confirm_pin || '')) throw new Error('The PINs do not match.');
      await db.callProcedure('sp_set_management_pin', req.session.user_id, String(req.body.password || ''), pin);
      flash(req, 'success', 'Approval PIN saved.');
      return res.redirect('/account');
    } catch (error) {
      flash(req, 'error', error.message);
      return renderPage(req, res, 'account.html', {}, 400);
    }
  });
}
