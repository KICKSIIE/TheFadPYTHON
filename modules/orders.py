"""Order list, receipt and delivery status. Owner: Pono (SALES, SALE_ITEM)."""
from datetime import date

from flask import (Blueprint, abort, flash, redirect, render_template,
                   request, session, url_for)

import db
from auth.decorators import login_required

bp = Blueprint("orders", __name__, url_prefix="/orders")
STATUSES = ["Pending", "Out_for_Delivery", "Completed", "Cancelled", "Partially_Refunded", "Refunded"]


@bp.route("/")
@login_required
def index():
    today = date.today()
    try:
        start = date.fromisoformat(request.args.get("start") or today.isoformat())
        end = date.fromisoformat(request.args.get("end") or today.isoformat())
    except ValueError:
        flash("Enter dates as year-month-day.", "error")
        start = end = today
    status = request.args.get("status") or None
    try:
        rows = db.call_function("fn_list_sales", start, end, status)
    except db.DbError as exc:
        flash(str(exc), "error")
        rows = []
    total = sum(r["total_amount"] for r in rows if r["order_status"] not in ("Cancelled", "Refunded"))
    return render_template("orders.html", rows=rows, start=start, end=end, status=status,
                           statuses=STATUSES, total=total)


@bp.route("/<int:sale_id>")
@login_required
def detail(sale_id):
    try:
        sale = db.call_function("fn_get_sale", sale_id, one=True)
        items = db.call_function("fn_sale_items", sale_id)
    except db.DbError as exc:
        flash(str(exc), "error")
        return redirect(url_for("orders.index"))
    if sale is None:
        abort(404)
    return render_template("order_detail.html", sale=sale, items=items)


@bp.route("/<int:sale_id>/status", methods=["POST"])
@login_required
def set_status(sale_id):
    f = request.form
    try:
        db.call_procedure("sp_update_order_status", session["user_id"], sale_id, f.get("new_status"),
                          f.get("rider_service", "").strip(), f.get("rider_contact", "").strip())
        flash("Order updated.", "success")
    except db.DbError as exc:
        flash(str(exc), "error")
    return redirect(url_for("orders.detail", sale_id=sale_id))
