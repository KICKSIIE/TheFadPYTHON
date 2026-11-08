from functools import wraps

from flask import abort, flash, redirect, request, session, url_for


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
