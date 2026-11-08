"""Admin audit viewer; changes are captured by database triggers."""
from datetime import date, timedelta

from flask import Blueprint, flash, render_template, request

import db
from rules import shop_now
from auth.decorators import role_required

bp = Blueprint("audit", __name__, url_prefix="/admin/audit")


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
    return render_template("audit.html", rows=rows[:50], more=len(rows)>50, page=page,
                           filters=dict(start=start.isoformat(), end=end.isoformat(), actor=actor, entity=entity, action=action))
