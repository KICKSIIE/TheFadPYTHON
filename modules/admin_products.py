"""Products and categories (admin). Owner: Batiola (PRODUCT, CATEGORY).

Each color/size combination is its own product row with its own stock, so inventory, POS,
promos and refunds need no changes. Name, price and description are shared across sizes when you tick
"apply to all sizes"; photos are shared through the product_photo link table.
"""
from flask import (Blueprint, abort, flash, redirect, render_template,
                   request, url_for)

import db
from auth.decorators import role_required
from utils import group_products, read_photos, size_key, to_decimal, to_int

bp = Blueprint("admin_products", __name__, url_prefix="/admin/products")


def _categories():
    try:
        return db.call_function("fn_list_categories")
    except db.DbError as exc:
        flash(str(exc), "error")
        return []


@bp.route("/")
@role_required("AD")
def index():
    q = request.args.get("q", "").strip()
    category = request.args.get("category", type=int)
    show_inactive = request.args.get("inactive") == "1"
    try:
        products = db.call_function("fn_list_products", q or None, category, show_inactive)
    except db.DbError as exc:
        flash(str(exc), "error")
        products = []
    variants_view = request.args.get("variants") == "1"
    return render_template("admin/products.html", products=products, cards=group_products(products),
                           variants_view=variants_view, categories=_categories(),
                           q=q, category=category, show_inactive=show_inactive)


def _read_form():
    f = request.form
    return {
        "name": f.get("product_name", "").strip(),
        "price": to_decimal(f.get("base_price"), "Price"),
        "category_id": to_int(f.get("category_id"), "Category"),
        "description": f.get("description", "").strip(),
    }


@bp.route("/new", methods=["GET", "POST"])
@role_required("AD")
def new():
    categories = _categories()
    if request.method == "POST":
        try:
            v = _read_form()
            sizes = request.form.get("sizes", "").strip()
            colors = request.form.get("colors", "").strip()
            mimes, datas = read_photos(request.files.getlist("photos"))
            db.call_procedure("sp_create_product", v["name"], v["price"], v["category_id"],
                              v["description"], sizes, colors, mimes or None, datas or None, None)
        except (ValueError, db.DbError) as exc:
            flash(str(exc), "error")
            return render_template("admin/product_form.html", product=request.form,
                                   categories=categories, editing=False), 400
        flash(f"Added {v['name']}. Stock starts at 0; add stock from Inventory.", "success")
        return redirect(url_for("admin_products.index"))
    return render_template("admin/product_form.html", product={}, categories=categories, editing=False)


@bp.route("/<int:product_id>/edit", methods=["GET", "POST"])
@role_required("AD")
def edit(product_id):
    categories = _categories()
    if request.method == "POST":
        try:
            v = _read_form()
            db.call_procedure("sp_update_product", product_id, v["name"], v["price"], v["category_id"],
                              request.form.get("size", "").strip(), request.form.get("color", "").strip(),
                              v["description"], request.form.get("apply_all") == "1")
            flash(f"Saved {v['name']}.", "success")
            return redirect(url_for("admin_products.index"))
        except (ValueError, db.DbError) as exc:
            flash(str(exc), "error")
            return _edit_page(product_id, categories, request.form, 400)
    return _edit_page(product_id, categories, None, 200)


def _edit_page(product_id, categories, form_values, status):
    try:
        current = db.call_function("fn_get_product", product_id, one=True)
        variants = db.call_function("fn_list_variants", product_id)
    except db.DbError as exc:
        flash(str(exc), "error")
        return redirect(url_for("admin_products.index"))
    if current is None:
        abort(404)
    variants = sorted(variants, key=lambda v: ((v["color"] or ""), size_key(v["size"])))
    return render_template("admin/product_form.html", product=form_values or current, current=current,
                           categories=categories, editing=True, product_id=product_id, variants=variants), status


# -------------------------------------------------------------------- photos
@bp.route("/<int:product_id>/photos")
@role_required("AD")
def photos(product_id):
    try:
        current = db.call_function("fn_get_product", product_id, one=True)
        gallery = db.call_function("fn_list_product_photos", product_id)
        variants = db.call_function("fn_list_variants", product_id)
    except db.DbError as exc:
        flash(str(exc), "error")
        return redirect(url_for("admin_products.index"))
    if current is None:
        abort(404)
    urls = [url_for("catalog.product_image", image_id=g["image_id"]) for g in gallery]
    colors, seen = [], set()
    for v in variants:
        name = v["color"] or ""
        if name and name not in seen:
            seen.add(name)
            colors.append({"name": name, "first_id": v["product_id"]})
    same_color = [v for v in variants if (v["color"] or "") == (current["color"] or "")]
    return render_template("admin/product_photos.html", current=current, gallery=gallery, photo_urls=urls,
                           product_id=product_id, colors=colors, many_sizes=len(same_color) > 1)


@bp.route("/<int:product_id>/photos/upload", methods=["POST"])
@role_required("AD")
def upload_photos(product_id):
    apply_all = request.form.get("apply_all") == "1"
    try:
        mimes, datas = read_photos(request.files.getlist("photos"))
        if not datas:
            raise ValueError("Choose at least one photo to upload.")
        added = 0
        for mime, data in zip(mimes, datas):
            db.call_procedure("sp_add_product_photo", product_id, mime, data, apply_all, None)
            added += 1
        flash(f"Added {added} photo{'' if added == 1 else 's'}.", "success")
    except (ValueError, db.DbError) as exc:
        flash(str(exc), "error")
    return redirect(url_for("admin_products.photos", product_id=product_id))


@bp.route("/<int:product_id>/photos/<int:image_id>/remove", methods=["POST"])
@role_required("AD")
def remove_photo(product_id, image_id):
    try:
        db.call_procedure("sp_remove_product_photo", product_id, image_id, request.form.get("apply_all") == "1")
        flash("Photo removed.", "success")
    except db.DbError as exc:
        flash(str(exc), "error")
    return redirect(url_for("admin_products.photos", product_id=product_id))


@bp.route("/<int:product_id>/photos/<int:image_id>/cover", methods=["POST"])
@role_required("AD")
def cover_photo(product_id, image_id):
    try:
        db.call_procedure("sp_set_cover_photo", product_id, image_id, request.form.get("apply_all") == "1")
        flash("Cover photo updated.", "success")
    except db.DbError as exc:
        flash(str(exc), "error")
    return redirect(url_for("admin_products.photos", product_id=product_id))


@bp.route("/<int:product_id>/add-variant", methods=["POST"])
@role_required("AD")
def add_variant(product_id):
    try:
        result = db.call_procedure("sp_add_variant", product_id, request.form.get("size", "").strip(),
                                   request.form.get("color", "").strip(), None)
        flash("Variant added with stock 0. Add stock from Inventory.", "success")
        return redirect(url_for("admin_products.edit", product_id=result["p_new_id"]))
    except db.DbError as exc:
        flash(str(exc), "error")
        return redirect(url_for("admin_products.edit", product_id=product_id))


@bp.route("/<int:product_id>/active", methods=["POST"])
@role_required("AD")
def set_active(product_id):
    active = request.form.get("active") == "1"
    try:
        db.call_procedure("sp_set_product_active", product_id, active)
        flash("Product reactivated." if active else "Product deactivated. It no longer shows on the catalog or POS.", "success")
    except db.DbError as exc:
        flash(str(exc), "error")
    return redirect(request.referrer or url_for("admin_products.index"))


# ---------------------------------------------------------------- categories
@bp.route("/categories", methods=["GET", "POST"])
@role_required("AD")
def categories():
    if request.method == "POST":
        try:
            name = request.form.get("category_name", "").strip()
            order = to_int(request.form.get("display_order") or "0", "Display order")
            db.call_procedure("sp_create_category", name, order, None)
            flash(f"Added category {name}.", "success")
        except (ValueError, db.DbError) as exc:
            flash(str(exc), "error")
        return redirect(url_for("admin_products.categories"))
    return render_template("admin/categories.html", categories=_categories())


@bp.route("/categories/<int:category_id>", methods=["POST"])
@role_required("AD")
def update_category(category_id):
    try:
        name = request.form.get("category_name", "").strip()
        order = to_int(request.form.get("display_order") or "0", "Display order")
        db.call_procedure("sp_update_category", category_id, name, order)
        flash("Category saved.", "success")
    except (ValueError, db.DbError) as exc:
        flash(str(exc), "error")
    return redirect(url_for("admin_products.categories"))


@bp.route("/categories/<int:category_id>/delete", methods=["POST"])
@role_required("AD")
def delete_category(category_id):
    try:
        db.call_procedure("sp_delete_category", category_id)
        flash("Category deleted.", "success")
    except db.DbError as exc:
        flash(str(exc), "error")
    return redirect(url_for("admin_products.categories"))
