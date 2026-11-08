"""Payroll estimate from attendance (admin). Gross pay only: hours x hourly rate, overtime at the overtime rate."""
import calendar
import csv
import io
from datetime import date

from flask import (Blueprint, Response, flash, render_template, request)

import db
from auth.decorators import role_required
from rules import shift_rules, shop_now

bp = Blueprint("payroll", __name__, url_prefix="/admin/payroll")


def _periods(today):
    """Semi-monthly pay periods: 1st to 15th and 16th to end of month."""
    last = calendar.monthrange(today.year, today.month)[1]
    first_half = (today.replace(day=1), today.replace(day=15))
    second_half = (today.replace(day=16), today.replace(day=last))
    this = first_half if today.day <= 15 else second_half
    if today.day <= 15:                                    # previous period = 16th to end of last month
        py, pm = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
        prev = (date(py, pm, 16), date(py, pm, calendar.monthrange(py, pm)[1]))
    else:
        prev = first_half
    return [("This period", *this), ("Last period", *prev),
            ("This month", today.replace(day=1), today.replace(day=last))]


def _load():
    r = dict(shift_rules(), ot=1)
    today = shop_now().date()
    presets = _periods(today)
    try:
        start = date.fromisoformat(request.args.get("start") or presets[0][1].isoformat())
        end = date.fromisoformat(request.args.get("end") or presets[0][2].isoformat())
    except ValueError:
        flash("Enter dates as year-month-day.", "error")
        start, end = presets[0][1], presets[0][2]
    rows, absent, open_shifts = [], {}, 0
    try:
        rows = db.call_function("fn_payroll", start, end)
        board = db.call_function("fn_attendance_board", start, end, None, r["work_days"])
        for b in board:
            if b["status"] == "Absent":
                absent[b["user_id"]] = absent.get(b["user_id"], 0) + 1
            elif b["dtr_id"] and b["time_out"] is None:
                open_shifts += 1
    except db.DbError as exc:
        flash(str(exc), "error")
    lines = [dict(x, absent_days=absent.get(x["user_id"], 0)) for x in rows]
    totals = {k: sum(x[k] for x in lines) for k in ("regular_hours", "overtime_hours", "regular_pay", "overtime_pay", "gross_pay")}
    return start, end, presets, lines, totals, open_shifts, r


@bp.route("/")
@role_required("AD")
def index():
    start, end, presets, lines, totals, open_shifts, r = _load()
    return render_template("admin/payroll.html", start=start, end=end, presets=presets, lines=lines,
                           totals=totals, open_shifts=open_shifts, shift_hours=r["shift_hours"], ot=r["ot"])


@bp.route("/download")
@role_required("AD")
def download():
    start, end, _, lines, totals, _, _ = _load()
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Name", "Hourly rate", "Days worked", "Late days", "Absent days", "Regular hours",
                "Overtime hours", "Regular pay", "Overtime pay", "Gross pay"])
    for x in lines:
        w.writerow([x["full_name"], x["hourly_rate"], x["days_worked"], x["late_days"], x["absent_days"],
                    x["regular_hours"], x["overtime_hours"], x["regular_pay"], x["overtime_pay"], x["gross_pay"]])
    w.writerow(["Total", "", "", "", "", totals["regular_hours"], totals["overtime_hours"],
                totals["regular_pay"], totals["overtime_pay"], totals["gross_pay"]])
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=payroll_{start}_{end}.csv"})
