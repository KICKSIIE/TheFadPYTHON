"""Promo manager (admin). Owner: Po (DISCOUNT). Uses sp_create_discount / sp_update_discount."""
from datetime import date

from flask import (Blueprint, abort, flash, redirect, render_template,
                   request, url_for)

import db
from auth.decorators import role_required
from utils import to_int

bp = Blueprint("admin_promos", __name__, url_prefix="/admin/promos")


def _styles():
    """One entry per product (all its colors and sizes), for the "apply to" dropdown."""
    seen, out = set(), []
    for r in db.call_function("fn_list_products", None, None, False):
        key = (r["category_name"], r["product_name"])
        if key not in seen:
            seen.add(key)
            out.append({"product_id": r["product_id"], "name": r["product_name"]})
    return out


def _date(value, label):
    try:
        return date.fromisoformat((value or "").strip())
    except ValueError:
        raise ValueError(f"{label} must be a valid date.")


@bp.route("/")
@role_required("AD")
def index():
    try:
        db.call_procedure("sp_expire_promos", None)
        rows = db.call_function("fn_list_discounts")
        for row in rows:
            styles = db.call_function("fn_discount_product_names", row["discount_id"])
            row["product_names"] = [s["product_name"] for s in styles]
            row["variant_count"] = sum(s["variants"] for s in styles)
    except db.DbError as exc:
        flash(str(exc), "error")
        rows = []
    return render_template("admin/promos.html", rows=rows)


def _linked(rows):
    """Group promo rows by product so a 12-variant jacket shows as one line."""
    grouped = {}
    for r in rows:
        g = grouped.setdefault(r["product_name"], {"name": r["product_name"], "product_id": r["product_id"],
                                                   "variants": 0, "base": r["base_price"], "promo": r["current_price"]})
        g["variants"] += 1
    return list(grouped.values())


@bp.route("/new", methods=["GET", "POST"])
@role_required("AD")
def new():
    try:
        products = _styles()
    except db.DbError as exc:
        flash(str(exc), "error")
        products = []
    if request.method == "POST":
        f = request.form
        try:
            name = f.get("discount_name", "").strip()
            pct = to_int(f.get("discount_percentage"), "Discount percent")
            start, end = _date(f.get("start_date"), "Start date"), _date(f.get("end_date"), "End date")
            scope = f.get("scope", "NONE")
            product_id = to_int(f.get("product_id"), "Product") if scope == "PRODUCT" else None
            created = db.call_procedure("sp_create_discount", name, pct, start, end, "NONE", None, None)
            flash(f"Created promo {name}.", "success")
            if scope in ("PRODUCT", "STORE"):
                try:   # applied separately so a promo covers every color and size of a product
                    applied = db.call_procedure("sp_apply_discount", created["p_discount_id"], scope, product_id, None)
                    flash(f"Applied to {applied['p_products_updated']} item(s).", "success")
                except db.DbError as exc:
                    flash(f"The promo was created but not applied: {exc}", "error")
                    return redirect(url_for("admin_promos.edit", discount_id=created["p_discount_id"]))
            return redirect(url_for("admin_promos.index"))
        except (ValueError, db.DbError) as exc:
            flash(str(exc), "error")
            return render_template("admin/promo_form.html", promo=f, products=products,
                                   editing=False, today=date.today()), 400
    return render_template("admin/promo_form.html", promo={}, products=products, editing=False, today=date.today())


@bp.route("/<int:discount_id>", methods=["GET", "POST"])
@role_required("AD")
def edit(discount_id):
    if request.method == "POST":
        f = request.form
        try:
            name = f.get("discount_name", "").strip()
            pct = to_int(f.get("discount_percentage"), "Discount percent")
            start, end = _date(f.get("start_date"), "Start date"), _date(f.get("end_date"), "End date")
            db.call_procedure("sp_update_discount", discount_id, name, pct, start, end, False, None)
            flash("Promo saved. Prices on linked products were updated.", "success")
        except (ValueError, db.DbError) as exc:
            flash(str(exc), "error")
        return redirect(url_for("admin_promos.edit", discount_id=discount_id))
    try:
        promo = db.call_function("fn_get_discount", discount_id, one=True)
        linked = _linked(db.call_function("fn_discount_products", discount_id))
        products = _styles()
    except db.DbError as exc:
        flash(str(exc), "error")
        return redirect(url_for("admin_promos.index"))
    if promo is None:
        abort(404)
    return render_template("admin/promo_form.html", promo=promo, linked=linked, products=products,
                           editing=True, discount_id=discount_id, today=date.today())


@bp.route("/<int:discount_id>/end", methods=["POST"])
@role_required("AD")
def end_now(discount_id):
    try:
        db.call_procedure("sp_update_discount", discount_id, None, None, None, None, True, None)
        flash("Promo ended. Prices are back to normal.", "success")
    except db.DbError as exc:
        flash(str(exc), "error")
    return redirect(url_for("admin_promos.index"))


@bp.route("/<int:discount_id>/apply", methods=["POST"])
@role_required("AD")
def apply(discount_id):
    scope = request.form.get("scope", "")
    try:
        product_id = to_int(request.form.get("product_id"), "Product") if scope == "PRODUCT" else None
        result = db.call_procedure("sp_apply_discount", discount_id, scope, product_id, None)
        flash(f"Promo applied to {result['p_products_updated']} product(s).", "success")
    except (ValueError, db.DbError) as exc:
        flash(str(exc), "error")
    return redirect(url_for("admin_promos.edit", discount_id=discount_id))


@bp.route("/unlink/<int:product_id>", methods=["POST"])
@role_required("AD")
def unlink(product_id):
    try:
        db.call_procedure("sp_clear_product_discount", product_id)
        flash("Promo removed from the product.", "success")
    except db.DbError as exc:
        flash(str(exc), "error")
    return redirect(request.referrer or url_for("admin_promos.index"))


@bp.post("/<int:discount_id>/delete")
@role_required("AD")
def delete_unused(discount_id):
    try:
        db.call_procedure("sp_delete_unused_discount", discount_id)
        flash("Unused promo deleted.", "success")
    except db.DbError as exc:
        flash(str(exc), "error")
    return redirect(url_for("admin_promos.index"))
