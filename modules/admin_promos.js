/** Promo manager (admin). */
import * as db from '../db.js';
import { flash } from '../flash.js';
import { renderPage } from '../render.js';
import { urlFor } from '../urls.js';
import { toInt, ValidationError } from '../utils.js';
import { roleRequired } from './auth.js';

async function styles() {
  const seen = new Set();
  const out = [];
  for (const row of await db.callFunction('fn_list_products', null, null, false)) {
    const key = `${row.category_name}||${row.product_name}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({ product_id: row.product_id, name: row.product_name });
  }
  return out;
}

function parseDate(value, label) {
  const text = String(value || '').trim();
  if (!/^\d{4}-\d{2}-\d{2}$/.test(text)) throw new ValidationError(`${label} must be a valid date.`);
  return text;
}

async function linkedProducts(rows) {
  const catalog = new Map(rows.length
    ? (await db.callFunction('fn_list_products', null, null, true)).map((product) => [product.product_id, product])
    : []);
  const grouped = new Map();
  for (const row of rows) {
    const product = catalog.get(row.product_id) || row;
    const key = `${product.product_name}||${product.category_id ?? ''}`;
    if (!grouped.has(key)) {
      grouped.set(key, {
        name: product.product_name,
        product_id: row.product_id,
        variants: 0,
        base: row.base_price,
        promo: row.current_price,
      });
    }
    grouped.get(key).variants += 1;
  }
  return [...grouped.values()];
}

export default function register(router) {
  router.get('/admin/promos', 'admin_promos.index', roleRequired('AD'), async (req, res) => {
    let rows = [];
    try {
      await db.callProcedure('sp_expire_promos', null);
      rows = await db.callFunction('fn_list_discounts');
      for (const row of rows) {
        const productNames = await db.callFunction('fn_discount_product_names', row.discount_id);
        row.product_names = productNames.map((entry) => entry.product_name);
        row.variant_count = productNames.reduce((sum, entry) => sum + Number(entry.variants), 0);
      }
    } catch (error) {
      flash(req, 'error', error.message);
    }
    return renderPage(req, res, 'admin/promos.html', { rows });
  });

  router.get('/admin/promos/new', 'admin_promos.new', roleRequired('AD'), async (req, res) => {
    let products = [];
    try {
      products = await styles();
    } catch (error) {
      flash(req, 'error', error.message);
    }
    return renderPage(req, res, 'admin/promo_form.html', { promo: {}, products, editing: false, today: new Date() });
  });

  router.post('/admin/promos/new', 'admin_promos.new', roleRequired('AD'), async (req, res) => {
    let products = [];
    try {
      products = await styles();
    } catch (error) {
      flash(req, 'error', error.message);
    }
    try {
      const name = String(req.body.discount_name || '').trim();
      const percentage = toInt(req.body.discount_percentage, 'Discount percent');
      const start = parseDate(req.body.start_date, 'Start date');
      const end = parseDate(req.body.end_date, 'End date');
      const scope = req.body.scope || 'NONE';
      const productId = scope === 'PRODUCT' ? toInt(req.body.product_id, 'Product') : null;
      const created = await db.callProcedure('sp_create_discount', name, percentage, start, end, 'NONE', null, null);
      flash(req, 'success', `Created promo ${name}.`);
      if (scope === 'PRODUCT' || scope === 'STORE') {
        try {
          const applied = await db.callProcedure('sp_apply_discount', created.p_discount_id, scope, productId, null);
          flash(req, 'success', `Applied to ${applied.p_products_updated} item(s).`);
        } catch (error) {
          flash(req, 'error', `The promo was created but not applied: ${error.message}`);
          return res.redirect(`/admin/promos/${created.p_discount_id}`);
        }
      }
      return res.redirect('/admin/promos/');
    } catch (error) {
      flash(req, 'error', error.message);
      return renderPage(req, res, 'admin/promo_form.html', {
        promo: req.body, products, editing: false, today: new Date(),
      }, 400);
    }
  });

  const loadPromo = async (req, res, discountId) => {
    let promo;
    let linked;
    let products;
    try {
      promo = await db.callFunctionOne('fn_get_discount', discountId);
      linked = await linkedProducts(await db.callFunction('fn_discount_products', discountId));
      products = await styles();
    } catch (error) {
      flash(req, 'error', error.message);
      return { redirected: res.redirect('/admin/promos/') };
    }
    if (!promo) {
      return {
        redirected: renderPage(req, res, 'error.html', {
          code: 404, heading: 'Page not found', message: 'Check the address or use the menu.',
        }, 404),
      };
    }
    return { promo, linked, products, discountId };
  };

  router.get('/admin/promos/:discount_id(\\d+)', 'admin_promos.edit', roleRequired('AD'), async (req, res) => {
    const state = await loadPromo(req, res, Number(req.params.discount_id));
    if (state.redirected) return state.redirected;
    if (req.query.view === '1') {
      return renderPage(req, res, 'admin/promo_detail.html', { promo: state.promo, linked: state.linked });
    }
    return renderPage(req, res, 'admin/promo_form.html', {
      promo: state.promo,
      linked: state.linked,
      products: state.products,
      editing: true,
      discount_id: state.discountId,
      today: new Date(),
    });
  });

  router.post('/admin/promos/:discount_id(\\d+)', 'admin_promos.edit', roleRequired('AD'), async (req, res) => {
    const discountId = Number(req.params.discount_id);
    try {
      const name = String(req.body.discount_name || '').trim();
      const percentage = toInt(req.body.discount_percentage, 'Discount percent');
      const start = parseDate(req.body.start_date, 'Start date');
      const end = parseDate(req.body.end_date, 'End date');
      await db.callProcedure('sp_update_discount', discountId, name, percentage, start, end, false, null);
      flash(req, 'success', 'Promo saved. Prices on linked products were updated.');
    } catch (error) {
      flash(req, 'error', error.message);
    }
    return res.redirect(`/admin/promos/${discountId}`);
  });

  router.get('/admin/promos/:discount_id(\\d+)/view', 'admin_promos.view', roleRequired('AD'), async (req, res) => {
    const discountId = Number(req.params.discount_id);
    let promo;
    let linked;
    try {
      promo = await db.callFunctionOne('fn_get_discount', discountId);
      if (!promo) {
        return renderPage(req, res, 'error.html', { code: 404, heading: 'Page not found', message: 'Check the address or use the menu.' }, 404);
      }
      linked = await linkedProducts(await db.callFunction('fn_discount_products', discountId));
    } catch (error) {
      flash(req, 'error', error.message);
      return res.redirect('/admin/promos/');
    }
    return renderPage(req, res, 'admin/promo_detail.html', { promo, linked });
  });

  router.post('/admin/promos/:discount_id(\\d+)/end', 'admin_promos.end_now', roleRequired('AD'), async (req, res) => {
    try {
      await db.callProcedure('sp_update_discount', Number(req.params.discount_id), null, null, null, null, true, null);
      flash(req, 'success', 'Promo ended. Prices are back to normal.');
    } catch (error) {
      flash(req, 'error', error.message);
    }
    return res.redirect('/admin/promos/');
  });

  router.post('/admin/promos/:discount_id(\\d+)/apply', 'admin_promos.apply', roleRequired('AD'), async (req, res) => {
    const discountId = Number(req.params.discount_id);
    const scope = req.body.scope || '';
    try {
      const productId = scope === 'PRODUCT' ? toInt(req.body.product_id, 'Product') : null;
      const result = await db.callProcedure('sp_apply_discount', discountId, scope, productId, null);
      flash(req, 'success', `Promo applied to ${result.p_products_updated} product(s).`);
    } catch (error) {
      flash(req, 'error', error.message);
    }
    return res.redirect(`/admin/promos/${discountId}`);
  });

  router.post('/admin/promos/unlink/:product_id(\\d+)', 'admin_promos.unlink', roleRequired('AD'), async (req, res) => {
    try {
      await db.callProcedure('sp_clear_product_discount', Number(req.params.product_id));
      flash(req, 'success', 'Promo removed from the product.');
    } catch (error) {
      flash(req, 'error', error.message);
    }
    return res.redirect(req.get('Referer') || urlFor('admin_promos.index'));
  });

  router.post('/admin/promos/:discount_id(\\d+)/delete', 'admin_promos.delete_unused', roleRequired('AD'), async (req, res) => {
    try {
      await db.callProcedure('sp_delete_unused_discount', Number(req.params.discount_id));
      flash(req, 'success', 'Unused promo deleted.');
    } catch (error) {
      flash(req, 'error', error.message);
    }
    return res.redirect('/admin/promos/');
  });
}
