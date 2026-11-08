"""Runs without a database: db.call_function / db.call_procedure are faked."""
import io
import re
from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest

import db
from app import create_app

USERS = {
    ("dev_admin", "pw"): dict(user_id=1, username="dev_admin", first_name="Dev", last_name="Admin", user_type="AD"),
    ("dev_cashier", "pw"): dict(user_id=2, username="dev_cashier", first_name="Dev", last_name="Cashier", user_type="CA"),
}
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24
PRODUCT = dict(product_id=1, product_name="Denim Jacket", color="Black", size="M", display_name="Denim Jacket - Black (M)",
               description="Heavy cotton denim.", image_id=4, base_price=Decimal("1000"),
               current_price=Decimal("800"), current_stock=5, category_id=1, category_name="Outerwear",
               discount_name="Sale", discount_percentage=20, is_active=True)
PRODUCT_L = dict(PRODUCT, product_id=2, size="L", display_name="Denim Jacket - Black (L)", current_stock=0)
PRODUCT_NAVY = dict(PRODUCT, product_id=3, color="Navy", display_name="Denim Jacket - Navy (M)", image_id=6, current_stock=8)
VARIANTS = [dict(product_id=p["product_id"], color=p["color"], size=p["size"], base_price=p["base_price"],
                 current_price=p["current_price"], current_stock=p["current_stock"], is_active=True,
                 image_id=p["image_id"]) for p in (PRODUCT, PRODUCT_L, PRODUCT_NAVY)]
CATEGORY = dict(category_id=1, category_name="Outerwear", display_order=0, product_count=3)
STAFF = dict(user_id=2, username="dev_cashier", first_name="Dev", last_name="Cashier", user_type="CA",
             email="c@x.com", station="Counter 1", is_active=True, clocked_in=False,
             hired_on=date(2026, 10, 1))
BOARD = [
    dict(dtr_id=1, user_id=2, full_name="Dev Cashier", work_day=date(2026, 11, 3), shift_type="Regular",
         time_in=datetime(2026, 11, 3, 9, 5), time_out=datetime(2026, 11, 3, 17, 5), total_hours=Decimal("8.00"),
         overtime_hours=Decimal("0"), status="Present", note=None),
    dict(dtr_id=8, user_id=2, full_name="Dev Cashier", work_day=date(2026, 11, 3), shift_type="Overtime",
         time_in=datetime(2026, 11, 3, 17, 5), time_out=datetime(2026, 11, 3, 19, 5), total_hours=Decimal("2.00"),
         overtime_hours=Decimal("2.00"), status="Present", note="Stock count"),
    dict(dtr_id=7, user_id=2, full_name="Dev Cashier", work_day=date(2026, 11, 4), shift_type="Regular",
         time_in=datetime(2026, 11, 4, 9, 40), time_out=datetime(2026, 11, 4, 17, 40), total_hours=Decimal("8.00"),
         overtime_hours=Decimal("0"), status="Late", note=None),
    dict(dtr_id=None, user_id=2, full_name="Dev Cashier", work_day=date(2026, 11, 2), shift_type="Regular",
         time_in=None, time_out=None, total_hours=None, overtime_hours=None, status="Absent", note=None),
]
SETTING = dict(shift_start=time(9, 0), shift_end=time(17, 0), grace_minutes=15, shift_hours=Decimal("8"))
OT_LIST = [dict(permit_id=3, user_id=2, full_name="Dev Cashier", work_date=date(2026, 11, 9), start_time=time(18, 0),
                end_time=time(21, 0), grace_minutes=15, note="Holiday rush", status="Allowed", hours_worked=None),
           dict(permit_id=2, user_id=2, full_name="Dev Cashier", work_date=date(2026, 11, 3), start_time=time(17, 0),
                end_time=time(20, 0), grace_minutes=15, note=None, status="Done", hours_worked=Decimal("2.00"))]
SHIFT = dict(dtr_id=1, user_id=2, full_name="Dev Cashier", time_in=datetime(2026, 11, 3, 9, 5),
             time_out=datetime(2026, 11, 3, 18, 0), status="Present", note="forgot to clock in")
def open_shift():
    now = STATE["now"] or datetime.now()
    return dict(dtr_id=1, shift_type="Regular", time_in=now.replace(microsecond=0) - timedelta(hours=STATE["open_hours"]),
                time_out=None, total_hours=None, overtime_hours=Decimal("0"), status="Present", note=None)

INV = dict(product_id=1, product_name="Denim Jacket", category_name="Outerwear", current_stock=3,
           is_active=True, is_low=True)
MOVE = dict(log_id=1, logged_at=datetime(2026, 11, 3, 9, 0), product_id=1, product_name="Denim Jacket",
            transaction_type="IN", quantity_changed=10, balance_after=10, sale_id=None, staff_name="Dev Admin")
PROMO = dict(discount_id=1, discount_name="Sale", discount_percentage=20, start_date=date(2026, 11, 1),
             end_date=date(2026, 11, 30), status="Active", products_linked=1, linked_products="Denim Jacket")
SALE = dict(sale_id=7, user_id=2, cashier="Dev Cashier", sale_date=datetime(2026, 11, 3, 10, 0),
            fulfillment_type="Walk-in", customer_name=None, customer_contact=None, delivery_address=None,
            subtotal=Decimal("1000"), discount_amount=Decimal("200"), total_amount=Decimal("800"),
            payment_method="Cash", order_status="Completed", rider_service=None, rider_contact=None,
            item_count=1)
ITEM = dict(item_id=5, product_id=1, product_name="Denim Jacket", quantity=1, base_price=Decimal("1000"),
            unit_price_at_sale=Decimal("800"), line_total=Decimal("800"), discount_name="Sale", quantity_refunded=0)
SUMMARY = dict(sales_today=Decimal("800"), orders_today=1, pending_deliveries=0, low_stock=1,
               active_promos=1, refunds_today=Decimal("0"), staff_clocked_in=1)
REPORT = [dict(refund_method="Cash", refund_count=0, units_refunded=0, total_refunded=Decimal("0"),
               gross_sales=None, net_sales=None)]

CALLS = []
FUNC_CALLS = []
STATE = {"shift_open": False, "open_hours": 3, "now": None, "permit": None}


def fake_function(name, *args, one=False):
    FUNC_CALLS.append((name, args))
    if name == "fn_staff_access":
        now = STATE["now"] or datetime.now()
        return dict(active=True, allowed=True, can_clock_in=True, shop_now=now, shift_end=now.replace(hour=17, minute=0, second=0))
    if name == "fn_verify_management_pin":
        return dict(verified=args[1] == "123456")
    if name == "fn_login_user":
        return USERS.get(tuple(args))
    if name == "fn_get_product" and args[0] == 999:
        return None
    data = {
        "fn_list_products": [PRODUCT, PRODUCT_L, PRODUCT_NAVY], "fn_list_categories": [CATEGORY], "fn_list_staff": [STAFF],
        "fn_get_product": [PRODUCT], "fn_get_staff": [STAFF], "fn_attendance_report": [],
        "fn_my_attendance": [open_shift()] if STATE["shift_open"] else [],
        "fn_attendance_board": BOARD, "fn_get_shift": [SHIFT], "fn_get_shift_setting": [SETTING],
        "fn_list_overtime": OT_LIST, "fn_my_overtime": [STATE["permit"]] if STATE["permit"] else [],
        "fn_get_overtime": [dict(OT_LIST[0], started=False)],
        "fn_list_inventory": [INV], "fn_inventory_history": [MOVE], "fn_list_discounts": [PROMO],
        "fn_get_discount": [PROMO], "fn_discount_products": [PRODUCT, PRODUCT_L], "fn_list_sales": [SALE],
        "fn_get_sale": [SALE], "fn_sale_items": [ITEM], "fn_dashboard_summary": [SUMMARY],
        "fn_list_variants": VARIANTS, "fn_list_product_photos": [dict(image_id=4, sort_order=1), dict(image_id=5, sort_order=2)], "fn_get_image": [dict(mime_type="image/png", image_data=PNG)],
        "fn_refund_report": REPORT,
        "fn_sales_by_day": [dict(sale_day=date(2026, 11, 2), total_sales=Decimal("0"), order_count=0),
                            dict(sale_day=date(2026, 11, 3), total_sales=Decimal("800"), order_count=1)],
        "fn_top_products": [dict(product_name="Denim Jacket", units=4, revenue=Decimal("3200"))], "fn_list_refunds": [],
    }.get(name, [])
    return (data[0] if data else None) if one else data


def fake_procedure(name, *args):
    CALLS.append((name, args))
    if name == "sp_clock_in":
        STATE["shift_open"] = True
        STATE["open_hours"] = 0.1
    if name == "sp_clock_out":
        STATE.update(shift_open=False, open_hours=3, now=None, permit=None)
    return {"sp_create_sale": {"p_sale_id": 7}, "sp_stock_in": {"p_balance": 13},
            "sp_apply_discount": {"p_products_updated": 1}, "sp_process_refund": {"p_refund_id": 3}, "sp_add_variant": {"p_new_id": 9}, "sp_save_shift": {"p_result_id": 5}, "sp_allow_overtime": {"p_permit_id": 4}, "sp_create_discount": {"p_discount_id": 11}}.get(name, {})


@pytest.fixture
def client(monkeypatch):
    CALLS.clear()
    FUNC_CALLS.clear()
    STATE["shift_open"] = False
    monkeypatch.setattr(db, "call_function", fake_function)
    monkeypatch.setattr(db, "call_procedure", fake_procedure)
    return create_app(testing=True).test_client()


def token(client, path="/login"):
    html = client.get(path).get_data(as_text=True)
    return re.search(r'name="_csrf" value="([^"]+)"', html).group(1)


def login(client, user, pw="pw"):
    return client.post("/login", data={"username": user, "password": pw, "_csrf": token(client)})


def post(client, path, data, token_path="/"):
    data = dict(data, approval_pin="123456", _csrf=token(client, token_path))
    return client.post(path, data=data)


# ------------------------------------------------------------------ foundation
def test_requires_login(client):
    assert client.get("/dashboard").status_code == 302


def test_bad_password(client):
    assert login(client, "dev_admin", "nope").status_code == 401


def test_post_without_csrf_rejected(client):
    assert client.post("/login", data={"username": "a", "password": "b"}).status_code == 400


def test_cashier_blocked_from_admin(client):
    login(client, "dev_cashier")
    assert client.get("/admin/products/").status_code == 403
    assert client.get("/admin/staff/").status_code == 403


def test_open_redirect_blocked(client):
    r = client.post("/login", data={"username": "dev_admin", "password": "pw",
                                    "next": "//evil.com", "_csrf": token(client)})
    assert r.headers["Location"].endswith("/attendance/")


# --------------------------------------------------------------------- wave 1
def test_public_catalog_shows_products(client):
    html = client.get("/").get_data(as_text=True)
    assert "Denim Jacket" in html and "800.00" in html and "Outerwear" in html


def test_admin_product_pages(client):
    login(client, "dev_admin")
    assert "Denim Jacket" in client.get("/admin/products/").get_data(as_text=True)
    assert client.get("/admin/products/new").status_code == 200
    assert client.get("/admin/products/1/edit").status_code == 200
    assert client.get("/admin/products/categories").status_code == 200


def test_create_product_calls_routine(client):
    login(client, "dev_admin")
    r = post(client, "/admin/products/new", {"product_name": "Tee", "base_price": "250.50", "category_id": "1"},
             "/admin/products/new")
    assert r.status_code == 302
    assert CALLS[-1][0] == "sp_create_product"
    assert CALLS[-1][1][:3] == ("Tee", Decimal("250.50"), 1)


def test_bad_price_is_rejected_before_database(client):
    login(client, "dev_admin")
    r = post(client, "/admin/products/new", {"product_name": "Tee", "base_price": "abc", "category_id": "1"},
             "/admin/products/new")
    assert r.status_code == 400 and not CALLS


def test_staff_pages_and_create(client):
    login(client, "dev_admin")
    assert "Counter 1" in client.get("/admin/staff/").get_data(as_text=True)
    r = post(client, "/admin/staff/new", {"username": "newbie", "password": "longenough", "first_name": "N",
             "last_name": "B", "user_type": "CA", "email": "n@x.com", "station": "",
             "hired_on": "2026-11-01"}, "/admin/staff/new")
    assert r.status_code == 302 and CALLS[-1][0] == "sp_create_staff"


def test_admin_cannot_deactivate_self(client):
    login(client, "dev_admin")
    post(client, "/admin/staff/1/active", {"active": "0"}, "/admin/staff/")
    assert not CALLS


def test_clock_in_uses_the_shop_rules(client):
    login(client, "dev_cashier")
    assert "Clock in" in client.get("/attendance/").get_data(as_text=True)
    post(client, "/attendance/clock-in", {}, "/attendance/")
    name, args = CALLS[-1]
    assert name == "sp_clock_in" and args[0] == 2 and args[1] == time(9, 0) and args[2] == 15 and args[3] == 24


# ------------------------------------------------------------------ waves 2-5
def test_dashboard_shows_numbers(client):
    login(client, "dev_cashier")
    html = client.get("/dashboard").get_data(as_text=True)
    assert "Sales today" in html and "800.00" in html
    assert "Sales, last 7 days" in html and "Best sellers" in html and "4 sold" in html


def test_inventory_stock_in(client):
    login(client, "dev_cashier")
    assert "Denim Jacket" in client.get("/inventory/").get_data(as_text=True)
    assert client.get("/inventory/1").status_code == 200
    assert client.get("/inventory/history").status_code == 200
    post(client, "/inventory/1/move", {"action": "in", "quantity": "10"}, "/inventory/1")
    assert CALLS[-1] == ("sp_stock_in", (2, 1, 10, None))


def test_cashier_sees_promos_but_cannot_manage(client):
    login(client, "dev_cashier")
    assert "Sale" in client.get("/promos/").get_data(as_text=True)
    assert client.get("/admin/promos/").status_code == 403
    assert client.get("/admin/refunds/").status_code == 403


def test_admin_creates_and_ends_promo(client):
    login(client, "dev_admin")
    assert client.get("/admin/promos/").status_code == 200
    assert client.get("/admin/promos/1").status_code == 200
    r = post(client, "/admin/promos/new", {"discount_name": "Week", "discount_percentage": "10",
             "start_date": "2026-11-03", "end_date": "2026-11-10", "scope": "NONE"}, "/admin/promos/new")
    assert r.status_code == 302
    assert CALLS[-1][0] == "sp_create_discount" and CALLS[-1][1][1] == 10
    post(client, "/admin/promos/1/end", {}, "/admin/promos/")
    assert CALLS[-1][0] == "sp_update_discount" and CALLS[-1][1][5] is True


def test_pos_cart_and_checkout(client):
    login(client, "dev_cashier")
    post(client, "/pos/cart/add", {"product_id": "1", "quantity": "2"}, "/pos/")
    html = client.get("/pos/").get_data(as_text=True)
    assert "Complete sale" in html and "1,600.00" in html
    r = post(client, "/pos/checkout", {"fulfillment_type": "Walk-in", "payment_method": "Cash"}, "/pos/")
    assert r.status_code == 302 and r.headers["Location"].endswith("/orders/7")
    name, args = CALLS[-1]
    assert name == "sp_create_sale" and '"product_id": 1' in args[6] and '"quantity": 2' in args[6]
    assert "cart is empty" in client.get("/pos/").get_data(as_text=True)


def test_empty_cart_cannot_checkout(client):
    login(client, "dev_cashier")
    post(client, "/pos/checkout", {"fulfillment_type": "Walk-in", "payment_method": "Cash"}, "/pos/")
    assert not CALLS


def test_orders_and_receipt(client):
    login(client, "dev_cashier")
    assert "#7" in client.get("/orders/").get_data(as_text=True)
    html = client.get("/orders/7").get_data(as_text=True)
    assert "Denim Jacket" in html and "800.00" in html
    post(client, "/orders/7/status", {"new_status": "Cancelled"}, "/orders/7")
    assert CALLS[-1][0] == "sp_update_order_status"


def test_admin_refund_flow(client):
    login(client, "dev_admin")
    assert client.get("/admin/refunds/").status_code == 200
    assert client.get("/admin/refunds/sale/7").status_code == 200
    post(client, "/admin/refunds/sale/7", {"item_id": "5", "quantity": "1", "method": "Cash", "reason": "Wrong size"},
         "/admin/refunds/sale/7")
    assert CALLS[-1][0] == "sp_process_refund" and CALLS[-1][1][:4] == (1, 7, 5, 1)


def test_every_menu_page_opens_for_admin(client):
    import menu
    app_client = client
    login(app_client, "dev_admin")
    from flask import url_for
    app = app_client.application
    with app.test_request_context():
        urls = [url_for(i["endpoint"]) for i in menu.items_for("AD")]
    for url in urls:
        assert app_client.get(url, follow_redirects=True).status_code == 200, url


# ----------------------------------------------------- product details, sizes, photos
def post_form_with_file(client, path, fields, filename, content, token_path):
    fields = dict(fields, approval_pin="123456", _csrf=token(client, token_path), photos=(io.BytesIO(content), filename))
    return client.post(path, data=fields, content_type="multipart/form-data")


def test_catalog_groups_colors_and_sizes_into_one_card(client):
    html = client.get("/").get_data(as_text=True)
    assert html.count('class="card-price"') == 1                      # three variants, one product card
    assert html.count('class="dot"') == 2                              # Black and Navy
    assert "13 in stock" in html and "M, L" in html                    # stock shown on the card
    assert "/media/product/4" in html and "20% off" in html


def test_catalog_search_filter_and_sort(client):
    html = client.get("/?q=black+jacket&instock=1&sort=price_low&category=1").get_data(as_text=True)
    assert ("fn_list_products", ("black jacket", 1, False)) in FUNC_CALLS
    assert "1 product" in html and "Clear" in html
    assert "Nothing matches" not in html


def test_product_page_shows_colors_sizes_and_stock(client):
    html = client.get("/product/1").get_data(as_text=True)
    assert "Heavy cotton denim." in html and "Color:" in html and "Black" in html
    assert "color=Navy" in html                                        # swatch link to the other color
    assert "5 left" in html and "Sold out" in html                     # per-size stock
    assert ("fn_list_product_photos", (1,)) in FUNC_CALLS
    navy = client.get("/product/1?color=Navy").get_data(as_text=True)
    assert "8 left" in navy and ("fn_list_product_photos", (3,)) in FUNC_CALLS   # Navy gallery, not Black
    assert client.get("/product/999").status_code == 404


def test_photo_served_from_database(client):
    r = client.get("/media/product/4")
    assert r.status_code == 200 and r.mimetype == "image/png" and r.data == PNG
    assert "immutable" in r.headers["Cache-Control"]


def test_create_product_with_sizes_and_photo(client):
    login(client, "dev_admin")
    r = post_form_with_file(client, "/admin/products/new",
                            {"product_name": "Tee", "base_price": "250", "category_id": "1",
                             "description": "Soft tee", "sizes": "S, M", "colors": "Black, Navy"},
                            "tee.png", PNG, "/admin/products/new")
    assert r.status_code == 302
    name, args = CALLS[-1]
    assert name == "sp_create_product"
    assert args[3:] == ("Soft tee", "S, M", "Black, Navy", ["image/png"], [PNG], None)


def test_fake_image_is_rejected(client):
    login(client, "dev_admin")
    r = post_form_with_file(client, "/admin/products/new",
                            {"product_name": "Tee", "base_price": "250", "category_id": "1"},
                            "tee.png", b"this is not an image", "/admin/products/new")
    assert r.status_code == 400 and not CALLS


def test_edit_applies_to_all_sizes_and_add_size(client):
    login(client, "dev_admin")
    assert client.get("/admin/products/1/edit").status_code == 200
    post(client, "/admin/products/1/edit", {"product_name": "Denim Jacket", "base_price": "1200", "category_id": "1",
         "size": "M", "color": "Black", "description": "New text", "apply_all": "1"}, "/admin/products/1/edit")
    name, args = CALLS[-1]
    assert name == "sp_update_product" and args[4:6] == ("M", "Black") and args[-1] is True and len(args) == 8
    r = post(client, "/admin/products/1/add-variant", {"size": "XL", "color": ""}, "/admin/products/1/edit")
    assert CALLS[-1] == ("sp_add_variant", (1, "XL", "", None)) and r.headers["Location"].endswith("/9/edit")


# ----------------------------------------------------------- photo gallery
def test_gallery_on_product_page(client):
    html = client.get("/product/1").get_data(as_text=True)
    assert "/media/product/4" in html and "photo=5" in html           # cover + a thumbnail link
    assert "data-lightbox-urls" in html and "/media/product/5" in html  # full-screen viewer wiring
    picked = client.get("/product/1?photo=5").get_data(as_text=True)
    assert 'class="thumb detail" src="/media/product/5"' in picked


def test_manage_photos_page_and_actions(client):
    login(client, "dev_admin")
    html = client.get("/admin/products/1/photos").get_data(as_text=True)
    assert "2 of 8 photos" in html and "Make cover" in html
    post(client, "/admin/products/1/photos/5/cover", {"apply_all": "1"}, "/admin/products/1/photos")
    assert CALLS[-1] == ("sp_set_cover_photo", (1, 5, True))
    post(client, "/admin/products/1/photos/4/remove", {"apply_all": "1"}, "/admin/products/1/photos")
    assert CALLS[-1] == ("sp_remove_product_photo", (1, 4, True))


def test_upload_several_photos(client):
    login(client, "dev_admin")
    fields = {"apply_all": "1", "approval_pin": "123456", "_csrf": token(client, "/admin/products/1/photos"),
              "photos": [(io.BytesIO(PNG), "a.png"), (io.BytesIO(PNG), "b.png")]}
    r = client.post("/admin/products/1/photos/upload", data=fields, content_type="multipart/form-data")
    assert r.status_code == 302
    added = [c for c in CALLS if c[0] == "sp_add_product_photo"]
    assert len(added) == 2 and added[0][1] == (1, "image/png", PNG, True, None)


def test_upload_rejects_non_image_and_empty(client):
    login(client, "dev_admin")
    fields = {"apply_all": "1", "approval_pin": "123456", "_csrf": token(client, "/admin/products/1/photos"),
              "photos": [(io.BytesIO(b"nope"), "a.png")]}
    client.post("/admin/products/1/photos/upload", data=fields, content_type="multipart/form-data")
    assert not CALLS
    r = post(client, "/admin/products/1/photos/upload", {"apply_all": "1"}, "/admin/products/1/photos")
    assert not CALLS


def test_full_screen_viewer_script_is_served_and_loaded(client):
    js = client.get("/static/lightbox.js")
    assert js.status_code == 200 and b"showModal" in js.data and b"popstate" in js.data
    assert "lightbox.js" in client.get("/").get_data(as_text=True)


def test_admin_photo_grid_opens_viewer(client):
    login(client, "dev_admin")
    html = client.get("/admin/products/1/photos").get_data(as_text=True)
    assert "data-lightbox-urls" in html and 'data-lightbox-index="1"' in html


# ------------------------------------------------------- colors, promos, navigation
def test_promo_created_then_applied_to_whole_product(client):
    login(client, "dev_admin")
    r = post(client, "/admin/promos/new", {"discount_name": "Hoodie Week", "discount_percentage": "20",
             "start_date": "2026-11-03", "end_date": "2026-11-10", "scope": "PRODUCT", "product_id": "1"},
             "/admin/promos/new")
    assert r.status_code == 302
    names = [c[0] for c in CALLS]
    assert names[-2:] == ["sp_create_discount", "sp_apply_discount"]
    assert CALLS[-1][1][:3] == (11, "PRODUCT", 1)
    page = client.get("/admin/promos/1").get_data(as_text=True)       # promo shows one product line, 2 variants
    assert "Denim Jacket" in page and ">2<" in page


def test_menu_sections_follow_role(client):
    import menu
    cashier = [g["name"] for g in menu.groups_for("CA")]
    admin = [g["name"] for g in menu.groups_for("AD")]
    assert "Admin" not in cashier and "Admin" in admin and cashier[0] == "Overview"
    labels = [i["label"] for g in menu.groups_for("AD") for i in g["items"]]
    assert labels.count("Promos") == 1                                 # admin sees only the promo manager


def test_staff_layout_has_sections_and_public_pages_keep_shop_header(client):
    login(client, "dev_cashier")
    staff = client.get("/dashboard").get_data(as_text=True)
    assert 'class="nav-sec"' in staff and "New sale" in staff and "View shop" in staff
    shop = client.get("/").get_data(as_text=True)                      # even when signed in: plain shop layout
    assert 'class="site-head"' in shop and 'class="side"' not in shop


def test_photos_page_has_color_tabs(client):
    login(client, "dev_admin")
    html = client.get("/admin/products/1/photos").get_data(as_text=True)
    assert 'class="tab on"' in html and "Navy" in html


def test_admin_products_grouped_by_default_with_variant_toggle(client):
    login(client, "dev_admin")
    html = client.get("/admin/products/").get_data(as_text=True)
    assert "One row per product" in html and "3 items" in html and "Show every color and size" in html
    assert html.count("Denim Jacket") >= 1 and html.count("<tr>") <= 3          # header + one product row
    every = client.get("/admin/products/?variants=1").get_data(as_text=True)
    assert "Every color and size" in every and "Navy" in every


def test_catalog_has_a_single_search_box(client):
    assert client.get("/").get_data(as_text=True).count('type="search"') == 1


def test_shop_is_fully_public_and_has_no_staff_links(client):
    for path in ("/", "/product/1", "/?q=jacket"):
        html = client.get(path).get_data(as_text=True)
        assert 'href="/login' not in html and 'href="/dashboard' not in html and 'href="/staff' not in html
        assert "Staff sign in" not in html and "Dashboard" not in html
    login(client, "dev_admin")                                          # still the same when a staff member is signed in
    html = client.get("/").get_data(as_text=True)
    assert "Dashboard" not in html and 'href="/dashboard' not in html and "Dev Admin" not in html


def test_staff_short_address(client):
    assert client.get("/staff").headers["Location"].endswith("/login")
    login(client, "dev_admin")
    assert client.get("/staff").headers["Location"].endswith("/attendance/")


def test_dashboard_survives_missing_name_and_stale_cookie(client):
    login(client, "dev_admin")
    with client.session_transaction() as sess:
        sess["display_name"] = None                                     # the case that crashed
    r = client.get("/dashboard")
    assert r.status_code == 200 and "Hello, dev_admin" in r.get_data(as_text=True)
    with client.session_transaction() as sess:                          # old cookie without the new fields
        sess.pop("username"); sess.pop("user_type")
    r = client.get("/dashboard")
    assert r.status_code == 302 and "/login" in r.headers["Location"]


# ------------------------------------------------ attendance, overtime, payroll, controls, layout
def _attendance_html(client, hours):
    STATE["shift_open"], STATE["open_hours"] = True, hours
    login(client, "dev_cashier")
    return client.get("/attendance/").get_data(as_text=True)


def test_clock_out_waits_for_a_full_shift(client):
    html = _attendance_html(client, 3)
    assert "of 8 hours" in html and "automatically closes at" in html and ">Clock out</button>" not in html


def test_clock_out_opens_after_8_hours(client):
    html = _attendance_html(client, 9.5)
    assert "disabled>Clock out" not in html and "did not clock out" not in html
    post(client, "/attendance/clock-out", {}, "/attendance/")
    name, args = CALLS[-1]
    assert name == "sp_clock_out" and args[1] == 8 and args[2] == 24 and args[3] is None


def test_missed_clock_out_is_automatic(client):
    html = _attendance_html(client, 30)
    assert "Forgotten clock-outs close automatically" in html
    assert 'type="datetime-local"' not in html
    assert client.post("/attendance/missed-clock-out", data={"_csrf": token(client, "/attendance/")}).status_code == 404


def test_everyone_tab_is_admin_only_and_shows_absences(client):
    login(client, "dev_cashier")
    assert client.get("/attendance/everyone").status_code == 403
    assert client.get("/attendance/shift").status_code == 403
    with client.session_transaction() as sess:
        sess.clear()
    login(client, "dev_admin")
    html = client.get("/attendance/everyone").get_data(as_text=True)
    assert 'class="tab on"' in html and "Absent" in html and "Late" in html
    assert "Add shift" in html and "Edit" in html and "Hours worked" in html
    assert "Overtime" in html and "shift/8" not in html          # overtime rows are shown but not editable
    assert "shift/1" in html


def test_admin_adds_and_edits_a_shift_with_a_reason(client):
    login(client, "dev_admin")
    assert client.get("/attendance/shift?user_id=2&date=2026-11-02").status_code == 200
    fields = {"user_id": "2", "time_in": "2026-11-02T09:00", "time_out": "2026-11-02T17:00", "note": "forgot to clock in"}
    r = post(client, "/attendance/shift", fields, "/attendance/shift")
    assert r.status_code == 302
    name, args = CALLS[-1]
    assert name == "sp_save_shift" and args[0] is None and args[1] == 2 and args[3] == datetime(2026, 11, 2, 17, 0)
    assert args[4] == "forgot to clock in" and args[5] == time(9, 0) and args[6] == 15
    assert args[7] == Decimal("8") and args[8] == 24 and len(args) == 10
    post(client, "/attendance/shift/1", fields, "/attendance/shift/1")
    assert CALLS[-1][1][0] == 1
    CALLS.clear()
    bad = post(client, "/attendance/shift", dict(fields, time_in="nope"), "/attendance/shift")
    assert bad.status_code == 400 and not CALLS


def test_inventory_low_level_is_set_in_the_search(client):
    login(client, "dev_cashier")
    html = client.get("/inventory/").get_data(as_text=True)
    assert ("fn_list_inventory", (None, False, 5)) in FUNC_CALLS and 'name="max"' in html and "Low means" in html
    client.get("/inventory/?max=12&low=1&q=jacket")
    assert ("fn_list_inventory", ("jacket", True, 12)) in FUNC_CALLS
    assert "below 6" not in html


def test_pos_cart_stepper_buttons(client):
    login(client, "dev_cashier")
    post(client, "/pos/cart/add", {"product_id": "1", "quantity": "1"}, "/pos/")
    post(client, "/pos/cart/update", {"product_id": "1", "delta": "1"}, "/pos/")
    assert 'class="stepper-qty" aria-label="Quantity">2<' in client.get("/pos/").get_data(as_text=True)
    post(client, "/pos/cart/update", {"product_id": "1", "quantity": "0"}, "/pos/")
    assert "cart is empty" in client.get("/pos/").get_data(as_text=True)


def test_actions_are_buttons_and_checkboxes_are_toggles():
    import glob, os, re
    root = os.path.join(os.path.dirname(__file__), "..")
    for f in glob.glob(os.path.join(root, "templates", "**", "*.html"), recursive=True):
        html = open(f).read()
        assert "link-action" not in html and "link-btn" not in html, f
        for m in re.finditer(r'<input[^>]*type="checkbox"[^>]*>', html):
            if "navtoggle" in m.group(0):
                continue
            assert 'class="toggle' in html[max(0, m.start() - 80):m.start()], (f, m.group(0))


def test_navigation_has_no_repeated_shortcuts(client):
    login(client, "dev_admin")
    html = client.get("/dashboard").get_data(as_text=True)
    assert html.count("New sale") == 1 and 'class="topline"' not in html and "Today's orders" not in html
    assert "View shop" in html and "Sign out" in html and "Payroll" in html
    import menu
    cashier = [i["label"] for g in menu.groups_for("CA") for i in g["items"]]
    assert "New sale" in cashier and "Payroll" not in cashier and "Payroll" in [i["label"] for g in menu.groups_for("AD") for i in g["items"]]


def test_layouts_use_the_full_screen_width():
    import os, re
    css = open(os.path.join(os.path.dirname(__file__), "..", "static", "style.css")).read()
    assert re.search(r"\.content \{[^}]*max-width: none", css)
    assert "1180px" not in css


# ------------------------------------------- schedule, overtime, footer, centered filters, no payroll
from contextlib import contextmanager


@contextmanager
def frozen(when):
    """Pretend it is `when` inside the attendance pages."""
    import modules.attendance as att
    class Fixed(datetime):
        @classmethod
        def now(cls, tz=None):
            return when
    old, att.datetime = att.datetime, Fixed
    STATE["now"] = when
    try:
        yield
    finally:
        att.datetime, STATE["now"] = old, None


def _permit(**kw):
    base = dict(permit_id=3, work_date=date(2026, 11, 9), start_time=time(18, 0), end_time=time(21, 0),
                grace_minutes=15, note="Holiday rush", dtr_id=None, time_in=None, time_out=None)
    return dict(base, **kw)


def _ot_page(client, when, permit, regular_open=False):
    STATE["permit"] = permit
    STATE["shift_open"], STATE["open_hours"] = regular_open, 3
    with client.session_transaction() as session:
        signed_in = "user_id" in session
    if not signed_in:
        login(client, "dev_cashier")
    with frozen(when):
        return client.get("/attendance/").get_data(as_text=True)


def test_employee_overtime_card_follows_the_time_in_and_grace(client):
    day = date(2026, 11, 9)
    early = _ot_page(client, datetime(2026, 11, 9, 17, 30), _permit())
    assert "Overtime today" in early and "06:00 PM to 09:00 PM" in early and "Starts at 06:00 PM" in early
    assert "disabled>Start overtime" in early
    ready = _ot_page(client, datetime(2026, 11, 9, 18, 10), _permit())
    assert "disabled>Start overtime" not in ready and "Start overtime" in ready and "Clock in by 06:15 PM" in ready
    assert 'badge warn">Late' not in ready
    late = _ot_page(client, datetime(2026, 11, 9, 18, 30), _permit())
    assert 'badge warn">Late' in late and "Start overtime" in late
    waiting = _ot_page(client, datetime(2026, 11, 9, 18, 10), _permit(), regular_open=True)
    assert "Clock out of your regular shift first." in waiting and "disabled>Start overtime" in waiting
    on = _ot_page(client, datetime(2026, 11, 9, 19, 0), _permit(dtr_id=9, time_in=datetime(2026, 11, 9, 18, 5)))
    assert "Automatically closes at the approved end" in on and "Start overtime" not in on
    done = _ot_page(client, datetime(2026, 11, 9, 20, 0),
                    _permit(dtr_id=9, time_in=datetime(2026, 11, 9, 18, 5), time_out=datetime(2026, 11, 9, 19, 30)))
    assert "Overtime done." in done and "Start overtime" not in done
    over = _ot_page(client, datetime(2026, 11, 9, 21, 30), _permit())
    assert "window has ended" in over and "Start overtime" not in over
    upcoming = _ot_page(client, datetime(2026, 11, 8, 12, 0), _permit())          # permit is for tomorrow
    assert "Upcoming overtime" in upcoming and "Overtime today" not in upcoming
    post(client, "/attendance/overtime-in", {}, "/attendance/")
    assert CALLS[-1] == ("sp_overtime_in", (2, None))
    post(client, "/attendance/overtime-out", {}, "/attendance/")
    assert CALLS[-1] == ("sp_overtime_out", (2, None))


def test_admin_allows_overtime_with_time_in_time_out_and_grace(client):
    login(client, "dev_cashier")
    assert client.get("/attendance/overtime").status_code == 403 and client.get("/attendance/overtime/new").status_code == 403
    with client.session_transaction() as sess:
        sess.clear()
    login(client, "dev_admin")
    html = client.get("/attendance/overtime").get_data(as_text=True)
    assert "Allow overtime" in html and "06:00 PM" in html and "Allowed" in html and "Done" in html
    assert html.count(">Cancel</button>") == 1                                     # only the unused one can be cancelled
    form = client.get("/attendance/overtime/new").get_data(as_text=True)
    assert 'name="start_time"' in form and 'name="end_time"' in form and 'name="grace_minutes"' in form
    fields = {"user_id": "2", "work_date": "2026-11-09", "start_time": "18:00", "end_time": "21:00",
              "grace_minutes": "10", "note": "Holiday rush"}
    assert post(client, "/attendance/overtime/new", fields, "/attendance/overtime/new").status_code == 302
    name, args = CALLS[-1]
    assert name == "sp_allow_overtime" and args[0] == 1 and args[1] == 2 and args[2] == date(2026, 11, 9)
    assert args[3] == time(18, 0) and args[4] == time(21, 0) and args[5] == 10 and args[6] == "Holiday rush"
    post(client, "/attendance/overtime/new", dict(fields, grace_minutes=""), "/attendance/overtime/new")
    assert CALLS[-1][1][5] is None                                                  # blank grace = the schedule's default
    CALLS.clear()
    bad = post(client, "/attendance/overtime/new", dict(fields, start_time="late"), "/attendance/overtime/new")
    assert bad.status_code == 400 and not CALLS
    assert client.get("/attendance/overtime/3").status_code == 200
    post(client, "/attendance/overtime/3", {"start_time": "19:00", "end_time": "21:30", "grace_minutes": "5", "note": ""},
         "/attendance/overtime/3")
    assert CALLS[-1] == ("sp_update_overtime", (3, time(19, 0), time(21, 30), 5, ""))
    post(client, "/attendance/overtime/3/cancel", {}, "/attendance/overtime")
    assert CALLS[-1] == ("sp_cancel_overtime", (3,))


def test_admin_sets_the_shift_schedule(client):
    login(client, "dev_cashier")
    assert client.get("/attendance/schedule").status_code == 403
    with client.session_transaction() as sess:
        sess.clear()
    login(client, "dev_admin")
    html = client.get("/attendance/schedule").get_data(as_text=True)
    assert 'value="09:00"' in html and 'value="17:00"' in html and 'value="15"' in html and "Save schedule" in html
    post(client, "/attendance/schedule", {"shift_start": "08:30", "shift_end": "17:30", "grace_minutes": "10"}, "/attendance/schedule")
    assert CALLS[-1] == ("sp_save_shift_setting", (time(8, 30), time(17, 30), 10))
    CALLS.clear()
    assert post(client, "/attendance/schedule", {"shift_start": "x", "shift_end": "17:30", "grace_minutes": "10"},
                "/attendance/schedule").status_code == 400 and not CALLS


def test_clock_in_uses_the_saved_schedule(client):
    import modules.attendance as att
    login(client, "dev_cashier")
    orig = t_fake = fake_function
    def with_setting(name, *args, one=False):
        if name == "fn_get_shift_setting":
            return dict(shift_start=time(8, 0), shift_end=time(16, 0), grace_minutes=5, shift_hours=Decimal("8"))
        return orig(name, *args, one=one)
    db.call_function = with_setting
    post(client, "/attendance/clock-in", {}, "/attendance/")
    name, args = CALLS[-1]
    assert name == "sp_clock_in" and args[1] == time(8, 0) and args[2] == 5            # the admin's grace, not the default


def test_shop_footer_has_ordering_address_map_and_facebook(client):
    for path in ("/", "/product/1"):
        html = client.get(path).get_data(as_text=True)
        assert "How to order" in html and "contact our official Facebook page" in html
        assert "https://www.facebook.com/profile.php?id=61580609323200" in html and "Message us on Facebook" in html
        assert "G.Y. Dela Serna St, Lapu-Lapu, Cebu" in html and "8W6X+2QC" in html
        assert "<iframe" in html and "google.com/maps?q=10.3100695%2C123.9493883" in html and "output=embed" in html
        assert "Open in Google Maps" in html and "Get directions" in html and "destination=10.3100695%2C123.9493883" in html
    assert "Order on Facebook" in client.get("/product/1").get_data(as_text=True)
    login(client, "dev_admin")
    assert "<iframe" not in client.get("/dashboard").get_data(as_text=True)          # staff area has no shop footer
    assert 'class="site-foot"' not in client.get("/login", follow_redirects=True).get_data(as_text=True)


def test_shop_categories_are_on_the_left(client):
    html = client.get("/").get_data(as_text=True)
    assert html.index('class="shop-categories"') < html.index('class="shop-results"')


def test_payroll_summary_is_registered(client):
    login(client, "dev_admin")
    assert client.get("/admin/payroll/").status_code == 200
    assert client.get("/admin/payroll/download").status_code == 200
