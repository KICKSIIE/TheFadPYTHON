/** One place that decides what each role sees in the staff menu, grouped into sections. */

export const ROLE_LABELS = { CA: 'Cashier', AD: 'Admin' };

// [section, label, endpoint, roles, short description]
export const MENU = [
  ['Overview', 'Dashboard', 'dashboard.index', ['CA', 'AD'], ''],
  ['Sell', 'New sale', 'pos.index', ['CA', 'AD'], 'Ring up walk-in and delivery orders.'],
  ['Sell', 'Orders', 'orders.index', ['CA', 'AD'], 'Track orders, deliveries and receipts.'],
  ['Stock', 'Inventory', 'inventory.index', ['CA', 'AD'], 'Stock in, out, counts and history.'],
  ['Stock', 'Products', 'admin_products.index', ['AD'], 'Products, colors, sizes and photos.'],
  ['Stock', 'Promos', 'promos.index', ['CA'], 'See which promos are running.'],
  ['Stock', 'Promos', 'admin_promos.index', ['AD'], 'Create, edit and end promos.'],
  ['Team', 'Attendance', 'attendance.index', ['CA', 'AD'], 'Clock in and out; admins manage schedule and overtime.'],
  ['Team', 'Staff', 'admin_staff.index', ['AD'], 'Staff accounts and roles.'],
  ['Admin', 'Refunds', 'refunds.index', ['AD'], 'Process refunds and see the refund report.'],
  ['Admin', 'Audit log', 'audit.index', ['AD'], 'Who changed what, and when.'],
];

export function itemsFor(userType) {
  return MENU
    .filter(([, , , roles]) => roles.includes(userType))
    .map(([section, label, endpoint, , desc]) => ({ section, label, endpoint, desc }));
}

/** Menu items grouped by section, in order, for the sidebar. */
export function groupsFor(userType) {
  const groups = [];
  for (const item of itemsFor(userType)) {
    if (!groups.length || groups[groups.length - 1].name !== item.section) {
      groups.push({ name: item.section, items: [] });
    }
    groups[groups.length - 1].items.push(item);
  }
  return groups;
}
