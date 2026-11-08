from functools import wraps

from flask import abort, flash, g, redirect, request, session, url_for

import db


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Sign in to continue.", "info")
            return redirect(url_for("auth.login", next=request.path))
        if not all(session.get(k) for k in ("username", "user_type")):   # stale cookie from an older version
            session.clear()
            flash("Please sign in again.", "info")
            return redirect(url_for("auth.login", next=request.path))
        try:
            access = db.call_function("fn_staff_access", session["user_id"], one=True)
        except db.DbError:
            abort(503, description="Attendance cannot be verified. Try again shortly.")
        if not access or not access["active"]:
            session.clear()
            return redirect(url_for("auth.login"))
        if access.get("user_type"):
            session["user_type"] = access["user_type"]
        g.staff_access = access
        exempt = request.endpoint in {"attendance.index", "attendance.clock_in", "attendance.clock_out",
                                     "attendance.overtime_in", "attendance.overtime_out", "auth.account"}
        if not exempt and not access["allowed"]:
            flash("Clock in to a scheduled shift or approved overtime before using the staff system.", "info")
            return redirect(url_for("attendance.index"))
        return view(*args, **kwargs)

    return wrapped


def role_required(*roles):
    """Usage: @role_required("AD")  (also checks that the user is signed in)."""

    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if session.get("user_type") not in roles:
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator
