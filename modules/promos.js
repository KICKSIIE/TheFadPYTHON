/** Promos list for staff (read only). */
import * as db from '../db.js';
import { flash } from '../flash.js';
import { renderPage } from '../render.js';
import { loginRequired } from './auth.js';

export default function register(router) {
  router.get('/promos', 'promos.index', loginRequired, async (req, res) => {
    let rows = [];
    try {
      rows = (await db.callFunction('fn_list_discounts')).filter((row) => row.status === 'Active');
    } catch (error) {
      flash(req, 'error', error.message);
    }
    return renderPage(req, res, 'promos.html', { rows });
  });
}
