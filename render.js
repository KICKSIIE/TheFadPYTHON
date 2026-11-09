/** Builds the template context (user, navigation, store details, flashes) for every page. */
import { config, LOW_STOCK } from './config.js';
import { csrfToken } from './csrf.js';
import { takeFlashes } from './flash.js';
import * as menu from './menu.js';
import { urlFor } from './urls.js';

export function renderPage(req, res, view, locals = {}, status = 200) {
  const userType = req.session.user_type;
  let user = null;
  if (req.session.user_id) {
    const name = String(req.session.display_name || '').trim() || req.session.username || 'Staff';
    user = {
      name,
      first_name: name.split(/\s+/)[0],
      username: req.session.username,
      role: menu.ROLE_LABELS[userType] || userType,
    };
  }

  let nav = user ? menu.itemsFor(userType) : [];
  let groups = user ? menu.groupsFor(userType) : [];
  const locked = Boolean(user && req.staffAccess && !req.staffAccess.allowed);
  if (locked) {
    nav = nav.filter((item) => item.endpoint === 'attendance.index');
    groups = [{ name: 'Team', items: nav }];
  }

  const place = `${config.store.latitude},${config.store.longitude}`;
  const store = {
    name: config.store.name,
    tagline: config.store.tagline,
    facebook: config.store.facebook,
    facebook_short: config.store.facebook.replace(/^https?:\/\//, '').replace(/\/$/, ''),
    plus_code: config.store.plusCode,
    address: config.store.address,
    map_embed: `https://www.google.com/maps?q=${encodeURIComponent(place)}&z=17&output=embed`,
    map_open: config.store.mapUrl,
    directions: `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(place)}`,
  };

  const context = {
    ...locals,
    store,
    csrf_token: () => csrfToken(req),
    current_user: user,
    nav_items: nav,
    nav_groups: groups,
    low_stock_limit: LOW_STOCK,
    staff_access: req.staffAccess || null,
    flashes: takeFlashes(req),
    session: req.session,
    request: {
      path: req.path,
      blueprint: req.endpoint ? req.endpoint.split('.')[0] : '',
      endpoint: req.endpoint || '',
      args: req.query,
    },
    config: { NAV_UNLOCKED: config.navUnlocked },
    url_for: urlFor,
  };
  return res.status(status).render(view, context);
}
