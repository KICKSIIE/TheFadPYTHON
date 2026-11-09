/** Stock levels and movements. */
import * as db from '../db.js';
import { flash } from '../flash.js';
import { renderPage } from '../render.js';
import { lowStockDefault } from '../rules.js';
import { toInt } from '../utils.js';
import { loginRequired } from './auth.js';

export default function register(router) {
  router.get('/inventory', 'inventory.index', loginRequired, async (req, res) => {
    const q = String(req.query.q || '').trim();
    const lowOnly = req.query.low === '1';
    const category = String(req.query.category || '').trim();
    let limit = req.query.max === undefined ? lowStockDefault() : Number(req.query.max);
    if (!Number.isFinite(limit) || limit < 0) limit = lowStockDefault();

    let items = [];
    try {
      items = await db.callFunction('fn_list_inventory', q || null, lowOnly, limit);
    } catch (error) {
      flash(req, 'error', error.message);
    }
    if (category) items = items.filter((item) => item.category_name === category);
    items.sort((a, b) => a.product_name.localeCompare(b.product_name) || a.product_id - b.product_id);

    let categories = [];
    try {
      categories = (await db.callFunction('fn_list_categories')).map((entry) => entry.category_name);
    } catch {
      categories = [...new Set(items.map((item) => item.category_name))].sort();
    }
    return renderPage(req, res, 'inventory.html', { items, q, low_only: lowOnly, limit, categories, category });
  });

  router.get('/inventory/history', 'inventory.history', loginRequired, async (_req, res) => {
    let rows = [];
    try {
      rows = await db.callFunction('fn_inventory_history', null, 200);
    } catch (error) {
      flash(_req, 'error', error.message);
    }
    return renderPage(_req, res, 'inventory_history.html', { rows, product: null });
  });

  router.get('/inventory/:product_id(\\d+)', 'inventory.item', loginRequired, async (req, res) => {
    const productId = Number(req.params.product_id);
    let product;
    let rows;
    try {
      product = await db.callFunctionOne('fn_get_product', productId);
      rows = await db.callFunction('fn_inventory_history', productId, 50);
    } catch (error) {
      flash(req, 'error', error.message);
      return res.redirect('/inventory/');
    }
    if (!product) {
      return renderPage(req, res, 'error.html', { code: 404, heading: 'Page not found', message: 'Check the address or use the menu.' }, 404);
    }
    return renderPage(req, res, 'inventory_item.html', { product, rows });
  });

  router.post('/inventory/:product_id(\\d+)/move', 'inventory.move', loginRequired, async (req, res) => {
    const productId = Number(req.params.product_id);
    const routine = { in: 'sp_stock_in', out: 'sp_stock_out', adjust: 'sp_adjust_stock' }[req.body.action];
    if (!routine) {
      return renderPage(req, res, 'error.html', { code: 400, heading: 'Request could not be verified', message: 'Reload the page and try again.' }, 400);
    }
    try {
      const quantity = toInt(req.body.quantity, 'Quantity');
      const result = await db.callProcedure(routine, req.session.user_id, productId, quantity, null);
      flash(req, 'success', `Done. Stock is now ${result.p_balance}.`);
    } catch (error) {
      flash(req, 'error', error.message);
    }
    return res.redirect(`/inventory/${productId}`);
  });
}
