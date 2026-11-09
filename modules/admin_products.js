/** Products, variants and categories (admin). */
import * as db from '../db.js';
import { flash } from '../flash.js';
import { renderPage } from '../render.js';
import { urlFor } from '../urls.js';
import { groupProducts, readPhotos, toDecimal, toInt, compareSizes, ValidationError } from '../utils.js';
import { roleRequired } from './auth.js';

const photoFiles = (req) => (req.files || []).filter((file) => file.fieldname === 'photos');

async function categoriesOrFlash(req) {
  try {
    return await db.callFunction('fn_list_categories');
  } catch (error) {
    flash(req, 'error', error.message);
    return [];
  }
}

function readProductForm(body) {
  return {
    name: String(body.product_name || '').trim(),
    price: toDecimal(body.base_price, 'Price'),
    category_id: toInt(body.category_id, 'Category'),
    description: String(body.description || '').trim(),
  };
}

export default function register(router) {
  router.get('/admin/products', 'admin_products.index', roleRequired('AD'), async (req, res) => {
    const q = String(req.query.q || '').trim();
    const category = req.query.category ? Number(req.query.category) : null;
    const showInactive = req.query.inactive === '1';
    let products = [];
    try {
      products = await db.callFunction('fn_list_products', q || null, category, showInactive);
    } catch (error) {
      flash(req, 'error', error.message);
    }
    const variantsView = req.query.variants === '1';
    return renderPage(req, res, 'admin/products.html', {
      products,
      cards: groupProducts(products),
      variants_view: variantsView,
      categories: await categoriesOrFlash(req),
      q,
      category,
      show_inactive: showInactive,
    });
  });

  router.get('/admin/products/new', 'admin_products.new', roleRequired('AD'), async (req, res) => renderPage(req, res, 'admin/product_form.html', {
    product: {}, categories: await categoriesOrFlash(req), editing: false,
  }));

  router.post('/admin/products/new', 'admin_products.new', roleRequired('AD'), async (req, res) => {
    const categories = await categoriesOrFlash(req);
    try {
      const values = readProductForm(req.body);
      const { mimes, datas } = readPhotos(photoFiles(req));
      await db.callProcedure('sp_create_product', values.name, values.price, values.category_id,
        values.description, String(req.body.sizes || '').trim(), String(req.body.colors || '').trim(),
        mimes.length ? mimes : null, datas.length ? datas : null, null);
    } catch (error) {
      flash(req, 'error', error.message);
      return renderPage(req, res, 'admin/product_form.html', {
        product: req.body, categories, editing: false,
      }, 400);
    }
    const name = String(req.body.product_name || '').trim();
    flash(req, 'success', `Added ${name}. Stock starts at 0; add stock from Inventory.`);
    return res.redirect('/admin/products/');
  });

  const editPage = async (req, res, productId, categories, formValues, status) => {
    let current;
    let variants;
    try {
      current = await db.callFunctionOne('fn_get_product', productId);
      variants = await db.callFunction('fn_list_variants', productId);
    } catch (error) {
      flash(req, 'error', error.message);
      return res.redirect('/admin/products/');
    }
    if (!current) {
      return renderPage(req, res, 'error.html', { code: 404, heading: 'Page not found', message: 'Check the address or use the menu.' }, 404);
    }
    variants.sort((a, b) => (a.color || '').localeCompare(b.color || '') || compareSizes(a.size, b.size));
    return renderPage(req, res, 'admin/product_form.html', {
      product: formValues || current, current, categories, editing: true, product_id: productId, variants,
    }, status);
  };

  router.get('/admin/products/:product_id(\\d+)/edit', 'admin_products.edit', roleRequired('AD'), async (req, res) => {
    const productId = Number(req.params.product_id);
    return editPage(req, res, productId, await categoriesOrFlash(req), null, 200);
  });

  router.post('/admin/products/:product_id(\\d+)/edit', 'admin_products.edit', roleRequired('AD'), async (req, res) => {
    const productId = Number(req.params.product_id);
    const categories = await categoriesOrFlash(req);
    try {
      const values = readProductForm(req.body);
      await db.callProcedure('sp_update_product', productId, values.name, values.price, values.category_id,
        String(req.body.size || '').trim(), String(req.body.color || '').trim(), values.description,
        req.body.apply_all === '1');
    } catch (error) {
      flash(req, 'error', error.message);
      return editPage(req, res, productId, categories, req.body, 400);
    }
    flash(req, 'success', `Saved ${String(req.body.product_name || '').trim()}.`);
    return res.redirect('/admin/products/');
  });

  // ------------------------------------------------------------------ photos
  router.get('/admin/products/:product_id(\\d+)/photos', 'admin_products.photos', roleRequired('AD'), async (req, res) => {
    const productId = Number(req.params.product_id);
    let current;
    let gallery;
    let variants;
    try {
      current = await db.callFunctionOne('fn_get_product', productId);
      gallery = await db.callFunction('fn_list_product_photos', productId);
      variants = await db.callFunction('fn_list_variants', productId);
    } catch (error) {
      flash(req, 'error', error.message);
      return res.redirect('/admin/products/');
    }
    if (!current) {
      return renderPage(req, res, 'error.html', { code: 404, heading: 'Page not found', message: 'Check the address or use the menu.' }, 404);
    }
    const urls = gallery.map((photo) => urlFor('catalog.product_image', { image_id: photo.image_id }));
    const colors = [];
    const seen = new Set();
    for (const variant of variants) {
      const name = variant.color || '';
      if (name && !seen.has(name)) {
        seen.add(name);
        colors.push({ name, first_id: variant.product_id });
      }
    }
    const sameColor = variants.filter((variant) => (variant.color || '') === (current.color || ''));
    return renderPage(req, res, 'admin/product_photos.html', {
      current, gallery, photo_urls: urls, product_id: productId, colors, many_sizes: sameColor.length > 1,
    });
  });

  router.post('/admin/products/:product_id(\\d+)/photos/upload', 'admin_products.upload_photos', roleRequired('AD'), async (req, res) => {
    const productId = Number(req.params.product_id);
    try {
      const { mimes, datas } = readPhotos(photoFiles(req));
      if (!datas.length) throw new ValidationError('Choose at least one photo to upload.');
      for (let index = 0; index < datas.length; index += 1) {
        await db.callProcedure('sp_add_product_photo', productId, mimes[index], datas[index],
          req.body.apply_all === '1', null);
      }
      flash(req, 'success', `Added ${datas.length} photo${datas.length === 1 ? '' : 's'}.`);
    } catch (error) {
      flash(req, 'error', error.message);
    }
    return res.redirect(`/admin/products/${productId}/photos`);
  });

  router.post('/admin/products/:product_id(\\d+)/photos/:image_id(\\d+)/remove', 'admin_products.remove_photo', roleRequired('AD'), async (req, res) => {
    const productId = Number(req.params.product_id);
    try {
      await db.callProcedure('sp_remove_product_photo', productId, Number(req.params.image_id), req.body.apply_all === '1');
      flash(req, 'success', 'Photo removed.');
    } catch (error) {
      flash(req, 'error', error.message);
    }
    return res.redirect(`/admin/products/${productId}/photos`);
  });

  router.post('/admin/products/:product_id(\\d+)/photos/:image_id(\\d+)/cover', 'admin_products.cover_photo', roleRequired('AD'), async (req, res) => {
    const productId = Number(req.params.product_id);
    try {
      await db.callProcedure('sp_set_cover_photo', productId, Number(req.params.image_id), req.body.apply_all === '1');
      flash(req, 'success', 'Cover photo updated.');
    } catch (error) {
      flash(req, 'error', error.message);
    }
    return res.redirect(`/admin/products/${productId}/photos`);
  });

  router.post('/admin/products/:product_id(\\d+)/add-variant', 'admin_products.add_variant', roleRequired('AD'), async (req, res) => {
    const productId = Number(req.params.product_id);
    try {
      const result = await db.callProcedure('sp_add_variant', productId,
        String(req.body.size || '').trim(), String(req.body.color || '').trim(), null);
      flash(req, 'success', 'Variant added with stock 0. Add stock from Inventory.');
      return res.redirect(`/admin/products/${result.p_new_id}/edit`);
    } catch (error) {
      flash(req, 'error', error.message);
      return res.redirect(`/admin/products/${productId}/edit`);
    }
  });

  router.post('/admin/products/:product_id(\\d+)/active', 'admin_products.set_active', roleRequired('AD'), async (req, res) => {
    const productId = Number(req.params.product_id);
    const active = req.body.active === '1';
    try {
      await db.callProcedure('sp_set_product_active', productId, active);
      flash(req, 'success', active
        ? 'Product reactivated.'
        : 'Product deactivated. It no longer shows on the catalog or POS.');
    } catch (error) {
      flash(req, 'error', error.message);
    }
    return res.redirect(req.get('Referer') || '/admin/products/');
  });

  // ---------------------------------------------------------------- categories
  router.get('/admin/products/categories', 'admin_products.categories', roleRequired('AD'), async (req, res) => renderPage(req, res, 'admin/categories.html', {
    categories: await categoriesOrFlash(req),
  }));

  router.post('/admin/products/categories', 'admin_products.categories', roleRequired('AD'), async (req, res) => {
    try {
      const name = String(req.body.category_name || '').trim();
      const order = toInt(req.body.display_order || '0', 'Display order');
      await db.callProcedure('sp_create_category', name, order, null);
      flash(req, 'success', `Added category ${name}.`);
    } catch (error) {
      flash(req, 'error', error.message);
    }
    return res.redirect('/admin/products/categories');
  });

  router.post('/admin/products/categories/:category_id(\\d+)', 'admin_products.update_category', roleRequired('AD'), async (req, res) => {
    try {
      const name = String(req.body.category_name || '').trim();
      const order = toInt(req.body.display_order || '0', 'Display order');
      await db.callProcedure('sp_update_category', Number(req.params.category_id), name, order);
      flash(req, 'success', 'Category saved.');
    } catch (error) {
      flash(req, 'error', error.message);
    }
    return res.redirect('/admin/products/categories');
  });

  router.post('/admin/products/categories/:category_id(\\d+)/delete', 'admin_products.delete_category', roleRequired('AD'), async (req, res) => {
    try {
      await db.callProcedure('sp_delete_category', Number(req.params.category_id));
      flash(req, 'success', 'Category deleted.');
    } catch (error) {
      flash(req, 'error', error.message);
    }
    return res.redirect('/admin/products/categories');
  });
}
