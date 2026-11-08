"""Shift schedule (saved by an admin in the database) and stock defaults (config.py)."""
from flask import current_app, g

import db


def shift_rules():
    """Regular shift time in / time out / grace, from the database; config.py values until one is saved."""
    if "shift_rules" in g:
        return g.shift_rules
    c = current_app.config
    r = {"shift_start": c["SHIFT_START"], "shift_end": c["SHIFT_END"], "grace": c["GRACE_MINUTES"],
         "shift_hours": c["SHIFT_HOURS"], "max_hours": c["MAX_SHIFT_HOURS"], "work_days": c["WORK_DAYS"]}
    try:
        row = db.call_function("fn_get_shift_setting", one=True)
        if row:
            r.update(shift_start=row["shift_start"], shift_end=row["shift_end"], grace=row["grace_minutes"],
                     shift_hours=row["shift_hours"])
    except db.DbError:
        pass
    g.shift_rules = r
    return r


def low_stock_default():
    return current_app.config["LOW_STOCK_DEFAULT"]
