"""
All database access goes through this file.

Rule for the team: the web app never runs INSERT / UPDATE / DELETE on tables.
It only calls stored routines:

    db.call_function("fn_view_discounts", "Active")          -> list of dict rows
    db.call_function("fn_login_user", user, pw, one=True)    -> one dict row or None
    db.call_procedure("sp_create_discount", name, 20, start, end, "NONE", None, None)
                                                              -> dict of INOUT values

Phase 2 / 3 hooks (RLS, audit trigger, restricted role) go in _prepare() only,
so no other file has to change when security is switched on.
"""
import atexit
import re
from contextlib import contextmanager

import psycopg
from flask import has_request_context, session
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

pool = None
SCHEMA = "thefad"
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class DbError(Exception):
    """Raised for any database error. str(e) is safe to show to the user."""


def init_db(app):
    global pool, SCHEMA
    SCHEMA = app.config["DB_SCHEMA"]
    pool = ConnectionPool(
        conninfo=app.config["DATABASE_URL"],
        min_size=1,
        max_size=10,
        timeout=5,
        kwargs={
            "row_factory": dict_row,
            "options": f"-c search_path={SCHEMA},public",
        },
        open=True,
    )
    atexit.register(pool.close)   # close cleanly when the program exits


def _check_ident(name):
    if not _IDENT.match(name):
        raise ValueError(f"Invalid routine name: {name!r}")


def _prepare(cur):
    """Runs at the start of every transaction."""
    user = session.get("username") if has_request_context() else None
    if user:
        # Lets the audit trigger (phase 3) see the app-level user.
        cur.execute("SELECT set_config('app.current_user', %s, true)", (user,))
    # PHASE 2 TODO: SET LOCAL ROLE fad_admin / fad_cashier based on session user_type
    # PHASE 2 TODO: set_config('app.current_shift', <shift>, true)


@contextmanager
def _cursor():
    with pool.connection() as conn:  # commits on success, rolls back on error
        with conn.cursor() as cur:
            _prepare(cur)
            yield cur


def _message(exc):
    diag = getattr(exc, "diag", None)
    if diag is not None and diag.message_primary:
        return diag.message_primary
    return "The database could not complete the request."


def call_function(name, *args, one=False):
    _check_ident(name)
    marks = ", ".join(["%s"] * len(args))
    sql = f"SELECT * FROM {SCHEMA}.{name}({marks})"
    try:
        with _cursor() as cur:
            cur.execute(sql, args)
            rows = cur.fetchall()
    except (psycopg.Error, Exception) as exc:
        if isinstance(exc, psycopg.Error):
            raise DbError(_message(exc)) from exc
        raise DbError("Cannot reach the database. Try again in a moment.") from exc
    if one:
        return rows[0] if rows else None
    return rows


def call_procedure(name, *args):
    """CALL a stored procedure. Pass None for INOUT params. Returns a dict of INOUT values."""
    _check_ident(name)
    marks = ", ".join(["%s"] * len(args))
    sql = f"CALL {SCHEMA}.{name}({marks})"
    try:
        with _cursor() as cur:
            cur.execute(sql, args)
            return cur.fetchone() if cur.description else None
    except (psycopg.Error, Exception) as exc:
        if isinstance(exc, psycopg.Error):
            raise DbError(_message(exc)) from exc
        raise DbError("Cannot reach the database. Try again in a moment.") from exc


def ping():
    try:
        with _cursor() as cur:
            cur.execute("SELECT 1 AS ok")
            return cur.fetchone()["ok"] == 1
    except Exception:
        return False
