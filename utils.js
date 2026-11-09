/** Stock defaults, sizes, colours and the product/size helpers shared by the shop and admin screens. */
import { LOW_STOCK } from './config.js';

export { LOW_STOCK };

export class ValidationError extends Error {}

export function toDecimal(value, label) {
  const text = String(value ?? '').trim();
  const number = Number(text);
  if (!text || !Number.isFinite(number)) throw new ValidationError(`${label} must be a number.`);
  return number;
}

export function toInt(value, label) {
  const text = String(value ?? '').trim();
  if (!/^[+-]?\d+$/.test(text)) throw new ValidationError(`${label} must be a whole number.`);
  return Number.parseInt(text, 10);
}

const SIZE_ORDER = ['XXS', 'XS', 'S', 'M', 'L', 'XL', 'XXL', '2XL', 'XXXL', '3XL', '4XL', '5XL'];

export function sizeRank(size) {
  if (!size) return { rank: 0, index: 0, text: '' };
  const text = String(size).toUpperCase();
  const index = SIZE_ORDER.indexOf(text);
  return index >= 0 ? { rank: 1, index, text: '' } : { rank: 2, index: 0, text };
}

export function compareSizes(a, b) {
  const left = sizeRank(a);
  const right = sizeRank(b);
  if (left.rank !== right.rank) return left.rank - right.rank;
  if (left.rank === 1) return left.index - right.index;
  return left.text.localeCompare(right.text);
}

const MAGIC = [
  { mime: 'image/jpeg', test: (d) => d[0] === 0xff && d[1] === 0xd8 && d[2] === 0xff },
  { mime: 'image/png', test: (d) => d.subarray(0, 8).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])) },
  { mime: 'image/webp', test: (d) => d.subarray(0, 4).toString('ascii') === 'RIFF' && d.subarray(8, 12).toString('ascii') === 'WEBP' },
];

/** Returns { mime, data } for an uploaded photo, or { mime: null } when nothing was chosen. */
export function readPhoto(file) {
  if (!file || !file.buffer || !file.buffer.length) return { mime: null, data: null };
  if (file.buffer.length > 3 * 1024 * 1024) {
    throw new ValidationError('The photo is larger than 3 MB. Resize it and try again.');
  }
  const found = MAGIC.find((entry) => entry.test(file.buffer));
  if (!found) throw new ValidationError('The photo must be a JPG, PNG or WebP image.');
  return { mime: found.mime, data: file.buffer };
}

export function readPhotos(files = [], limit = 8) {
  const mimes = [];
  const datas = [];
  for (const file of files) {
    const { mime, data } = readPhoto(file);
    if (mime) { mimes.push(mime); datas.push(data); }
  }
  if (datas.length > limit) throw new ValidationError(`A product can have up to ${limit} photos.`);
  return { mimes, datas };
}

const COLOR_HEX = {
  white: '#f5f5f2', black: '#17191f', navy: '#1f2f54', indigo: '#2e4a7d', denim: '#4a6a96',
  charcoal: '#3b4048', grey: '#9aa0a8', gray: '#9aa0a8', silver: '#c3c7cc', sage: '#9db39a',
  forest: '#2f5a43', green: '#4c8a5a', olive: '#6d7040', khaki: '#b9a779', beige: '#d8c9ad',
  cream: '#f2ead7', ivory: '#f4efdf', sand: '#d9c3a0', natural: '#e8dfc9', brown: '#7a5238',
  tan: '#c19a6b', red: '#b3342f', maroon: '#6f1f2b', burgundy: '#6f1f2b', pink: '#e6a1b4',
  orange: '#d9762b', yellow: '#e4be3f', mustard: '#c9a227', blue: '#3f6fb5', sky: '#8fb8de',
  teal: '#2f7f84', purple: '#6c4f9b', lavender: '#b5a6d6',
};

export function colorHex(name) {
  if (!name) return '#c8ccd2';
  const key = String(name).trim().toLowerCase();
  if (COLOR_HEX[key]) return COLOR_HEX[key];
  const words = key.split(/\s+/).reverse();
  for (const word of words) if (COLOR_HEX[word]) return COLOR_HEX[word];
  return '#c8ccd2';
}

export function stockStatus(stock) {
  return stock <= 0 ? 'out' : stock <= LOW_STOCK ? 'low' : 'in';
}

/** One card per product (style). Rows are color/size variants: collect colors, sizes and stock. */
export function groupProducts(rows) {
  const groups = new Map();
  for (const row of rows) {
    const key = `${row.category_name}||${row.product_name}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(row);
  }
  const cards = [];
  for (const items of groups.values()) {
    const sorted = [...items].sort((a, b) => (a.color || '').localeCompare(b.color || '') || compareSizes(a.size, b.size));
    const byColor = new Map();
    for (const row of [...sorted].sort((a, b) => a.product_id - b.product_id)) {
      const color = row.color || '';
      if (!byColor.has(color)) byColor.set(color, []);
      byColor.get(color).push(row);
    }
    const colors = [];
    for (const [color, group] of byColor) {
      const stocked = group.filter((row) => row.current_stock > 0);
      colors.push({
        name: color,
        hex: colorHex(color),
        stock: group.reduce((sum, row) => sum + row.current_stock, 0),
        image_id: group.find((row) => row.image_id)?.image_id ?? null,
        first_id: (stocked.length ? stocked : group)[0].product_id,
      });
    }
    const named = colors.filter((color) => color.name);
    const sizes = new Map();
    for (const row of items) {
      if (row.size) sizes.set(row.size, (sizes.get(row.size) || 0) + row.current_stock);
    }
    const sizeList = [...sizes.entries()]
      .sort((a, b) => compareSizes(a[0], b[0]))
      .map(([size, stock]) => ({ size, stock }));
    const prices = items.map((row) => row.current_price);
    const stockedRows = items.filter((row) => row.current_stock > 0);
    cards.push({
      category: items[0].category_name,
      name: items[0].product_name,
      rows: sorted,
      first_id: (stockedRows.length ? stockedRows : sorted)[0].product_id,
      colors: named,
      color_count: named.length,
      sizes: sizeList,
      price_min: Math.min(...prices),
      price_max: Math.max(...prices),
      base_min: Math.min(...items.map((row) => row.base_price)),
      image_id: colors.find((color) => color.image_id)?.image_id ?? null,
      description: items.find((row) => row.description)?.description ?? null,
      promo: items.find((row) => row.discount_name) || null,
      stock: items.reduce((sum, row) => sum + row.current_stock, 0),
      newest: Math.max(...items.map((row) => row.product_id)),
    });
  }
  for (const card of cards) card.status = stockStatus(card.stock);
  return cards;
}
