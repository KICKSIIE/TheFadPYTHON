"""Refunds and refund report (admin). Owner: Po (REFUND). Uses your fn_refund_report."""
from datetime import date, timedelta

from flask import (Blueprint, abort, flash, redirect, render_template,
                   request, session, url_for)

import db
from auth.decorators import role_required
from utils import to_int

bp = Blueprint("refunds", __name__, url_prefix="/admin/refunds")


@bp.route("/")
@role_required("AD")
def index():
    today = date.today()
    try:
        start = date.fromisoformat(request.args.get("start") or (today - timedelta(days=30)).isoformat())
        end = date.fromisoformat(request.args.get("end") or today.isoformat())
    except ValueError:
        flash("Enter dates as year-month-day.", "error")
        start, end = today - timedelta(days=30), today
    try:
        report = db.call_function("fn_refund_report", start, end)
        refunds = db.call_function("fn_list_refunds", start, end)
    except db.DbError as exc:
        flash(str(exc), "error")
        report, refunds = [], []
    return render_template("admin/refunds.html", report=report, refunds=refunds, start=start, end=end)


@bp.route("/find")
@role_required("AD")
def find():
    try:
        sale_id = to_int(request.args.get("sale_id"), "Order number")
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("refunds.index"))
    return redirect(url_for("refunds.sale", sale_id=sale_id))


@bp.route("/sale/<int:sale_id>", methods=["GET", "POST"])
@role_required("AD")
def sale(sale_id):
    if request.method == "POST":
        f = request.form
        try:
            result = db.call_procedure(
                "sp_process_refund", session["user_id"], sale_id, to_int(f.get("item_id"), "Item"),
                to_int(f.get("quantity"), "Quantity"), f.get("reason", "").strip(), f.get("method"), None)
            flash(f"Refund #{result['p_refund_id']} recorded and the stock was returned.", "success")
        except (ValueError, db.DbError) as exc:
            flash(str(exc), "error")
        return redirect(url_for("refunds.sale", sale_id=sale_id))
    try:
        order = db.call_function("fn_get_sale", sale_id, one=True)
        items = db.call_function("fn_sale_items", sale_id)
    except db.DbError as exc:
        flash(str(exc), "error")
        return redirect(url_for("refunds.index"))
    if order is None:
        flash(f"No order number {sale_id}.", "error")
        return redirect(url_for("refunds.index"))
    return render_template("admin/refund_sale.html", sale=order, items=items,
                           can_refund=order["order_status"] in ("Completed", "Partially_Refunded"))
