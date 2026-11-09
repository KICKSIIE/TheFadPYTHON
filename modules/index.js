import adminProducts from './admin_products.js';
import adminPromos from './admin_promos.js';
import adminStaff from './admin_staff.js';
import attendance from './attendance.js';
import audit from './audit.js';
import auth from './auth.js';
import catalog from './catalog.js';
import dashboard from './dashboard.js';
import inventory from './inventory.js';
import orders from './orders.js';
import pos from './pos.js';
import promos from './promos.js';
import refunds from './refunds.js';

const MODULES = [
  auth, catalog, dashboard, pos, orders, inventory, attendance, promos,
  adminProducts, adminStaff, adminPromos, refunds, audit,
];

export function registerAll(router) {
  for (const register of MODULES) register(router);
}
