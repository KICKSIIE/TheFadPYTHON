"""Readable audit history with an explicit allowlist of safe business fields."""
from datetime import date, timedelta

from flask import Blueprint, flash, render_template, request

import db
from rules import shop_now
from auth.decorators import role_required

bp = Blueprint("audit", __name__, url_prefix="/admin/audit")

# Readable nouns for the record a change belongs to.
ENTITIES = {
    "product": "product",
    "category": "category",
    "users": "staff account",
    "discount": "promo",
    "sales": "sale",
    "sale_item": "sale item",
    "refund": "refund",
    "inventory_logs": "stock movement",
    "daily_time_record": "attendance record",
    "shift_setting": "shift schedule",
    "overtime_permit": "overtime",
    "management_pin": "approval PIN",
    "product_photo": "product photo link",
    "product_image": "product photo",
}
ACTIONS = {"INSERT": "created", "UPDATE": "updated", "DELETE": "deleted", "SET_PIN": "set"}
BADGES = {"INSERT": "ok", "UPDATE": "", "DELETE": "warn", "SET_PIN": "dark"}
ROLES = {"AD": "Admin", "CA": "Cashier"}
# A short, non-private name for the record so the line reads like a sentence.
SUBJECTS = {"product": "product_name", "category": "category_name", "discount": "discount_name",
            "users": "username", "refund": "refund_id"}


def _subject(entity, data):
    if not isinstance(data, dict):
        return ""
    if entity == "product" and data.get("product_name"):
        name = str(data["product_name"])
        if data.get("color"):
            name += f" - {data['color']}"
        if data.get("size"):
            name += f" ({data['size']})"
        return name
    if entity in {"sale_item", "refund", "inventory_logs"}:
        parts = []
        if data.get("sale_id"):
            parts.append(f"Receipt #{data['sale_id']}")
        if data.get("product_id"):
            parts.append(f"Product #{data['product_id']}")
        return " · ".join(parts)
    if entity == "sales" and data.get("sale_id"):
        return f"#{data['sale_id']}"
    key = SUBJECTS.get(entity)
    value = data.get(key) if key else None
    return "" if value in (None, "") else str(value)


# Unknown fields stay private until explicitly reviewed for display.
FIELDS = {
    "product_photo": "product_id image_id sort_order",
    "product_image": "image_id mime_type uploaded_at",
    "product": "product_id product_name description base_price current_price current_stock category_id discount_id color size is_active",
    "category": "category_id category_name display_order",
    "users": "user_id username first_name middle_name last_name user_type station inventory_section hourly_rate email hired_on is_active isActive",
    "discount": "discount_id discount_name discount_percentage start_date end_date",
    "sales": "sale_id user_id customer_name customer_contact subtotal discount_amount total_amount delivery_address payment_method order_status rider_service ride_service rider_contact sale_date sales_date fulfillment_type",
    "sale_item": "item_id sale_item_id sale_id product_id quantity base_price unit_price_at_sale discount_id quantity_refunded",
    "refund": "refund_id sale_id item_id sale_item_id quantity_refunded refund_amount refund_method quantity amount method reason processed_by refund_date refunded_at",
    "inventory_logs": "log_id product_id sale_id user_id transaction_type quantity_changed balance_after logged_at note",
    "daily_time_record": "dtr_id user_id time_in time_out total_hours overtime_hours status shift_type note permit_id scheduled_end",
    "shift_setting": "shift_start shift_end grace_minutes updated_at",
    "overtime_permit": "permit_id user_id work_date start_time end_time grace_minutes note dtr_id created_by",
}
MONEY_FIELDS = {"base_price", "current_price", "unit_price_at_sale", "subtotal", "discount_amount", "total_amount", "amount", "refund_amount", "hourly_rate"}


def _value(key, value):
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if key == "user_type":
        return ROLES.get(value, str(value))
    if key in MONEY_FIELDS:
        try:
            from decimal import Decimal
            return f"₱{Decimal(str(value)):,.2f}"
        except (ValueError, ArithmeticError):
            return str(value)
    # Never serialize nested payloads, which could contain private fields.
    if isinstance(value, (dict, list)):
        return "[Structured value]"
    return str(value).replace("_", " ") if key in {"order_status", "shift_type"} else str(value)


def _readable(rows, staff):
    out = []
    for row in rows:
        entity, action = row["entity"], row["action"]
        before = row.get("before_data") if isinstance(row.get("before_data"), dict) else {}
        after = row.get("after_data") if isinstance(row.get("after_data"), dict) else {}
        changes = []
        for key in FIELDS.get(entity, "").split():
            if key not in before and key not in after:
                continue
            if action == "UPDATE" and before.get(key) == after.get(key):
                continue
            if action != "UPDATE" and before.get(key) is None and after.get(key) is None:
                continue
            changes.append({"field": key.replace("_", " ").capitalize(),
                            "before": _value(key, before.get(key)), "after": _value(key, after.get(key))})
        member = staff.get(row["actor"], {})
        # Old callers may provide only role strings.
        if isinstance(member, str):
            member = {"role": member}
        verb = ACTIONS.get(action, action.lower())
        noun = ENTITIES.get(entity, entity.replace("_", " "))
        details = f"{noun.capitalize()} {verb}"
        if entity == "sales":
            details = {"INSERT": "Receipt created", "UPDATE": "Order updated", "DELETE": "Sale deleted"}.get(action, details)
        if entity == "users" and action == "UPDATE" and not changes:
            details = "Account security updated"
        out.append({"time": row["occurred_at"], "actor": row["actor"],
                    "name": row.get("actor_name") or member.get("name") or row["actor"],
                    "approved_by": row.get("approved_by"), "details": details,
                    "subject": _subject(entity, after or before), "changes": changes,
                    "badge": BADGES.get(action, ""),
                    "role": ROLES.get(row.get("actor_role"), row.get("actor_role")) or member.get("role", "System" if row["actor"] == "system" else "Unavailable")})
    return out


@bp.route("/")
@role_required("AD")
def index():
    today = shop_now().date()
    try:
        start = date.fromisoformat(request.args.get("start") or (today - timedelta(days=6)).isoformat())
        end = date.fromisoformat(request.args.get("end") or today.isoformat())
        if end < start:
            raise ValueError()
    except ValueError:
        flash("Choose a valid date range.", "error")
        start, end = today - timedelta(days=6), today
    page = max(1, request.args.get("page", 1, type=int))
    actor = request.args.get("actor", "").strip()[:100]
    entity = request.args.get("entity", "").strip()[:60]
    action = request.args.get("action", "").strip()
    try:
        rows = db.call_function("fn_audit_logs", start, end, actor or None, entity or None, action or None, (page - 1) * 50)
    except db.DbError as exc:
        flash(str(exc), "error")
        rows = []
    try:
        roles = {s["username"]: {"role": ROLES.get(s["user_type"], s["user_type"]),
                  "name": " ".join(str(s.get(k) or "") for k in ("first_name", "last_name")).strip()}
                 for s in db.call_function("fn_list_staff")}
    except db.DbError:
        roles = {}
    return render_template("audit.html", rows=_readable(rows[:50], roles), more=len(rows) > 50, page=page,
                           entities=ENTITIES,
                           filters=dict(start=start.isoformat(), end=end.isoformat(), actor=actor, entity=entity, action=action))
