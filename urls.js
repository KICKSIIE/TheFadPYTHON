/**
 * Endpoint → URL map. Templates call url_for('orders.detail', {sale_id: 65}); extra parameters become
 * query-string values (null/undefined/'' are dropped, like Flask's url_for).
 */
const ROUTES = {
  'catalog.index': '/',
  'catalog.suggestions': '/search-suggestions',
  'catalog.product': '/product/:product_id',
  'catalog.product_image': '/media/product/:image_id',

  'auth.staff': '/staff',
  'auth.login': '/login',
  'auth.verify_otp': '/verify-otp',
  'auth.logout': '/logout',
  'auth.account': '/account',

  'dashboard.index': '/dashboard',

  'pos.index': '/pos/',
  'pos.add': '/pos/cart/add',
  'pos.update': '/pos/cart/update',
  'pos.clear': '/pos/cart/clear',
  'pos.checkout': '/pos/checkout',

  'orders.index': '/orders/',
  'orders.detail': '/orders/:sale_id',
  'orders.set_status': '/orders/:sale_id/status',

  'inventory.index': '/inventory/',
  'inventory.history': '/inventory/history',
  'inventory.item': '/inventory/:product_id',
  'inventory.move': '/inventory/:product_id/move',

  'attendance.index': '/attendance/',
  'attendance.clock_in': '/attendance/clock-in',
  'attendance.clock_out': '/attendance/clock-out',
  'attendance.overtime_in': '/attendance/overtime-in',
  'attendance.overtime_out': '/attendance/overtime-out',
  'attendance.everyone': '/attendance/everyone',
  'attendance.new_shift': '/attendance/shift',
  'attendance.edit_shift': '/attendance/shift/:dtr_id',
  'attendance.overtime': '/attendance/overtime',
  'attendance.new_overtime': '/attendance/overtime/new',
  'attendance.edit_overtime': '/attendance/overtime/:permit_id',
  'attendance.cancel_overtime': '/attendance/overtime/:permit_id/cancel',
  'attendance.schedule': '/attendance/schedule',

  'promos.index': '/promos/',

  'admin_products.index': '/admin/products/',
  'admin_products.new': '/admin/products/new',
  'admin_products.edit': '/admin/products/:product_id/edit',
  'admin_products.photos': '/admin/products/:product_id/photos',
  'admin_products.upload_photos': '/admin/products/:product_id/photos/upload',
  'admin_products.remove_photo': '/admin/products/:product_id/photos/:image_id/remove',
  'admin_products.cover_photo': '/admin/products/:product_id/photos/:image_id/cover',
  'admin_products.add_variant': '/admin/products/:product_id/add-variant',
  'admin_products.set_active': '/admin/products/:product_id/active',
  'admin_products.categories': '/admin/products/categories',
  'admin_products.update_category': '/admin/products/categories/:category_id',
  'admin_products.delete_category': '/admin/products/categories/:category_id/delete',

  'admin_staff.index': '/admin/staff/',
  'admin_staff.new': '/admin/staff/new',
  'admin_staff.edit': '/admin/staff/:user_id/edit',
  'admin_staff.set_active': '/admin/staff/:user_id/active',

  'admin_promos.index': '/admin/promos/',
  'admin_promos.new': '/admin/promos/new',
  'admin_promos.edit': '/admin/promos/:discount_id',
  'admin_promos.view': '/admin/promos/:discount_id/view',
  'admin_promos.end_now': '/admin/promos/:discount_id/end',
  'admin_promos.apply': '/admin/promos/:discount_id/apply',
  'admin_promos.unlink': '/admin/promos/unlink/:product_id',
  'admin_promos.delete_unused': '/admin/promos/:discount_id/delete',

  'refunds.index': '/admin/refunds/',
  'refunds.find': '/admin/refunds/find',
  'refunds.sale': '/admin/refunds/sale/:sale_id',

  'audit.index': '/admin/audit/',
};

/** Express route paths use the same pattern, with numeric params constrained. */
export function routePath(name) {
  return ROUTES[name];
}

export function urlFor(name, params = {}) {
  if (name === 'static') return `/static/${params.filename ?? ''}`;
  const pattern = ROUTES[name];
  if (!pattern) throw new Error(`Unknown endpoint: ${name}`);
  const used = new Set();
  const path = pattern.replace(/:([a-z_]+)/g, (match, key) => {
    used.add(key);
    const value = params[key];
    if (value === undefined || value === null || value === '') {
      throw new Error(`Missing parameter "${key}" for ${name}`);
    }
    return encodeURIComponent(String(value));
  });
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (used.has(key) || value === undefined || value === null || value === '') continue;
    query.append(key, String(value));
  }
  const suffix = query.toString();
  return suffix ? `${path}?${suffix}` : path;
}
