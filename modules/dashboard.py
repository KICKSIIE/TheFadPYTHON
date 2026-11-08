from flask import Blueprint, flash, render_template, session

import db
from auth.decorators import login_required
from rules import low_stock_default

bp = Blueprint("dashboard", __name__)


@bp.route("/dashboard")
@login_required
def index():
    summary, days, top, low = None, [], [], low_stock_default()
    try:
        db.call_procedure("sp_expire_promos", None)  # reset prices of promos that ended
        low = low_stock_default()
        summary = db.call_function("fn_dashboard_summary", low, one=True)
        days = db.call_function("fn_sales_by_day", 7)
        top = db.call_function("fn_top_products", 7, 5)
    except db.DbError as exc:
        flash(str(exc), "error")
    peak = max((float(d["total_sales"]) for d in days), default=0) or 1
    bars = [{"day": d["sale_day"], "total": d["total_sales"], "orders": d["order_count"],
             "pct": round(float(d["total_sales"]) / peak * 100)} for d in days]
    return render_template("dashboard.html", low=low, s=summary, bars=bars, top=top, week_total=sum(d["total_sales"] for d in days))
