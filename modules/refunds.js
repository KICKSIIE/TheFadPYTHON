/** Refunds and the refund report (admin). */
import * as db from '../db.js';
import { flash } from '../flash.js';
import { renderPage } from '../render.js';
import { shopDate, shopNow } from '../time.js';
import { toInt, ValidationError } from '../utils.js';
import { roleRequired } from './auth.js';

const isoToday = () => shopDate(shopNow());
const isDate = (text) => /^\d{4}-\d{2}-\d{2}$/.test(text);

export default function register(router) {
  router.get('/admin/refunds', 'refunds.index', roleRequired('AD'), async (req, res) => {
    const today = isoToday();
    let start = String(req.query.start || '');
    let end = String(req.query.end || '');
    if (!isDate(start) || !isDate(end)) {
      const monthAgo = new Date(shopNow().getTime() - 30 * 86400000);
      start = shopDate(monthAgo);
      end = today;
      if (req.query.start || req.query.end) flash(req, 'error', 'Enter dates as year-month-day.');
    }
    let report = [];
    let refunds = [];
    try {
      report = await db.callFunction('fn_refund_report', start, end);
      refunds = await db.callFunction('fn_list_refunds', start, end);
    } catch (error) {
      flash(req, 'error', error.message);
    }
    return renderPage(req, res, 'admin/refunds.html', {
      report, refunds, start: new Date(`${start}T00:00:00+08:00`), end: new Date(`${end}T00:00:00+08:00`),
    });
  });

  router.get('/admin/refunds/find', 'refunds.find', roleRequired('AD'), (req, res) => {
    try {
      const saleId = toInt(req.query.sale_id, 'Order number');
      return res.redirect(`/admin/refunds/sale/${saleId}`);
    } catch (error) {
      flash(req, 'error', error.message);
      return res.redirect('/admin/refunds/');
    }
  });

  const salePage = async (req, res, saleId) => {
    let order;
    let items;
    try {
      order = await db.callFunctionOne('fn_get_sale', saleId);
      items = await db.callFunction('fn_sale_items', saleId);
    } catch (error) {
      flash(req, 'error', error.message);
      return res.redirect('/admin/refunds/');
    }
    if (!order) {
      flash(req, 'error', `No order number ${saleId}.`);
      return res.redirect('/admin/refunds/');
    }
    return renderPage(req, res, 'admin/refund_sale.html', {
      sale: order, items, can_refund: ['Completed', 'Partially_Refunded'].includes(order.order_status),
    });
  };

  router.get('/admin/refunds/sale/:sale_id(\\d+)', 'refunds.sale', roleRequired('AD'), async (req, res) => {
    const saleId = Number(req.params.sale_id);
    return salePage(req, res, saleId);
  });

  router.post('/admin/refunds/sale/:sale_id(\\d+)', 'refunds.sale', roleRequired('AD'), async (req, res) => {
    const saleId = Number(req.params.sale_id);
    try {
      const result = await db.callProcedure('sp_process_refund', req.session.user_id, saleId,
        toInt(req.body.item_id, 'Item'), toInt(req.body.quantity, 'Quantity'),
        String(req.body.reason || '').trim(), req.body.method, null);
      flash(req, 'success', `Refund #${result.p_refund_id} recorded and the stock was returned.`);
    } catch (error) {
      if (error instanceof ValidationError) flash(req, 'error', error.message);
      else flash(req, 'error', error.message);
    }
    return res.redirect(`/admin/refunds/sale/${saleId}`);
  });
}
