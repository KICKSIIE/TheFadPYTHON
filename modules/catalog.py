"""Public shop: catalog with search, filters and sort, product pages, photos. Owner: Batiola."""
from itertools import groupby

from flask import (Blueprint, Response, abort, flash, redirect, render_template,
                   request, url_for)

import db
from utils import color_hex, group_products, size_key, stock_status

bp = Blueprint("catalog", __name__)

SORTS = {
    "featured": ("Featured", None),
    "newest": ("Newest", lambda c: -c["newest"]),
    "price_low": ("Price: low to high", lambda c: c["price_min"]),
    "price_high": ("Price: high to low", lambda c: -c["price_min"]),
    "name": ("Name A to Z", lambda c: c["name"].lower()),
}


@bp.route("/")
def index():
    q = request.args.get("q", "").strip()
    category = request.args.get("category", type=int)
    in_stock = request.args.get("instock") == "1"
    sort = request.args.get("sort") if request.args.get("sort") in SORTS else "featured"
    try:
        rows = db.call_function("fn_list_products", q or None, category, False)
        categories = [c for c in db.call_function("fn_list_categories") if c["product_count"]]
    except db.DbError as exc:
        flash(str(exc), "error")
        rows, categories = [], []

    cards = group_products(rows)
    if in_stock:
        cards = [c for c in cards if c["stock"] > 0]
    key = SORTS[sort][1]
    if key:
        cards.sort(key=key)

    filtered = bool(q or category or in_stock or sort != "featured")
    sections = []
    if not filtered:
        sections = [{"name": n, "cards": list(g)} for n, g in groupby(cards, key=lambda c: c["category"])]
    return render_template("catalog.html", cards=cards, sections=sections, filtered=filtered, q=q,
                           category=category, in_stock=in_stock, sort=sort, sorts=SORTS, categories=categories)


@bp.route("/product/<int:product_id>")
def product(product_id):
    try:
        item = db.call_function("fn_get_product", product_id, one=True)
        variants = [v for v in db.call_function("fn_list_variants", product_id) if v["is_active"]] if item else []
        categories = {c["category_id"]: c["category_name"] for c in db.call_function("fn_list_categories")}
    except db.DbError as exc:
        flash(str(exc), "error")
        abort(404)
    if item is None or not variants:
        abort(404)

    colors, seen = [], set()
    for v in variants:
        name = v["color"] or ""
        if name and name not in seen:
            seen.add(name)
            mine = [x for x in variants if (x["color"] or "") == name]
            stocked = [x for x in mine if x["current_stock"] > 0]
            colors.append({"name": name, "hex": color_hex(name), "stock": sum(x["current_stock"] for x in mine),
                           "first_id": (stocked or mine)[0]["product_id"],
                           "image_id": next((x["image_id"] for x in mine if x["image_id"]), None)})

    wanted = (request.args.get("color") or "").strip().lower()
    selected = next((c["name"] for c in colors if c["name"].lower() == wanted), None)
    if selected is None:
        selected = item["color"] if item["color"] in seen else (colors[0]["name"] if colors else "")
    mine = sorted((v for v in variants if (v["color"] or "") == selected), key=lambda v: size_key(v["size"]))
    if not mine:
        mine = variants[:1]
    rep = next((v for v in mine if v["current_stock"] > 0), mine[0])

    try:
        photos = db.call_function("fn_list_product_photos", rep["product_id"])
    except db.DbError:
        photos = []
    ids = [p["image_id"] for p in photos]
    chosen = request.args.get("photo", type=int)
    main = chosen if chosen in ids else (ids[0] if ids else None)
    urls = [url_for("catalog.product_image", image_id=i) for i in ids]

    prices = [v["current_price"] for v in mine]
    stock = sum(v["current_stock"] for v in mine)
    return render_template(
        "product.html", item=item, category=categories.get(item["category_id"], ""), colors=colors,
        selected=selected, variants=mine, rep=rep, photo_ids=ids, photo_urls=urls, main_photo=main,
        main_index=ids.index(main) if main in ids else 0, price_min=min(prices), price_max=max(prices),
        base_price=min(v["base_price"] for v in mine), stock=stock, status=stock_status(stock))


@bp.route("/media/product/<int:image_id>")
def product_image(image_id):
    """Photos are stored in the database. A new upload gets a new id, so they can be cached for good."""
    try:
        row = db.call_function("fn_get_image", image_id, one=True)
    except db.DbError:
        abort(404)
    if row is None:
        abort(404)
    resp = Response(bytes(row["image_data"]), mimetype=row["mime_type"])
    resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp
