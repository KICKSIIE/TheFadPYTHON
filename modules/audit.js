/** Readable audit history with an explicit allowlist of safe business fields. */
import * as db from '../db.js';
import { flash } from '../flash.js';
import { renderPage } from '../render.js';
import { shopDate, shopNow, strftime } from '../time.js';
import { roleRequired } from './auth.js';

const ENTITIES = {
  product: 'product',
  category: 'category',
  users: 'staff account',
  discount: 'promo',
  sales: 'sale',
  sale_item: 'sale item',
  refund: 'refund',
  inventory_logs: 'stock movement',
  daily_time_record: 'attendance record',
  shift_setting: 'shift schedule',
  overtime_permit: 'overtime',
  management_pin: 'approval PIN',
  product_photo: 'product photo link',
  product_image: 'product photo',
};
const ACTIONS = { INSERT: 'created', UPDATE: 'updated', DELETE: 'deleted', SET_PIN: 'set' };
const BADGES = { INSERT: 'ok', UPDATE: '', DELETE: 'warn', SET_PIN: 'dark' };
const ROLES = { AD: 'Admin', CA: 'Cashier' };
const SUBJECTS = {
  product: 'product_name', category: 'category_name', discount: 'discount_name',
  users: 'username', refund: 'refund_id',
};

function subject(entity, data) {
  if (!data || typeof data !== 'object') return '';
  if (entity === 'product' && data.product_name) {
    let name = String(data.product_name);
    if (data.color) name += ` - ${data.color}`;
    if (data.size) name += ` (${data.size})`;
    return name;
  }
  if (['sale_item', 'refund', 'inventory_logs'].includes(entity)) {
    const parts = [];
    if (data.sale_id) parts.push(`Receipt #${data.sale_id}`);
    if (data.product_id) parts.push(`Product #${data.product_id}`);
    return parts.join(' · ');
  }
  if (entity === 'sales' && data.sale_id) return `#${data.sale_id}`;
  const key = SUBJECTS[entity];
  const value = key ? data[key] : null;
  return value === null || value === undefined || value === '' ? '' : String(value);
}

// Unknown fields stay private until explicitly reviewed for display.
const FIELDS = {
  product_photo: 'product_id image_id sort_order',
  product_image: 'image_id mime_type uploaded_at',
  product: 'sale_id product_id product_name description base_price current_price current_stock category_id discount_id color size is_active',
  category: 'category_id category_name display_order',
  users: 'user_id username first_name middle_name last_name user_type station inventory_section hourly_rate email hired_on is_active isActive',
  discount: 'discount_id discount_name discount_percentage start_date end_date',
  sales: 'sale_id user_id customer_name customer_contact subtotal discount_amount total_amount delivery_address payment_method order_status rider_service ride_service rider_contact sale_date sales_date fulfillment_type',
  sale_item: 'item_id sale_item_id sale_id product_id quantity base_price unit_price_at_sale discount_id quantity_refunded',
  refund: 'refund_id sale_id item_id sale_item_id quantity_refunded refund_amount refund_method quantity amount method reason processed_by refund_date refunded_at',
  inventory_logs: 'log_id product_id sale_id user_id transaction_type quantity_changed balance_after logged_at note',
  daily_time_record: 'dtr_id user_id time_in time_out total_hours overtime_hours status shift_type note permit_id scheduled_end',
  shift_setting: 'shift_start shift_end grace_minutes updated_at',
  overtime_permit: 'permit_id user_id work_date start_time end_time grace_minutes note dtr_id created_by',
};
const MONEY_FIELDS = new Set(['base_price', 'current_price', 'unit_price_at_sale', 'subtotal', 'discount_amount',
  'total_amount', 'amount', 'refund_amount', 'hourly_rate']);
// Internal keys are proven by the subject chip; they are not shown in the change list.
const INTERNAL = new Set(['log_id', 'product_id', 'user_id', 'sale_id', 'item_id', 'sale_item_id', 'dtr_id',
  'permit_id', 'audit_id', 'category_id', 'discount_id', 'image_id', 'sort_order', 'quantity_refunded', 'created_by']);
const STOCK_KINDS = { in: 'Stock in', out: 'Stock out', adjust: 'Stock count' };
// Already stated in the summary line, so it is not repeated in the proof list.
const SUMMARY_FIELDS = new Set(['transaction_type']);

const peso = (value) => `\u20b1${Number(value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

function displayValue(key, raw) {
  if (raw === null || raw === undefined) return '—';
  if (typeof raw === 'boolean') return raw ? 'Yes' : 'No';
  if (key === 'user_type') return ROLES[raw] || String(raw);
  if (key === 'transaction_type') return STOCK_KINDS[String(raw).toLowerCase()] || String(raw);
  if (MONEY_FIELDS.has(key)) return Number.isFinite(Number(raw)) ? peso(raw) : String(raw);
  if (typeof raw === 'object') return '[Structured value]';
  const text = String(raw);
  if (text.length >= 19 && text[4] === '-' && text[10] === 'T') {   // ISO timestamp from JSONB
    const parsed = new Date(`${text.slice(0, 19)}+08:00`);
    if (!Number.isNaN(parsed.getTime())) return strftime(parsed, '%b %d, %Y · %I:%M %p');
  }
  return ['order_status', 'shift_type'].includes(key) ? text.replaceAll('_', ' ') : text;
}

function snapshot(raw) {
  if (raw === null || raw === undefined) return {};
  let value = raw;
  if (typeof value === 'string') {
    try { value = JSON.parse(value); } catch { return {}; }
  }
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
  const out = {};
  for (const [key, entry] of Object.entries(value)) out[key.toLowerCase()] = entry;
  return out;
}

function readable(rows, staff) {
  const out = [];
  for (const row of rows) {
    const entity = String(row.entity).toLowerCase();
    const action = String(row.action).toUpperCase();
    const before = snapshot(row.before_data);
    const after = snapshot(row.after_data);
    let changes = [];
    for (const key of (FIELDS[entity] || '').split(/\s+/).filter(Boolean)) {
      if (INTERNAL.has(key) || SUMMARY_FIELDS.has(key) || (!(key in before) && !(key in after))) continue;
      if (action === 'UPDATE' && before[key] === after[key]) continue;
      if (action !== 'UPDATE' && before[key] === undefined && after[key] === undefined) continue;
      changes.push({
        field: key.replaceAll('_', ' ').replace(/^./, (char) => char.toUpperCase()),
        before: displayValue(key, before[key]),
        after: displayValue(key, after[key]),
      });
    }
    changes = changes.slice(0, 10);

    const member = staff[row.actor] || {};
    const role = ROLES[row.actor_role] || row.actor_role
      || member.role || (row.actor === 'system' ? 'System' : 'Unavailable');
    const verb = ACTIONS[action] || action.toLowerCase();
    const noun = ENTITIES[entity] || entity.replaceAll('_', ' ');
    let details = `${noun.charAt(0).toUpperCase()}${noun.slice(1)} ${verb}`;
    if (entity === 'sales') details = { INSERT: 'Receipt created', UPDATE: 'Order updated', DELETE: 'Sale deleted' }[action] || details;
    if (entity === 'product' && before.current_stock !== after.current_stock
      && 'current_stock' in before && 'current_stock' in after) {
      details = `Stock changed: ${before.current_stock} → ${after.current_stock}`;
      if (after.sale_id) details += ` · Receipt #${after.sale_id}`;
    }
    if (entity === 'inventory_logs') {
      const kind = STOCK_KINDS[String(after.transaction_type || '').toLowerCase()] || 'Stock movement';
      const quantity = after.quantity_changed;
      details = kind + (quantity !== null && quantity !== undefined && quantity !== ''
        ? ` · ${quantity} unit${Number(quantity) === 1 ? '' : 's'}` : '');
      if (after.sale_id) details += ` · Receipt #${after.sale_id}`;
    }
    if (entity === 'sale_item' && after.sale_id) {
      details = `Item sold · Receipt #${after.sale_id} · Quantity ${after.quantity ?? '—'} · Unit price ${displayValue('unit_price_at_sale', after.unit_price_at_sale)}`;
    }
    if (entity === 'users' && action === 'UPDATE' && !changes.length) details = 'Account security updated';

    out.push({
      audit_id: row.audit_id,
      time: row.occurred_at,
      actor: row.actor,
      name: row.actor_name || member.name || row.actor,
      approved_by: row.approved_by,
      details,
      subject: subject(entity, Object.keys(after).length ? after : before),
      changes,
      security_only: entity === 'management_pin' || details === 'Account security updated',
      badge: BADGES[action] || '',
      role,
    });
  }
  return out;
}

export default function register(router) {
  router.get('/admin/audit', 'audit.index', roleRequired('AD'), async (req, res) => {
    const today = shopDate(shopNow());
    let start = String(req.query.start || '');
    let end = String(req.query.end || '');
    const sixDaysAgo = shopDate(new Date(shopNow().getTime() - 6 * 86400000));
    if (!/^\d{4}-\d{2}-\d{2}$/.test(start) || !/^\d{4}-\d{2}-\d{2}$/.test(end) || end < start) {
      if (req.query.start || req.query.end) flash(req, 'error', 'Choose a valid date range.');
      start = sixDaysAgo;
      end = today;
    }
    const page = Math.max(1, Number(req.query.page) || 1);
    const actor = String(req.query.actor || '').trim().slice(0, 100);
    const entity = String(req.query.entity || '').trim().slice(0, 60);
    const action = String(req.query.action || '').trim();

    let rows = [];
    try {
      rows = await db.callFunction('fn_audit_logs', start, end, actor || null, entity || null, action || null, (page - 1) * 50);
    } catch (error) {
      flash(req, 'error', error.message);
    }
    let staff = {};
    try {
      staff = Object.fromEntries((await db.callFunction('fn_list_staff')).map((member) => [
        member.username,
        {
          role: ROLES[member.user_type] || member.user_type,
          name: `${member.first_name || ''} ${member.last_name || ''}`.trim(),
        },
      ]));
    } catch { /* roles stay unknown */ }

    return renderPage(req, res, 'audit.html', {
      rows: readable(rows.slice(0, 50), staff),
      more: rows.length > 50,
      page,
      entities: ENTITIES,
      filters: { start, end, actor, entity, action },
    });
  });
}
