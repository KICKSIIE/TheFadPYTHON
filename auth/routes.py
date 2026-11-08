from flask import (Blueprint, current_app, flash, redirect, render_template,
                   request, session, url_for)

import db

bp = Blueprint("auth", __name__)


def _safe_next(target):
    return bool(target) and target.startswith("/") and not target.startswith("//") and "\\" not in target


def _start_session(user):
    session.clear()  # new session on login
    session.permanent = True
    session["user_id"] = user["user_id"]
    session["username"] = user["username"]
    session["user_type"] = user["user_type"]
    full = f"{user.get('first_name') or ''} {user.get('last_name') or ''}".strip()
    session["display_name"] = full or user["username"]


@bp.route("/staff")
def staff():
    """Short address for staff. The public shop never links here."""
    return redirect(url_for("dashboard.index" if "user_id" in session else "auth.login"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("dashboard.index"))

    nxt = request.args.get("next") or request.form.get("next") or ""

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not username or not password:
            flash("Enter both your username and password.", "error")
            return render_template("login.html", next=nxt, username=username), 400

        try:
            user = db.call_function("fn_login_user", username, password, one=True)
        except db.DbError as exc:
            flash(str(exc), "error")
            return render_template("login.html", next=nxt, username=username), 503

        if user is None:
            flash("Incorrect username or password.", "error")
            return render_template("login.html", next=nxt, username=username), 401

        if current_app.config["MFA_ENABLED"]:
            session.clear()
            session["pending_user"] = {k: user[k] for k in
                                       ("user_id", "username", "first_name", "last_name", "user_type")}
            return redirect(url_for("auth.verify_otp"))

        _start_session(user)
        return redirect(nxt if _safe_next(nxt) else url_for("dashboard.index"))

    return render_template("login.html", next=nxt, username="")


@bp.route("/verify-otp", methods=["GET", "POST"])
def verify_otp():
    # PHASE 2 TODO: call generate_otp / verify_otp routines, then _start_session(pending).
    if "pending_user" not in session:
        return redirect(url_for("auth.login"))
    flash("The OTP step is not built yet (phase 2).", "info")
    return render_template("login.html", next="", username="")


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("auth.login"))
