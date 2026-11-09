/** Public shop: catalog with search, filters and sort, product pages, photos. */
import * as db from '../db.js';
import { flash } from '../flash.js';
import { renderPage } from '../render.js';
import { urlFor } from '../urls.js';
import { colorHex, groupProducts, stockStatus, compareSizes } from '../utils.js';

const SORTS = {
  featured: { label: 'Featured' },
  newest: { label: 'Newest', compare: (a, b) => b.newest - a.newest },
  price_low: { label: 'Price: low to high', compare: (a, b) => a.price_min - b.price_min },
  price_high: { label: 'Price: high to low', compare: (a, b) => b.price_min - a.price_min },
  name: { label: 'Name A to Z', compare: (a, b) => a.name.toLowerCase().localeCompare(b.name.toLowerCase()) },
};

const sortList = () => Object.entries(SORTS).map(([key, value]) => ({ key, label: value.label }));

export default function register(router) {
  router.get('/', 'catalog.index', async (req, res) => {
    const q = String(req.query.q || '').trim();
    const category = req.query.category ? Number(req.query.category) : null;
    const inStock = req.query.instock === '1';
    const sort = Object.hasOwn(SORTS, req.query.sort || '') ? req.query.sort : 'featured';
    let rows = [];
    let categories = [];
    try {
      rows = await db.callFunction('fn_list_products', q || null, category, false);
      categories = (await db.callFunction('fn_list_categories')).filter((entry) => entry.product_count);
    } catch (error) {
      flash(req, 'error', error.message);
    }

    let cards = groupProducts(rows);
    if (inStock) cards = cards.filter((card) => card.stock > 0);
    if (SORTS[sort].compare) cards.sort(SORTS[sort].compare);

    const filtered = Boolean(q || category || inStock || sort !== 'featured');
    const sections = [];
    if (!filtered) {
      for (const card of cards) {
        const last = sections[sections.length - 1];
        if (last && last.name === card.category) last.cards.push(card);
        else sections.push({ name: card.category, cards: [card] });
      }
    }
    return renderPage(req, res, 'catalog.html', {
      cards, sections, filtered, q, category, in_stock: inStock, sort, sorts: sortList(), categories,
    });
  });

  router.get('/search-suggestions', 'catalog.suggestions', async (req, res) => {
    const q = String(req.query.q || '').trim().slice(0, 100);
    if (q.length < 2) return res.json([]);
    let cards;
    try {
      cards = groupProducts(await db.callFunction('fn_list_products', q,
        req.query.category ? Number(req.query.category) : null, false));
    } catch {
      return res.status(503).json({ error: 'Search is temporarily unavailable.' });
    }
    return res.json(cards.slice(0, 6).map((card) => ({
      name: card.name,
      url: urlFor('catalog.product', { product_id: card.first_id }),
      price: String(card.price_min),
    })));
  });

  router.get('/product/:product_id(\\d+)', 'catalog.product', async (req, res) => {
    const productId = Number(req.params.product_id);
    let item;
    let variants;
    let categories;
    try {
      item = await db.callFunctionOne('fn_get_product', productId);
      variants = item ? (await db.callFunction('fn_list_variants', productId)).filter((variant) => variant.is_active) : [];
      categories = new Map((await db.callFunction('fn_list_categories')).map((entry) => [entry.category_id, entry.category_name]));
    } catch (error) {
      flash(req, 'error', error.message);
      return renderPage(req, res, 'error.html', { code: 404, heading: 'Page not found', message: 'Check the address or use the menu.' }, 404);
    }
    if (!item || !variants.length) {
      return renderPage(req, res, 'error.html', { code: 404, heading: 'Page not found', message: 'Check the address or use the menu.' }, 404);
    }

    const colors = [];
    const seen = new Set();
    for (const variant of variants) {
      const name = variant.color || '';
      if (!name || seen.has(name)) continue;
      seen.add(name);
      const mine = variants.filter((entry) => (entry.color || '') === name);
      const stocked = mine.filter((entry) => entry.current_stock > 0);
      colors.push({
        name,
        hex: colorHex(name),
        stock: mine.reduce((sum, entry) => sum + entry.current_stock, 0),
        first_id: (stocked.length ? stocked : mine)[0].product_id,
        image_id: mine.find((entry) => entry.image_id)?.image_id ?? null,
      });
    }

    const wanted = String(req.query.color || '').trim().toLowerCase();
    let selected = colors.find((color) => color.name.toLowerCase() === wanted)?.name;
    if (selected === undefined) {
      selected = item.color && seen.has(item.color) ? item.color : (colors[0]?.name ?? '');
    }
    let mine = variants.filter((variant) => (variant.color || '') === selected)
      .sort((a, b) => compareSizes(a.size, b.size));
    if (!mine.length) mine = variants.slice(0, 1);
    const rep = mine.find((variant) => variant.current_stock > 0) || mine[0];

    let photos = [];
    try {
      photos = await db.callFunction('fn_list_product_photos', rep.product_id);
    } catch { /* no gallery */ }
    const ids = photos.map((photo) => photo.image_id);
    const chosen = req.query.photo ? Number(req.query.photo) : null;
    const main = ids.includes(chosen) ? chosen : (ids[0] ?? null);
    const urls = ids.map((imageId) => urlFor('catalog.product_image', { image_id: imageId }));

    const prices = mine.map((variant) => variant.current_price);
    const stock = mine.reduce((sum, variant) => sum + variant.current_stock, 0);
    return renderPage(req, res, 'product.html', {
      item,
      category: categories.get(item.category_id) || '',
      colors,
      selected,
      variants: mine,
      rep,
      photo_ids: ids,
      photo_urls: urls,
      main_photo: main,
      main_index: ids.indexOf(main),
      price_min: Math.min(...prices),
      price_max: Math.max(...prices),
      base_price: Math.min(...mine.map((variant) => variant.base_price)),
      stock,
      status: stockStatus(stock),
    });
  });

  router.get('/media/product/:image_id(\\d+)', 'catalog.product_image', async (req, res) => {
    let row;
    try {
      row = await db.callFunctionOne('fn_get_image', Number(req.params.image_id));
    } catch {
      row = null;
    }
    if (!row) {
      return renderPage(req, res, 'error.html', { code: 404, heading: 'Page not found', message: 'Check the address or use the menu.' }, 404);
    }
    res.set('Content-Type', row.mime_type);
    res.set('Cache-Control', 'public, max-age=31536000, immutable');
    res.set('X-Content-Type-Options', 'nosniff');
    return res.send(Buffer.from(row.image_data));
  });
}
