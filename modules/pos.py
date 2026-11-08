"""POS checkout: build a cart in the session, then save the sale. Owner: Pono (SALES, SALE_ITEM)."""
import json

from flask import (Blueprint, flash, redirect, render_template, request,
                   session, url_for)

import db
from auth.decorators import login_required
from utils import to_int

bp = Blueprint("pos", __name__, url_prefix="/pos")


def _cart():
    return session.get("cart", {})


def _catalog():
    """Active products by id. Prices here are only for display; the database prices the sale."""
    return {p["product_id"]: p for p in db.call_function("fn_list_products", None, None, False)}


@bp.route("/")
@login_required
def index():
    q = request.args.get("q", "").strip().lower()
    category = request.args.get("category", type=int)
    try:
        catalog = _catalog()
    except db.DbError as exc:
        flash(str(exc), "error")
        catalog = {}

    lines, total = [], 0
    for pid, qty in _cart().items():
        p = catalog.get(int(pid))
        if p is None:
            continue
        line_total = p["current_price"] * qty
        total += line_total
        lines.append({"product": p, "qty": qty, "line_total": line_total, "short": qty > p["current_stock"]})

    shown = [p for p in catalog.values()
             if (not q or q in p["display_name"].lower()) and (category is None or p["category_id"] == category)]
    shown.sort(key=lambda p: p["current_stock"] <= 0)
    categories = sorted({(p["category_id"], p["category_name"]) for p in catalog.values()}, key=lambda c: c[1])
    return render_template("pos.html", products=shown, lines=lines, total=total,
                           categories=categories, q=q, category=category)


def _return_to_catalog():
    return redirect(url_for("pos.index", q=request.form.get("q", ""), category=request.form.get("category", "")))


@bp.route("/cart/add", methods=["POST"])
@login_required
def add():
    try:
        pid = to_int(request.form.get("product_id"), "Product")
        qty = max(1, to_int(request.form.get("quantity") or "1", "Quantity"))
        product = _catalog().get(pid)
    except (ValueError, db.DbError) as exc:
        flash(str(exc), "error")
        return _return_to_catalog()
    if product is None or product["current_stock"] <= 0:
        flash("That product is out of stock.", "error")
        return _return_to_catalog()
    cart = _cart()
    wanted = cart.get(str(pid), 0) + qty
    if wanted > product["current_stock"]:
        wanted = product["current_stock"]
        flash(f"Only {wanted} of {product['display_name']} in stock. Cart set to {wanted}.", "info")
    cart[str(pid)] = wanted
    session["cart"] = cart
    return _return_to_catalog()


@bp.route("/cart/update", methods=["POST"])
@login_required
def update():
    try:
        pid = to_int(request.form.get("product_id"), "Product")
        cart = _cart()
        if request.form.get("delta"):
            qty = cart.get(str(pid), 0) + to_int(request.form.get("delta"), "Change")
        else:
            qty = to_int(request.form.get("quantity"), "Quantity")
        product = _catalog().get(pid)
    except (ValueError, db.DbError) as exc:
        flash(str(exc), "error")
        return _return_to_catalog()
    if qty <= 0 or product is None:
        cart.pop(str(pid), None)
    else:
        cart[str(pid)] = min(qty, product["current_stock"])
    session["cart"] = cart
    return _return_to_catalog()


@bp.route("/cart/clear", methods=["POST"])
@login_required
def clear():
    session.pop("cart", None)
    flash("Cart cleared.", "info")
    return _return_to_catalog()


@bp.route("/checkout", methods=["POST"])
@login_required
def checkout():
    cart = _cart()
    if not cart:
        flash("Add at least one item to the cart.", "error")
        return redirect(url_for("pos.index"))
    f = request.form
    items = [{"product_id": int(pid), "quantity": qty} for pid, qty in cart.items()]
    try:
        result = db.call_procedure(
            "sp_create_sale", session["user_id"], f.get("fulfillment_type"), f.get("payment_method"),
            f.get("customer_name", "").strip(), f.get("customer_contact", "").strip(),
            f.get("delivery_address", "").strip(), json.dumps(items), None)
    except db.DbError as exc:
        flash(str(exc), "error")
        return redirect(url_for("pos.index"))
    session.pop("cart", None)
    flash("Sale saved.", "success")
    return redirect(url_for("orders.detail", sale_id=result["p_sale_id"]))
