/** POS checkout: build a cart in the session, then save the sale. */
import * as db from '../db.js';
import { flash } from '../flash.js';
import { renderPage } from '../render.js';
import { urlFor } from '../urls.js';
import { toInt } from '../utils.js';
import { loginRequired } from './auth.js';

const cartOf = (req) => req.session.cart || {};

async function catalogByProduct() {
  const rows = await db.callFunction('fn_list_products', null, null, false);
  return new Map(rows.map((product) => [product.product_id, product]));
}

const backToCatalog = (req, res) => res.redirect(urlFor('pos.index', {
  q: req.body.q || '', category: req.body.category || '',
}));

export default function register(router) {
  router.get('/pos', 'pos.index', loginRequired, async (req, res) => {
    const q = String(req.query.q || '').trim().toLowerCase();
    const category = req.query.category ? Number(req.query.category) : null;
    let catalog = new Map();
    try {
      catalog = await catalogByProduct();
    } catch (error) {
      flash(req, 'error', error.message);
    }

    const lines = [];
    let total = 0;
    for (const [pid, qty] of Object.entries(cartOf(req))) {
      const product = catalog.get(Number(pid));
      if (!product) continue;
      const lineTotal = product.current_price * qty;
      total += lineTotal;
      lines.push({ product, qty, line_total: lineTotal, short: qty > product.current_stock });
    }

    const shown = [...catalog.values()]
      .filter((product) => (!q || product.display_name.toLowerCase().includes(q))
        && (category === null || product.category_id === category));
    shown.sort((a, b) => Number(a.current_stock <= 0) - Number(b.current_stock <= 0));
    const categories = [...new Map([...catalog.values()].map((product) => [product.category_id, product.category_name])).entries()]
      .sort((a, b) => a[1].localeCompare(b[1]));

    return renderPage(req, res, 'pos.html', { products: shown, lines, total, categories, q, category });
  });

  router.post('/pos/cart/add', 'pos.add', loginRequired, async (req, res) => {
    let pid;
    let qty;
    let product;
    try {
      pid = toInt(req.body.product_id, 'Product');
      qty = Math.max(1, toInt(req.body.quantity || '1', 'Quantity'));
      product = (await catalogByProduct()).get(pid);
    } catch (error) {
      flash(req, 'error', error.message);
      return backToCatalog(req, res);
    }
    if (!product || product.current_stock <= 0) {
      flash(req, 'error', 'That product is out of stock.');
      return backToCatalog(req, res);
    }
    const cart = cartOf(req);
    let wanted = (cart[String(pid)] || 0) + qty;
    if (wanted > product.current_stock) {
      wanted = product.current_stock;
      flash(req, 'info', `Only ${wanted} of ${product.display_name} in stock. Cart set to ${wanted}.`);
    }
    cart[String(pid)] = wanted;
    req.session.cart = cart;
    return backToCatalog(req, res);
  });

  router.post('/pos/cart/update', 'pos.update', loginRequired, async (req, res) => {
    let pid;
    let qty;
    let product;
    try {
      pid = toInt(req.body.product_id, 'Product');
      const cart = cartOf(req);
      if (req.body.delta) qty = (cart[String(pid)] || 0) + toInt(req.body.delta, 'Change');
      else qty = toInt(req.body.quantity, 'Quantity');
      product = (await catalogByProduct()).get(pid);
    } catch (error) {
      flash(req, 'error', error.message);
      return backToCatalog(req, res);
    }
    const cart = cartOf(req);
    if (qty <= 0 || !product) delete cart[String(pid)];
    else cart[String(pid)] = Math.min(qty, product.current_stock);
    req.session.cart = cart;
    return backToCatalog(req, res);
  });

  router.post('/pos/cart/clear', 'pos.clear', loginRequired, (req, res) => {
    delete req.session.cart;
    flash(req, 'info', 'Cart cleared.');
    return backToCatalog(req, res);
  });

  router.post('/pos/checkout', 'pos.checkout', loginRequired, async (req, res) => {
    const cart = cartOf(req);
    if (!Object.keys(cart).length) {
      flash(req, 'error', 'Add at least one item to the cart.');
      return res.redirect('/pos/');
    }
    const items = Object.entries(cart).map(([pid, qty]) => ({ product_id: Number(pid), quantity: qty }));
    let result;
    try {
      result = await db.callProcedure('sp_create_sale', req.session.user_id,
        req.body.fulfillment_type, req.body.payment_method,
        String(req.body.customer_name || '').trim(), String(req.body.customer_contact || '').trim(),
        String(req.body.delivery_address || '').trim(), JSON.stringify(items), null);
    } catch (error) {
      flash(req, 'error', error.message);
      return res.redirect('/pos/');
    }
    delete req.session.cart;
    flash(req, 'success', 'Sale saved.');
    return res.redirect(urlFor('orders.detail', { sale_id: result.p_sale_id }));
  });
}
