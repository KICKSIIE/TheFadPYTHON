"""Admin audit viewer; changes are captured by database triggers."""
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
    if entity == "sales" and data.get("sale_id"):
        return f"#{data['sale_id']}"
    key = SUBJECTS.get(entity)
    value = data.get(key) if key else None
    return "" if value in (None, "") else str(value)


def _readable(rows, roles):
    """Human words only: the before/after payloads never leave this function."""
    out = []
    for row in rows:
        verb = ACTIONS.get(row["action"], row["action"].lower())
        noun = ENTITIES.get(row["entity"], row["entity"].replace("_", " "))
        details = f"{noun.capitalize()} {verb}"
        out.append({"time": row["occurred_at"],
                    "actor": row["actor"],
                    "approved_by": row["approved_by"],
                    "details": details,
                    "subject": _subject(row["entity"], row.get("after_data") or row.get("before_data")),
                    "badge": BADGES.get(row["action"], ""),
                    "role": roles.get(row["actor"], "")})
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
        roles = {s["username"]: ROLES.get(s["user_type"], s["user_type"]) for s in db.call_function("fn_list_staff")}
    except db.DbError:
        roles = {}
    return render_template("audit.html", rows=_readable(rows[:50], roles), more=len(rows) > 50, page=page,
                           entities=ENTITIES,
                           filters=dict(start=start.isoformat(), end=end.isoformat(), actor=actor, entity=entity, action=action))
