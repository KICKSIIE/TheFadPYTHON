"""Promos list for staff (read only). Owner: Po (DISCOUNT)."""
from flask import Blueprint, flash, render_template

import db
from auth.decorators import login_required

bp = Blueprint("promos", __name__, url_prefix="/promos")


@bp.route("/")
@login_required
def index():
    try:
        rows = [r for r in db.call_function("fn_list_discounts") if r["status"] == "Active"]
    except db.DbError as exc:
        flash(str(exc), "error")
        rows = []
    return render_template("promos.html", rows=rows)
