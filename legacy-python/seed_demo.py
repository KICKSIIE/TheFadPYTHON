"""Fills The Fad with demo data so the shop and dashboard look alive.

    python seed_demo.py                 (asks before doing anything; add --yes to skip the question)
    python seed_demo.py --attendance    (database already seeded: just add attendance and start dates)

Run it AFTER sql/setup_all.sql, on a development database. It creates, through the same stored
routines the app uses: categories, products with colors, sizes and photos, stock, promos, a few
staff accounts, two weeks of attendance (late, absences, allowed overtime), about 35 orders spread over the last two weeks (walk-in and delivery), a refund,
and some attendance. Products that already exist are skipped, so a second run does nothing.
The photos are drawn placeholders; replace them with real ones under Products > Manage photos.
"""
import argparse
import json
import random
import sys
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from demo_images import render_photos
from utils import color_hex

CATEGORIES = [("Tops", 1), ("Outerwear", 2), ("Bottoms", 3), ("Headwear", 4), ("Accessories", 5)]

PRODUCTS = [
    dict(name="Essential Tee", category="Tops", price=499, kind="tee", sizes="S, M, L, XL",
         colors=["White", "Black", "Sage"], description="Midweight cotton tee with a relaxed fit. Soft, breathable and easy to layer."),
    dict(name="Boxy Graphic Tee", category="Tops", price=699, kind="tee", sizes="S, M, L, XL",
         colors=["Black", "Cream"], description="Cropped boxy cut in heavy cotton. Pairs well with wide-leg pants."),
    dict(name="Ribbed Tank", category="Tops", price=399, kind="tank", sizes="XS, S, M, L",
         colors=["Sand", "Black"], description="Stretchy ribbed knit tank. Fits close to the body."),
    dict(name="Classic Hoodie", category="Outerwear", price=1299, kind="hoodie", sizes="S, M, L, XL",
         colors=["Charcoal", "Navy", "Forest"], description="Fleece-lined pullover with a kangaroo pocket and drawstring hood. Warm without being bulky."),
    dict(name="Denim Jacket", category="Outerwear", price=1899, kind="jacket", sizes="S, M, L, XL",
         colors=["Indigo"], description="Heavy cotton denim with chest pockets and button front. Gets better with every wash."),
    dict(name="Windbreaker", category="Outerwear", price=1499, kind="jacket", sizes="M, L, XL",
         colors=["Black", "Red"], description="Lightweight shell that packs small. Good for rainy commutes."),
    dict(name="Straight Jeans", category="Bottoms", price=1499, kind="pants", sizes="28, 30, 32, 34",
         colors=["Indigo", "Black"], description="Straight leg, mid rise, sturdy stretch denim."),
    dict(name="Cargo Shorts", category="Bottoms", price=899, kind="shorts", sizes="S, M, L, XL",
         colors=["Khaki", "Olive"], description="Cotton twill shorts with two roomy side pockets."),
    dict(name="Jogger Pants", category="Bottoms", price=999, kind="pants", sizes="S, M, L, XL",
         colors=["Grey", "Black"], description="Soft brushed fleece with tapered legs and elastic cuffs."),
    dict(name="Dad Cap", category="Headwear", price=349, kind="cap", sizes="",
         colors=["Black", "Beige", "Navy"], description="Unstructured six-panel cap with an adjustable strap."),
    dict(name="Bucket Hat", category="Headwear", price=399, kind="hat", sizes="",
         colors=["Cream", "Olive"], description="Washed cotton bucket hat. Wide brim keeps the sun off."),
    dict(name="Canvas Tote", category="Accessories", price=299, kind="tote", sizes="",
         colors=["Natural", "Black"], description="Roomy canvas tote with reinforced handles and an inside pocket."),
]

STAFF = [("Maria", "Santos", "maria.santos", "CA", "Counter 2"),
         ("Juan", "Dela Cruz", "juan.delacruz", "CA", "Counter 1"),
         ("Ana", "Reyes", "ana.reyes", "AD", None)]

CUSTOMERS = ["Camille Ramos", "Joaquin Bautista", "Bea Villanueva", "Miguel Torres", "Lara Mendoza",
             "Paolo Navarro", "Isabel Cruz", "Rafael Aquino", "Katrina Lim", "Diego Soriano"]
STREETS = ["12 Rizal St., Barangay Poblacion", "45 Mabini Ave., Barangay San Roque",
           "8 Bonifacio Rd., Barangay Central", "23 Luna St., Barangay Pag-asa", "7 Del Pilar St., Barangay Lourdes"]
RIDERS = ["Lalamove", "Grab Express", "Move It"]


def _execute(db, sql, params):
    with db.pool.connection() as conn:
        conn.execute(sql, params)


def _insert_returning(db, sql, params):
    with db.pool.connection() as conn:
        return conn.execute(sql, params).fetchone()


def seed_attendance(db, rng, say=print, today=None, days=14):
    """Two weeks of shifts for every active staff member: mostly on time, some late, a few absences, and
    some overtime that an admin allowed. Sets start dates first. Days that already have a shift are left alone."""
    today = today or date.today()
    start = today - timedelta(days=days)
    _execute(db, "UPDATE thefad.users SET hired_on = %s WHERE hired_on > %s", (start, start))
    board = db.call_function("fn_attendance_board", start, today - timedelta(days=1), None, "1,2,3,4,5,6")
    added = overtime = 0
    for row in board:
        if row["shift_type"] != "Regular" or row["status"] != "Absent" or rng.random() < 0.08:
            continue                                                  # leave about 8% as real absences
        late = rng.random() < 0.15
        tin = datetime.combine(row["work_day"],
                               time(9, rng.randint(20, 55)) if late
                               else time(8, rng.randint(50, 59)) if rng.random() < 0.5 else time(9, rng.randint(0, 10)))
        tout = tin + timedelta(hours=8)
        _execute(db, "INSERT INTO thefad.daily_time_record (user_id, time_in, time_out, total_hours, status) "
                     "VALUES (%s, %s, %s, %s, %s)",
                 (row["user_id"], tin, tout, Decimal("8.00"), "Late" if tin.time() > time(9, 15) else "Present"))
        added += 1
        if rng.random() < 0.2:                                        # an admin allowed 5 PM to 8 PM overtime
            day = tin.date()
            permit = _insert_returning(
                db, "INSERT INTO thefad.overtime_permit (user_id, work_date, start_time, end_time, grace_minutes, note) "
                    "VALUES (%s, %s, %s, %s, %s, %s) RETURNING permit_id",
                (row["user_id"], day, time(17, 0), time(20, 0), 15, rng.choice(["Busy day", "Stock count", "Sale prep"])))
            ot_in = datetime.combine(day, time(17, rng.choice([0, 3, 8, 22])))
            ot_out = datetime.combine(day, time(rng.choice([19, 19, 20]), rng.choice([0, 30]) if rng.random() < 0.5 else 0))
            ot_out = min(ot_out, datetime.combine(day, time(20, 0)))        # never past the allowed time out
            if ot_out <= ot_in:
                ot_out = datetime.combine(day, time(20, 0))
            hours = Decimal(str(round((ot_out - ot_in).total_seconds() / 3600, 2)))
            _execute(db, "INSERT INTO thefad.daily_time_record (user_id, time_in, time_out, total_hours, status, shift_type, permit_id) "
                         "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                     (row["user_id"], ot_in, ot_out, hours, "Late" if ot_in.time() > time(17, 15) else "Present",
                      "Overtime", permit["permit_id"]))
            overtime += 1
    say(f"Attendance: {added} shifts and {overtime} overtime records added for the last {days} days.")
    return added


def seed(db, rng, say=print, today=None):
    today = today or date.today()

    # ------------------------------------------------------------ who is who
    staff = db.call_function("fn_list_staff")
    admin = next((s for s in staff if s["username"] == "dev_admin"), None) or \
            next((s for s in staff if s["user_type"] == "AD" and s["is_active"]), None)
    if admin is None:
        say("No admin account found. Run sql/setup_all.sql first.")
        return False
    admin_id = admin["user_id"]

    # ------------------------------------------------------------ categories
    cat_ids = {c["category_name"]: c["category_id"] for c in db.call_function("fn_list_categories")}
    for name, order in CATEGORIES:
        if name not in cat_ids:
            cat_ids[name] = db.call_procedure("sp_create_category", name, order, None)["p_category_id"]
    say(f"Categories ready ({len(CATEGORIES)}).")

    # ------------------------------------------------------------ products, colors, sizes, photos
    made = []
    for p in PRODUCTS:
        try:
            db.call_procedure("sp_create_product", p["name"], Decimal(p["price"]), cat_ids[p["category"]],
                              p["description"], p["sizes"], ", ".join(p["colors"]), None, None, None)
        except db.DbError as exc:
            say(f"  skipped {p['name']}: {exc}")
            continue
        rows = [r for r in db.call_function("fn_list_products", p["name"], cat_ids[p["category"]], True)
                if r["product_name"] == p["name"]]
        for color in p["colors"]:
            rep = next(r for r in rows if r["color"] == color)
            for png in render_photos(p["kind"], color_hex(color)):
                db.call_procedure("sp_add_product_photo", rep["product_id"], "image/png", png, True, None)
        made.append(p["name"])
        say(f"  added {p['name']}: {len(rows)} variants, {3 * len(p['colors'])} photos")
    if not made:
        say("Demo products are already there, so nothing else was added.")
        return False

    def demo_rows(active_only=True):
        return [r for r in db.call_function("fn_list_products", None, None, not active_only)
                if r["product_name"] in made]

    # ------------------------------------------------------------ stock
    stock = {}
    for r in demo_rows():
        qty = rng.randint(10, 35)
        db.call_procedure("sp_stock_in", admin_id, r["product_id"], qty, None)
        stock[r["product_id"]] = qty
    say(f"Stocked {len(stock)} variants.")

    # ------------------------------------------------------------ staff
    for first, last, username, role, station in STAFF:
        try:
            db.call_procedure("sp_create_staff", username, "Cashier@1234", first, last, role,
                              f"{username}@thefad.local", station, today - timedelta(days=14), None)
        except db.DbError:
            pass
    cashiers = [s["user_id"] for s in db.call_function("fn_list_staff")
                if s["user_type"] == "CA" and s["is_active"]] or [admin_id]

    # ------------------------------------------------------------ promos
    def first_id(style):
        return next(r["product_id"] for r in demo_rows() if r["product_name"] == style)

    for name, pct, start, end, scope, style in [
            ("Midseason Sale", 20, today - timedelta(days=3), today + timedelta(days=10), "PRODUCT", "Classic Hoodie"),
            ("Weekend Deal", 15, today - timedelta(days=1), today + timedelta(days=2), "PRODUCT", "Essential Tee"),
            ("Payday Sale", 25, today + timedelta(days=6), today + timedelta(days=8), None, None),
            ("Summer Clearance", 30, today - timedelta(days=40), today - timedelta(days=20), None, None)]:
        try:
            did = db.call_procedure("sp_create_discount", name, pct, start, end, "NONE", None, None)["p_discount_id"]
            if scope:
                db.call_procedure("sp_apply_discount", did, scope, first_id(style), None)
        except db.DbError as exc:
            say(f"  promo {name}: {exc}")
    say("Promos created.")

    # ------------------------------------------------------------ orders over the last two weeks
    rows = demo_rows()
    left = {r["product_id"]: r["current_stock"] for r in rows}
    plan = [0] * 5 + [1] * 4 + [d for d in range(2, 14) for _ in range(rng.randint(2, 3))]
    done = []
    for days_ago in plan:
        pool = [r for r in rows if left[r["product_id"]] > 0]
        picks = rng.sample(pool, k=min(len(pool), rng.choice([1, 1, 2, 2, 3])))
        items = []
        for r in picks:
            qty = min(rng.choice([1, 1, 1, 2]), left[r["product_id"]])
            items.append({"product_id": r["product_id"], "quantity": qty})
        delivery = rng.random() < 0.28
        cashier = rng.choice(cashiers)
        name = rng.choice(CUSTOMERS) if delivery or rng.random() < 0.3 else ""
        try:
            sale_id = db.call_procedure(
                "sp_create_sale", cashier, "Delivery" if delivery else "Walk-in", rng.choice(["Cash", "GCash"]),
                name, f"09{rng.randint(100000000, 999999999)}" if delivery else "",
                rng.choice(STREETS) if delivery else "", json.dumps(items), None)["p_sale_id"]
        except db.DbError as exc:
            say(f"  order skipped: {exc}")
            continue
        for it in items:
            left[it["product_id"]] -= it["quantity"]
        status = "Completed"
        if delivery:
            if days_ago >= 2 and rng.random() < 0.12:
                db.call_procedure("sp_update_order_status", cashier, sale_id, "Cancelled", "", "")
                status = "Cancelled"
            elif days_ago >= 1 or rng.random() < 0.4:
                db.call_procedure("sp_update_order_status", cashier, sale_id, "Out_for_Delivery",
                                  rng.choice(RIDERS), f"09{rng.randint(100000000, 999999999)}")
                status = "Out_for_Delivery"
                if days_ago >= 1:
                    db.call_procedure("sp_update_order_status", cashier, sale_id, "Completed", "", "")
                    status = "Completed"
            else:
                status = "Pending"
        if days_ago > 0:    # spread the history over the last two weeks
            when = datetime.combine(today - timedelta(days=days_ago), time(rng.randint(9, 20), rng.randint(0, 59)))
            _execute(db, "UPDATE thefad.sales SET sale_date = %s WHERE sale_id = %s", (when, sale_id))
            _execute(db, "UPDATE thefad.inventory_logs SET logged_at = %s WHERE sale_id = %s", (when, sale_id))
        done.append((sale_id, status, delivery, days_ago))
    say(f"Created {len(done)} orders.")

    # ------------------------------------------------------------ one refund
    target = next((d for d in done if d[1] == "Completed" and not d[2] and d[3] >= 1), None)
    if target:
        try:
            item = db.call_function("fn_sale_items", target[0])[0]
            db.call_procedure("sp_process_refund", admin_id, target[0], item["item_id"], 1, "Wrong size", "Cash", None)
            say(f"Refunded one item on order #{target[0]}.")
        except db.DbError as exc:
            say(f"  refund skipped: {exc}")

    # ------------------------------------------------------------ attendance and pay
    seed_attendance(db, rng, say, today)
    try:       # overtime an admin has allowed for tomorrow
        db.call_procedure("sp_allow_overtime", admin_id, cashiers[-1], today + timedelta(days=1), time(17, 0),
                          time(20, 0), 15, "Busy weekend", None)
    except db.DbError as exc:
        say(f"  overtime not added: {exc}")
    try:       # one cashier is on shift right now
        db.call_procedure("sp_clock_in", cashiers[0], time(9, 0), 15, Decimal(24), None)
    except db.DbError:
        pass

    # ------------------------------------------------------------ make the stock list interesting
    current = {r["product_id"]: r for r in demo_rows()}
    forest = [pid for pid, r in current.items() if r["product_name"] == "Classic Hoodie" and r["color"] == "Forest"]
    others = [pid for pid in current if pid not in forest]
    changes = {pid: 0 for pid in forest}                           # a whole color sold out
    changes.update({pid: rng.choice([1, 2, 3, 4]) for pid in rng.sample(others, 6)})   # low stock
    changes.update({pid: 0 for pid in rng.sample([p for p in others if p not in changes], 3)})
    for pid, qty in changes.items():
        try:
            db.call_procedure("sp_adjust_stock", admin_id, pid, qty, None)
        except db.DbError:
            pass
    say("Done. Open the shop and the dashboard.")
    return True


def main():
    ap = argparse.ArgumentParser(description="Add demo data to The Fad.")
    ap.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    ap.add_argument("--seed", type=int, default=7, help="random seed (same number gives the same data)")
    ap.add_argument("--attendance", action="store_true",
                    help="only add two weeks of attendance and start dates (for a database that already has the demo data)")
    args = ap.parse_args()
    if not args.yes:
        answer = input("This adds demo products, orders and staff to the database named in .env. Continue? [y/N] ")
        if answer.strip().lower() != "y":
            print("Cancelled.")
            return 1
    from app import create_app
    import db
    create_app()          # starts the database pool
    try:
        if args.attendance:
            seed_attendance(db, random.Random(args.seed))
        else:
            seed(db, random.Random(args.seed))
    except db.DbError as exc:
        print(f"Stopped: {exc}\nHave you run sql/setup_all.sql on this database?")
        return 1
    finally:
        db.pool.close()   # avoids a harmless "cannot join thread" message at exit
    return 0


if __name__ == "__main__":
    sys.exit(main())
