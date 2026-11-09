"""Runs seed_demo.seed() against an in-memory stand-in for the database layer."""
import json
import random
from decimal import Decimal
from contextlib import contextmanager
from datetime import date, time, timedelta

import seed_demo


class FakeDB:
    class DbError(Exception):
        pass

    def __init__(self):
        self.categories, self.rows, self.photos, self.sales, self.sql, self.calls = {}, [], [], [], [], []
        self.shifts_args = []
        self.staff = [dict(user_id=1, username="dev_admin", user_type="AD", is_active=True),
                      dict(user_id=2, username="dev_cashier", user_type="CA", is_active=True)]
        self.next = 100
        outer = self

        class Conn:
            def execute(self, sql, params=None):
                outer.sql.append((sql, params))
                return type("Result", (), {"fetchone": staticmethod(lambda: {"permit_id": outer._id()})})()

        @contextmanager
        def connection():
            yield Conn()
        self.pool = type("Pool", (), {"connection": staticmethod(connection)})()

    def _id(self):
        self.next += 1
        return self.next

    def call_function(self, name, *args, one=False):
        if name == "fn_list_staff":
            return self.staff
        if name == "fn_list_categories":
            return [dict(category_id=i, category_name=n) for n, i in self.categories.items()]
        if name == "fn_list_products":
            return [r for r in self.rows if args[1] is None or r["category_id"] == args[1]]
        if name == "fn_sale_items":
            return [dict(item_id=1)]
        if name == "fn_attendance_board":
            start, end = args[0], args[1]
            out, d = [], start
            while d <= end:
                if d.isoweekday() <= 6:
                    for u in self.staff:
                        out.append(dict(dtr_id=None, user_id=u["user_id"], work_day=d, shift_type="Regular", status="Absent"))
                d += timedelta(days=1)
            return out
        raise AssertionError(name)

    def call_procedure(self, name, *args):
        self.calls.append(name)
        if name == "sp_create_category":
            self.categories[args[0]] = self._id()
            return {"p_category_id": self.categories[args[0]]}
        if name == "sp_create_product":
            pname, _, cat, _, sizes, colors = args[:6]
            if any(r["product_name"] == pname for r in self.rows):
                raise self.DbError(f"{pname} already exists.")
            sizes = [s.strip() for s in sizes.split(",") if s.strip()] or [None]
            colors = [c.strip() for c in colors.split(",") if c.strip()] or [None]
            first = None
            for c in colors:
                for s in sizes:
                    pid = self._id()
                    first = first or pid
                    self.rows.append(dict(product_id=pid, product_name=pname, color=c, size=s, current_stock=0,
                                          category_id=cat, is_active=True))
            return {"p_product_id": first}
        if name == "sp_add_product_photo":
            _, mime, data, apply_all, _ = args
            assert mime == "image/png" and data[:8] == b"\x89PNG\r\n\x1a\n" and apply_all is True
            self.photos.append(args[0])
            return {"p_image_id": self._id()}
        row = lambda pid: next(r for r in self.rows if r["product_id"] == pid)
        if name == "sp_stock_in":
            row(args[1])["current_stock"] += args[2]
            return {"p_balance": 0}
        if name == "sp_adjust_stock":
            if row(args[1])["current_stock"] == args[2]:
                raise self.DbError("Stock is already that number.")
            row(args[1])["current_stock"] = args[2]
            return {"p_balance": args[2]}
        if name == "sp_create_staff":
            if any(s["username"] == args[0] for s in self.staff):
                raise self.DbError("That username or email is already in use.")
            assert len(args) == 9 and isinstance(args[7], date)   # start date
            uid = self._id()
            self.staff.append(dict(user_id=uid, username=args[0], user_type=args[4], is_active=True))
            return {"p_user_id": uid}
        if name == "sp_create_discount":
            return {"p_discount_id": self._id()}
        if name == "sp_apply_discount":
            return {"p_products_updated": 1}
        if name == "sp_create_sale":
            user, fulfil, pay, cname, contact, addr, items, _ = args
            if fulfil == "Delivery" and not (cname and contact and addr):
                raise self.DbError("Delivery orders need the customer name, contact number and address.")
            items = json.loads(items)
            if not items:
                raise self.DbError("Add at least one item to the cart.")
            for it in items:
                if row(it["product_id"])["current_stock"] < it["quantity"]:
                    raise self.DbError("Not enough stock.")
            for it in items:
                row(it["product_id"])["current_stock"] -= it["quantity"]
            self.sales.append((user, fulfil, items))
            return {"p_sale_id": self._id()}
        if name == "sp_allow_overtime":
            assert len(args) == 8 and args[3] < args[4]          # starts before it ends
            return {"p_permit_id": self._id()}
        if name == "sp_clock_in":
            assert len(args) == 5
        if name in ("sp_update_order_status", "sp_process_refund", "sp_clock_in"):
            return {"p_refund_id": 1, "p_dtr_id": 1}
        raise AssertionError(name)


def test_seed_builds_a_lively_shop():
    db = FakeDB()
    assert seed_demo.seed(db, random.Random(7), say=lambda *_: None, today=date(2026, 11, 5)) is True

    names = {r["product_name"] for r in db.rows}
    assert len(names) == len(seed_demo.PRODUCTS)
    assert len({(r["product_name"], r["color"]) for r in db.rows}) == sum(len(p["colors"]) for p in seed_demo.PRODUCTS)
    assert len(db.photos) == 3 * sum(len(p["colors"]) for p in seed_demo.PRODUCTS)     # 3 photos per color
    assert len(db.sales) >= 25 and all(r["current_stock"] >= 0 for r in db.rows)       # orders never oversell
    stocks = [r["current_stock"] for r in db.rows]
    assert 0 in stocks and any(1 <= s <= 4 for s in stocks)                              # sold-out and low-stock items
    assert not any(r["current_stock"] for r in db.rows if r["product_name"] == "Classic Hoodie" and r["color"] == "Forest")
    assert any("UPDATE thefad.sales" in q for q, _ in db.sql) and any("daily_time_record" in q for q, _ in db.sql)
    shifts = [p for q, p in db.sql if "INSERT INTO thefad.daily_time_record" in q]
    assert len(shifts) > 40 and any(p[4] == "Late" for p in shifts)                       # two weeks for everyone, some late
    assert all(p[3] <= 24 for p in shifts)                                                 # never over 24 hours
    assert any("hired_on" in q for q, _ in db.sql) and not any("hourly_rate" in q for q, _ in db.sql)
    permits = [q for q, _ in db.sql if "INSERT INTO thefad.overtime_permit" in q]
    ot_rows = [p for q, p in db.sql if "INSERT INTO thefad.daily_time_record" in q and "Overtime" in p]
    assert permits and ot_rows and all(p[3] <= 3 for p in ot_rows)                      # overtime stays within the allowed 3 hours
    assert all(p[2].time() <= time(20, 0) for p in ot_rows)                              # and never ends after the permit's time out
    assert "sp_allow_overtime" in db.calls                                             # and one is allowed for tomorrow
    assert "sp_process_refund" in db.calls and db.calls.count("sp_create_discount") == 4
    assert any(s[1] == "Delivery" for s in db.sales)


def test_seed_twice_does_not_duplicate():
    db = FakeDB()
    seed_demo.seed(db, random.Random(7), say=lambda *_: None)
    before = (len(db.rows), len(db.sales))
    assert seed_demo.seed(db, random.Random(7), say=lambda *_: None) is False
    assert (len(db.rows), len(db.sales)) == before


def test_attendance_only_option_repairs_an_existing_database():
    db = FakeDB()
    n = seed_demo.seed_attendance(db, random.Random(3), say=lambda *_: None, today=date(2026, 11, 6))
    assert n > 15 and any("UPDATE thefad.users SET hired_on" in q for q, _ in db.sql)
