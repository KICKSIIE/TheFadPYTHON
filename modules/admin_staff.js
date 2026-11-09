/** Staff management (admin). */
import * as db from '../db.js';
import { flash } from '../flash.js';
import { renderPage } from '../render.js';
import { urlFor } from '../urls.js';
import { roleRequired } from './auth.js';

const staffFields = (body) => {
  const values = ['first_name', 'last_name', 'user_type', 'email', 'station']
    .map((key) => String(body[key] || '').trim());
  const start = String(body.hired_on || '').trim();
  if (start && !/^\d{4}-\d{2}-\d{2}$/.test(start)) return values.concat([null]);
  return values.concat([start || null]);
};

export default function register(router) {
  router.get('/admin/staff', 'admin_staff.index', roleRequired('AD'), async (req, res) => {
    let staff = [];
    try {
      staff = await db.callFunction('fn_list_staff');
    } catch (error) {
      flash(req, 'error', error.message);
    }
    return renderPage(req, res, 'admin/staff.html', { staff });
  });

  router.get('/admin/staff/new', 'admin_staff.new', roleRequired('AD'), (req, res) => renderPage(req, res, 'admin/staff_form.html', {
    person: { user_type: 'CA', hired_on: new Date() }, editing: false,
  }));

  router.post('/admin/staff/new', 'admin_staff.new', roleRequired('AD'), async (req, res) => {
    const username = String(req.body.username || '').trim();
    const password = String(req.body.password || '');
    try {
      const [first, last, userType, email, station, start] = staffFields(req.body);
      await db.callProcedure('sp_create_staff', username, password, first, last, userType, email, station, start, null);
    } catch (error) {
      flash(req, 'error', error.message);
      return renderPage(req, res, 'admin/staff_form.html', { person: req.body, editing: false }, 400);
    }
    flash(req, 'success', `Created account ${username}.`);
    return res.redirect('/admin/staff/');
  });

  router.get('/admin/staff/:user_id(\\d+)/edit', 'admin_staff.edit', roleRequired('AD'), async (req, res) => {
    const userId = Number(req.params.user_id);
    let person;
    try {
      person = await db.callFunctionOne('fn_get_staff', userId);
    } catch (error) {
      flash(req, 'error', error.message);
      return res.redirect('/admin/staff/');
    }
    if (!person) {
      return renderPage(req, res, 'error.html', { code: 404, heading: 'Page not found', message: 'Check the address or use the menu.' }, 404);
    }
    return renderPage(req, res, 'admin/staff_form.html', { person, editing: true, user_id: userId });
  });

  router.post('/admin/staff/:user_id(\\d+)/edit', 'admin_staff.edit', roleRequired('AD'), async (req, res) => {
    const userId = Number(req.params.user_id);
    try {
      const [first, last, userType, email, station, start] = staffFields(req.body);
      await db.callProcedure('sp_update_staff', userId, first, last, userType, email, station, start);
    } catch (error) {
      flash(req, 'error', error.message);
      return renderPage(req, res, 'admin/staff_form.html', {
        person: { ...req.body, username: req.body.username || '' }, editing: true, user_id: userId,
      }, 400);
    }
    flash(req, 'success', 'Staff details saved.');
    return res.redirect('/admin/staff/');
  });

  router.post('/admin/staff/:user_id(\\d+)/active', 'admin_staff.set_active', roleRequired('AD'), async (req, res) => {
    const userId = Number(req.params.user_id);
    const active = req.body.active === '1';
    if (!active && userId === Number(req.session.user_id)) {
      flash(req, 'error', 'You cannot deactivate your own account.');
      return res.redirect('/admin/staff/');
    }
    try {
      await db.callProcedure('sp_set_staff_active', userId, active);
      flash(req, 'success', active
        ? 'Account reactivated.'
        : 'Account deactivated. They can no longer sign in.');
    } catch (error) {
      flash(req, 'error', error.message);
    }
    return res.redirect(urlFor('admin_staff.index'));
  });
}
