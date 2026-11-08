"""Staff management and attendance report (admin). Owner: Decembrano (USERS, DAILY_TIME_RECORD)."""
from datetime import date

from flask import (Blueprint, abort, flash, redirect, render_template,
                   request, session, url_for)

import db
from auth.decorators import role_required

bp = Blueprint("admin_staff", __name__, url_prefix="/admin/staff")


@bp.route("/")
@role_required("AD")
def index():
    try:
        staff = db.call_function("fn_list_staff")
    except db.DbError as exc:
        flash(str(exc), "error")
        staff = []
    return render_template("admin/staff.html", staff=staff)


def _fields():
    f = request.form
    base = [f.get(k, "").strip() for k in ("first_name", "last_name", "user_type", "email", "station")]
    start = f.get("hired_on", "").strip()
    return base + [date.fromisoformat(start) if start else None]


@bp.route("/new", methods=["GET", "POST"])
@role_required("AD")
def new():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        try:
            first, last, user_type, email, station, start = _fields()
            db.call_procedure("sp_create_staff", username, password, first, last,
                              user_type, email, station, start, None)
        except (ValueError, db.DbError) as exc:
            flash(str(exc), "error")
            return render_template("admin/staff_form.html", person=request.form, editing=False), 400
        flash(f"Created account {username}.", "success")
        return redirect(url_for("admin_staff.index"))
    return render_template("admin/staff_form.html", person={"user_type": "CA", "hired_on": date.today()}, editing=False)


@bp.route("/<int:user_id>/edit", methods=["GET", "POST"])
@role_required("AD")
def edit(user_id):
    if request.method == "POST":
        try:
            first, last, user_type, email, station, start = _fields()
            db.call_procedure("sp_update_staff", user_id, first, last, user_type, email, station, start)
        except (ValueError, db.DbError) as exc:
            flash(str(exc), "error")
            person = dict(request.form, username=request.form.get("username", ""))
            return render_template("admin/staff_form.html", person=person, editing=True, user_id=user_id), 400
        flash("Staff details saved.", "success")
        return redirect(url_for("admin_staff.index"))
    try:
        person = db.call_function("fn_get_staff", user_id, one=True)
    except db.DbError as exc:
        flash(str(exc), "error")
        return redirect(url_for("admin_staff.index"))
    if person is None:
        abort(404)
    return render_template("admin/staff_form.html", person=person, editing=True, user_id=user_id)


@bp.route("/<int:user_id>/active", methods=["POST"])
@role_required("AD")
def set_active(user_id):
    active = request.form.get("active") == "1"
    if not active and user_id == session.get("user_id"):
        flash("You cannot deactivate your own account.", "error")
        return redirect(url_for("admin_staff.index"))
    try:
        db.call_procedure("sp_set_staff_active", user_id, active)
        flash("Account reactivated." if active else "Account deactivated. They can no longer sign in.", "success")
    except db.DbError as exc:
        flash(str(exc), "error")
    return redirect(url_for("admin_staff.index"))
