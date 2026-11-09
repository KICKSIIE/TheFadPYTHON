from decimal import Decimal, InvalidOperation


def to_decimal(value, label):
    try:
        number = Decimal((value or "").strip())
    except InvalidOperation:
        raise ValueError(f"{label} must be a number.")
    if not number.is_finite():
        raise ValueError(f"{label} must be a number.")
    return number


def to_int(value, label):
    try:
        return int((value or "").strip())
    except ValueError:
        raise ValueError(f"{label} must be a whole number.")


SIZE_ORDER = ["XXS", "XS", "S", "M", "L", "XL", "XXL", "2XL", "XXXL", "3XL", "4XL", "5XL"]


def size_key(size):
    """Sort sizes the way people expect: XS, S, M, L, XL, then anything else A to Z."""
    if not size:
        return (0, 0, "")
    s = size.upper()
    if s in SIZE_ORDER:
        return (1, SIZE_ORDER.index(s), "")
    return (2, 0, s)


def read_photo(file_storage):
    """Returns (mime, bytes) for an uploaded photo, or (None, None) if nothing was chosen.
    Checks the file's real signature, not its name, so only JPG, PNG and WebP get in."""
    if file_storage is None or not file_storage.filename:
        return None, None
    data = file_storage.read()
    if not data:
        return None, None
    if len(data) > 3 * 1024 * 1024:
        raise ValueError("The photo is larger than 3 MB. Resize it and try again.")
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg", data
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png", data
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", data
    raise ValueError("The photo must be a JPG, PNG or WebP image.")


def read_photos(file_list, limit=8):
    """Returns (mimes, datas) for every non-empty uploaded file, validated. Empty lists if none."""
    mimes, datas = [], []
    for f in file_list:
        mime, data = read_photo(f)
        if mime:
            mimes.append(mime)
            datas.append(data)
    if len(datas) > limit:
        raise ValueError(f"A product can have up to {limit} photos.")
    return mimes, datas


COLOR_HEX = {
    "white": "#f5f5f2", "black": "#17191f", "navy": "#1f2f54", "indigo": "#2e4a7d", "denim": "#4a6a96",
    "charcoal": "#3b4048", "grey": "#9aa0a8", "gray": "#9aa0a8", "silver": "#c3c7cc", "sage": "#9db39a",
    "forest": "#2f5a43", "green": "#4c8a5a", "olive": "#6d7040", "khaki": "#b9a779", "beige": "#d8c9ad",
    "cream": "#f2ead7", "ivory": "#f4efdf", "sand": "#d9c3a0", "natural": "#e8dfc9", "brown": "#7a5238",
    "tan": "#c19a6b", "red": "#b3342f", "maroon": "#6f1f2b", "burgundy": "#6f1f2b", "pink": "#e6a1b4",
    "orange": "#d9762b", "yellow": "#e4be3f", "mustard": "#c9a227", "blue": "#3f6fb5", "sky": "#8fb8de",
    "teal": "#2f7f84", "purple": "#6c4f9b", "lavender": "#b5a6d6",
}


def color_hex(name):
    """Swatch color for a color name. Tries the whole name, then each word ("Light Blue" -> blue)."""
    if not name:
        return "#c8ccd2"
    key = name.strip().lower()
    if key in COLOR_HEX:
        return COLOR_HEX[key]
    for word in reversed(key.split()):
        if word in COLOR_HEX:
            return COLOR_HEX[word]
    return "#c8ccd2"


LOW_STOCK = 5


def stock_status(stock):
    return "out" if stock <= 0 else ("low" if stock <= LOW_STOCK else "in")


def group_products(rows):
    """One card per product (style). Rows are color/size variants: collect colors, sizes, stock."""
    groups = {}
    for r in rows:
        groups.setdefault((r["category_name"], r["product_name"]), []).append(r)
    cards = []
    for (category, name), items in groups.items():
        items = sorted(items, key=lambda r: ((r.get("color") or ""), size_key(r.get("size"))))
        # colors keep the order they were created in (lowest product id first)
        by_color, order = {}, []
        for r in sorted(items, key=lambda r: r["product_id"]):
            c = r.get("color") or ""
            if c not in by_color:
                by_color[c] = []
                order.append(c)
            by_color[c].append(r)
        colors = []
        for c in order:
            rs = by_color[c]
            stocked = [r for r in rs if r["current_stock"] > 0]
            colors.append({
                "name": c, "hex": color_hex(c), "stock": sum(r["current_stock"] for r in rs),
                "image_id": next((r["image_id"] for r in rs if r["image_id"]), None),
                "first_id": (stocked or rs)[0]["product_id"],
            })
        named = [c for c in colors if c["name"]]
        sizes = {}
        for r in items:
            if r.get("size"):
                sizes[r["size"]] = sizes.get(r["size"], 0) + r["current_stock"]
        size_list = [{"size": k, "stock": v} for k, v in sorted(sizes.items(), key=lambda kv: size_key(kv[0]))]
        prices = [r["current_price"] for r in items]
        total = sum(r["current_stock"] for r in items)
        stocked_rows = [r for r in items if r["current_stock"] > 0]
        cards.append({
            "category": category, "name": name, "rows": items,
            "first_id": (stocked_rows or items)[0]["product_id"],
            "colors": named, "color_count": len(named), "sizes": size_list,
            "price_min": min(prices), "price_max": max(prices),
            "base_min": min(r["base_price"] for r in items),
            "image_id": next((c["image_id"] for c in colors if c["image_id"]), None),
            "description": next((r["description"] for r in items if r["description"]), None),
            "promo": next((r for r in items if r["discount_name"]), None),
            "stock": total, "status": stock_status(total),
            "newest": max(r["product_id"] for r in items),
        })
    return cards
