import * as db from '../db.js';
import { flash } from '../flash.js';
import { renderPage } from '../render.js';
import { loginRequired } from './auth.js';
import { lowStockDefault } from '../rules.js';

export default function register(router) {
  router.get('/dashboard', 'dashboard.index', loginRequired, async (req, res) => {
    let summary = null;
    let days = [];
    let top = [];
    let low = lowStockDefault();
    try {
      await db.callProcedure('sp_expire_promos', null);
      low = lowStockDefault();
      summary = await db.callFunctionOne('fn_dashboard_summary', low);
      days = await db.callFunction('fn_sales_by_day', 7);
      top = await db.callFunction('fn_top_products', 7, 5);
    } catch (error) {
      flash(req, 'error', error.message);
    }
    const peak = Math.max(0, ...days.map((day) => Number(day.total_sales))) || 1;
    const bars = days.map((day) => ({
      day: day.sale_day,
      total: day.total_sales,
      orders: day.order_count,
      pct: Math.round((Number(day.total_sales) / peak) * 100),
    }));
    const weekTotal = days.reduce((sum, day) => sum + Number(day.total_sales), 0);
    return renderPage(req, res, 'dashboard.html', { low, s: summary, bars, top, week_total: weekTotal });
  });
}
