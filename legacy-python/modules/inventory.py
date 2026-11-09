"""Stock levels and movements. Owner: Rivera (INVENTORY_LOGS)."""
from flask import (Blueprint, abort, flash, redirect, render_template,
                   request, session, url_for)

import db
from auth.decorators import login_required
from rules import low_stock_default
from utils import to_int

bp = Blueprint("inventory", __name__, url_prefix="/inventory")


@bp.route("/")
@login_required
def index():
    q = request.args.get("q", "").strip()
    low_only = request.args.get("low") == "1"
    category = request.args.get("category", "").strip()
    limit = request.args.get("max", type=int)
    if limit is None or limit < 0:
        limit = low_stock_default()
    try:
        items = db.call_function("fn_list_inventory", q or None, low_only, limit)
    except db.DbError as exc:
        flash(str(exc), "error")
        items = []
    if category:
        items = [i for i in items if i["category_name"] == category]
    items.sort(key=lambda i: (i["product_name"].casefold(), i["product_id"]))
    try:
        categories = [c["category_name"] for c in db.call_function("fn_list_categories")]
    except db.DbError:
        categories = sorted({i["category_name"] for i in items}, key=str.casefold)
    return render_template("inventory.html", items=items, q=q, low_only=low_only, limit=limit,
                           categories=categories, category=category)


@bp.route("/history")
@login_required
def history():
    try:
        rows = db.call_function("fn_inventory_history", None, 200)
    except db.DbError as exc:
        flash(str(exc), "error")
        rows = []
    return render_template("inventory_history.html", rows=rows, product=None)


@bp.route("/<int:product_id>")
@login_required
def item(product_id):
    try:
        product = db.call_function("fn_get_product", product_id, one=True)
        rows = db.call_function("fn_inventory_history", product_id, 50)
    except db.DbError as exc:
        flash(str(exc), "error")
        return redirect(url_for("inventory.index"))
    if product is None:
        abort(404)
    return render_template("inventory_item.html", product=product, rows=rows)


@bp.route("/<int:product_id>/move", methods=["POST"])
@login_required
def move(product_id):
    action = request.form.get("action")
    routine = {"in": "sp_stock_in", "out": "sp_stock_out", "adjust": "sp_adjust_stock"}.get(action)
    if routine is None:
        abort(400)
    try:
        qty = to_int(request.form.get("quantity"), "Quantity")
        result = db.call_procedure(routine, session["user_id"], product_id, qty, None)
        flash(f"Done. Stock is now {result['p_balance']}.", "success")
    except (ValueError, db.DbError) as exc:
        flash(str(exc), "error")
    return redirect(url_for("inventory.item", product_id=product_id))
