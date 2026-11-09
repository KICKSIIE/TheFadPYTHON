/** Order list, receipt and delivery status. */
import * as db from '../db.js';
import { flash } from '../flash.js';
import { renderPage } from '../render.js';
import { shopDate, todayIso } from '../time.js';
import { urlFor } from '../urls.js';
import { loginRequired } from './auth.js';

const STATUSES = ['Pending', 'Out_for_Delivery', 'Completed', 'Cancelled', 'Partially_Refunded', 'Refunded'];

export default function register(router) {
  router.get('/orders', 'orders.index', loginRequired, async (req, res) => {
    const today = todayIso();
    let start = String(req.query.start || today);
    let end = String(req.query.end || today);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(start) || !/^\d{4}-\d{2}-\d{2}$/.test(end)) {
      flash(req, 'error', 'Enter dates as year-month-day.');
      start = today;
      end = today;
    }
    const status = req.query.status || null;
    let rows = [];
    try {
      rows = await db.callFunction('fn_list_sales', start, end, status);
    } catch (error) {
      flash(req, 'error', error.message);
    }
    const total = rows
      .filter((row) => !['Cancelled', 'Refunded'].includes(row.order_status))
      .reduce((sum, row) => sum + Number(row.total_amount), 0);
    return renderPage(req, res, 'orders.html', {
      rows, start: new Date(`${start}T00:00:00+08:00`), end: new Date(`${end}T00:00:00+08:00`), status, statuses: STATUSES, total,
    });
  });

  router.get('/orders/:sale_id(\\d+)', 'orders.detail', loginRequired, async (req, res) => {
    const saleId = Number(req.params.sale_id);
    let sale;
    let items;
    try {
      sale = await db.callFunctionOne('fn_get_sale', saleId);
      items = await db.callFunction('fn_sale_items', saleId);
    } catch (error) {
      flash(req, 'error', error.message);
      return res.redirect('/orders/');
    }
    if (!sale) {
      return renderPage(req, res, 'error.html', { code: 404, heading: 'Page not found', message: 'Check the address or use the menu.' }, 404);
    }
    return renderPage(req, res, 'order_detail.html', { sale, items });
  });

  router.post('/orders/:sale_id(\\d+)/status', 'orders.set_status', loginRequired, async (req, res) => {
    const saleId = Number(req.params.sale_id);
    try {
      await db.callProcedure('sp_update_order_status', req.session.user_id, saleId,
        req.body.new_status, String(req.body.rider_service || '').trim(),
        String(req.body.rider_contact || '').trim());
      flash(req, 'success', 'Order updated.');
    } catch (error) {
      flash(req, 'error', error.message);
    }
    return res.redirect(urlFor('orders.detail', { sale_id: saleId }));
  });
}
