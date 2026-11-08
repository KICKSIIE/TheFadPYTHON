"""Clock in/out and overtime for the signed-in user; admins also manage everyone, overtime and the schedule."""
from datetime import date, datetime, time, timedelta

from flask import (Blueprint, abort, flash, redirect, render_template,
                   request, session, url_for, g)

import db
import attendance_store
from auth.decorators import login_required, role_required
from rules import shift_rules, shop_now

bp = Blueprint("attendance", __name__, url_prefix="/attendance")
FMT = "%Y-%m-%dT%H:%M"


def _hours(delta):
    return delta.total_seconds() / 3600


def _overtime_state(permit, regular_open, now):
    """What the overtime card should offer today."""
    start = datetime.combine(permit["work_date"], permit["start_time"])
    end = datetime.combine(permit["work_date"], permit["end_time"])
    grace_until = start + timedelta(minutes=permit["grace_minutes"])
    if permit["dtr_id"] and permit["time_out"] is None:
        state = "open"
    elif permit["dtr_id"]:
        state = "done"
    elif now >= end:
        state = "over"
    elif now < start:
        state = "early"
    elif regular_open:
        state = "wait"
    else:
        state = "ready"
    return {"state": state, "start": start, "end": end, "grace_until": grace_until,
            "late": state == "ready" and now > grace_until}


@bp.route("/")
@login_required
def index():
    r = shift_rules()
    shift = float(r["shift_hours"])
    rows = g.staff_access["rows"]
    permits = g.staff_access["permits"]
    now = g.staff_access["shop_now"]
    open_row = next((x for x in rows if x["shift_type"] == "Regular" and x["time_out"] is None), None)
    st = {}
    if open_row:
        worked = _hours(now - open_row["time_in"])
        st = {"worked": worked, "pct": min(100, max(0, round(worked / shift * 100))),
              "opens_at": open_row.get("scheduled_end") or g.staff_access["shift_end"]}
    today_done = any(x["shift_type"] == "Regular" and x["time_in"].date() == now.date() for x in rows)
    today_permit = next((p for p in permits if p["work_date"] == now.date()), None)
    ot = _overtime_state(today_permit, open_row is not None, now) if today_permit else None
    upcoming = [p for p in permits if p["work_date"] > now.date()]
    return render_template("attendance.html", rows=rows, open_row=open_row, st=st, shift=shift,
                           today_done=today_done, permit=today_permit, ot=ot, upcoming=upcoming, tab="mine", can_clock_in=g.staff_access["can_clock_in"],
                           shift_end=g.staff_access["shift_end"])


@bp.route("/clock-in", methods=["POST"])
@login_required
def clock_in():
    try:
        attendance_store.clock_in(session["user_id"])
        flash("Clocked in.", "success")
    except db.DbError as exc:
        flash(str(exc), "error")
    return redirect(url_for("attendance.index"))


@bp.route("/clock-out", methods=["POST"])
@login_required
def clock_out():
    rows = g.staff_access['rows']
    today = g.staff_access['shop_now'].date()
    if any(r['shift_type'] == 'Regular' and r['time_in'].date() == today and r['time_out'] for r in rows):
        flash('Your shift has closed.', 'success')
    else:
        flash('Your shift closes automatically at the scheduled end.', 'info')
    return redirect(url_for("attendance.index"))


@bp.route("/overtime-in", methods=["POST"])
@login_required
def overtime_in():
    try:
        attendance_store.clock_in(session["user_id"], overtime=True)
        flash("Overtime started.", "success")
    except db.DbError as exc:
        flash(str(exc), "error")
    return redirect(url_for("attendance.index"))


@bp.route("/overtime-out", methods=["POST"])
@login_required
def overtime_out():
    flash('Overtime closes automatically at the approved end.', 'info')
    return redirect(url_for("attendance.index"))


# ------------------------------------------------------------------ admin: everyone
def _range(default_back=6, default_ahead=0):
    today = shop_now().date()
    try:
        start = date.fromisoformat(request.args.get("start") or (today - timedelta(days=default_back)).isoformat())
        end = date.fromisoformat(request.args.get("end") or (today + timedelta(days=default_ahead)).isoformat())
    except ValueError:
        flash("Enter dates as year-month-day.", "error")
        start, end = today - timedelta(days=default_back), today + timedelta(days=default_ahead)
    return start, end


def _active_staff():
    return [s for s in db.call_function("fn_list_staff") if s["is_active"]]


@bp.route("/everyone")
@role_required("AD")
def everyone():
    r = shift_rules()
    start, end = _range()
    user_id = request.args.get("user_id", type=int)
    try:
        rows = db.call_function("fn_attendance_board", start, end, user_id, r["work_days"])
        staff = _active_staff()
    except db.DbError as exc:
        flash(str(exc), "error")
        rows, staff = [], []
    regular = [x for x in rows if x["shift_type"] == "Regular"]
    counts = {k: sum(1 for x in regular if x["status"] == k) for k in ("Present", "Late", "Absent")}
    hours = sum((x["total_hours"] or 0) for x in regular)
    overtime = sum((x["overtime_hours"] or 0) for x in rows)
    today = shop_now().date()
    presets = [("Today", today, today), ("Last 7 days", today - timedelta(days=6), today),
               ("This month", today.replace(day=1), today)]
    return render_template("attendance_everyone.html", rows=rows, staff=staff, start=start, end=end,
                           user_id=user_id, counts=counts, hours=hours, overtime=overtime,
                           presets=presets, tab="everyone")


def _parse_shift_form():
    f = request.form
    try:
        return (int(f.get("user_id", "")), datetime.fromisoformat(f.get("time_in", "")),
                datetime.fromisoformat(f.get("time_out", "")), f.get("note", "").strip())
    except ValueError:
        raise ValueError("Choose a staff member and enter both times.")


def _shift_page(shift, staff, status=200):
    return render_template("shift_form.html", shift=shift, staff=staff, tab="everyone"), status


def _save_shift(dtr_id, user_id, tin, tout, note):
    r = shift_rules()
    db.call_procedure("sp_save_shift", dtr_id, user_id, tin, tout, note, r["shift_start"], r["grace"],
                      r["shift_hours"], r["max_hours"], None)


@bp.route("/shift", methods=["GET", "POST"])
@role_required("AD")
def new_shift():
    staff = _active_staff()
    if request.method == "POST":
        try:
            user_id, tin, tout, note = _parse_shift_form()
            _save_shift(None, user_id, tin, tout, note)
            flash("Shift added.", "success")
            return redirect(url_for("attendance.everyone", start=tin.date().isoformat(), end=tin.date().isoformat()))
        except (ValueError, db.DbError) as exc:
            flash(str(exc), "error")
            return _shift_page(request.form, staff, 400)
    day = request.args.get("date") or shop_now().date().isoformat()
    r = shift_rules()
    shift = {"user_id": request.args.get("user_id", type=int), "note": "",
             "time_in": f"{day}T{r['shift_start'].strftime('%H:%M')}",
             "time_out": f"{day}T{r['shift_end'].strftime('%H:%M')}"}
    return _shift_page(shift, staff)


@bp.route("/shift/<int:dtr_id>", methods=["GET", "POST"])
@role_required("AD")
def edit_shift(dtr_id):
    staff = _active_staff()
    if request.method == "POST":
        try:
            user_id, tin, tout, note = _parse_shift_form()
            _save_shift(dtr_id, user_id, tin, tout, note)
            flash("Shift saved.", "success")
            return redirect(url_for("attendance.everyone", start=tin.date().isoformat(), end=tin.date().isoformat()))
        except (ValueError, db.DbError) as exc:
            flash(str(exc), "error")
            return _shift_page(dict(request.form, dtr_id=dtr_id), staff, 400)
    row = db.call_function("fn_get_shift", dtr_id, one=True)
    if row is None:
        abort(404)
    shift = {"dtr_id": dtr_id, "user_id": row["user_id"], "note": row["note"] or "",
             "time_in": row["time_in"].strftime(FMT),
             "time_out": row["time_out"].strftime(FMT) if row["time_out"] else ""}
    return _shift_page(shift, staff)


# ------------------------------------------------------------------ admin: overtime
@bp.route("/overtime")
@role_required("AD")
def overtime():
    start, end = _range(default_back=7, default_ahead=30)
    try:
        rows = db.call_function("fn_list_overtime", start, end)
    except db.DbError as exc:
        flash(str(exc), "error")
        rows = []
    return render_template("overtime.html", rows=rows, start=start, end=end, tab="overtime")


def _overtime_fields():
    f = request.form
    try:
        grace = f.get("grace_minutes", "").strip()
        return (time.fromisoformat(f.get("start_time", "")), time.fromisoformat(f.get("end_time", "")),
                int(grace) if grace else None, f.get("note", "").strip())
    except ValueError:
        raise ValueError("Enter the overtime time in and time out, and a whole number for the grace period.")


@bp.route("/overtime/new", methods=["GET", "POST"])
@role_required("AD")
def new_overtime():
    r = shift_rules()
    staff = _active_staff()
    if request.method == "POST":
        try:
            start, end, grace, note = _overtime_fields()
            work_date = date.fromisoformat(request.form.get("work_date", ""))
            attendance_store.save_overtime(session["user_id"], int(request.form.get("user_id", "")),
                                           work_date, start, end, grace, note)
            flash("Overtime allowed.", "success")
            return redirect(url_for("attendance.overtime"))
        except (ValueError, db.DbError) as exc:
            flash(str(exc) if isinstance(exc, db.DbError) or "grace" in str(exc) else
                  "Choose a staff member and a date, and enter the overtime times.", "error")
            return render_template("overtime_form.html", permit=request.form, staff=staff, editing=False,
                                   default_grace=r["grace"], tab="overtime"), 400
    permit = {"work_date": shop_now().date().isoformat(), "start_time": r["shift_end"].strftime("%H:%M"),
              "end_time": (datetime.combine(shop_now().date(), r["shift_end"]) + timedelta(hours=2)).strftime("%H:%M"),
              "grace_minutes": r["grace"], "note": ""}
    return render_template("overtime_form.html", permit=permit, staff=staff, editing=False,
                           default_grace=r["grace"], tab="overtime")


@bp.route("/overtime/<int:permit_id>", methods=["GET", "POST"])
@role_required("AD")
def edit_overtime(permit_id):
    r = shift_rules()
    row = db.call_function("fn_get_overtime", permit_id, one=True)
    if row is None:
        abort(404)
    if request.method == "POST":
        try:
            start, end, grace, note = _overtime_fields()
            attendance_store.save_overtime(session["user_id"], row["user_id"], row["work_date"],
                                           start, end, grace, note, permit_id=permit_id)
            flash("Overtime saved.", "success")
            return redirect(url_for("attendance.overtime"))
        except (ValueError, db.DbError) as exc:
            flash(str(exc), "error")
            return render_template("overtime_form.html", permit=dict(request.form, permit_id=permit_id, full_name=row["full_name"],
                                   work_date=row["work_date"].isoformat(), started=row["started"]), staff=[], editing=True,
                                   default_grace=r["grace"], tab="overtime"), 400
    permit = dict(row, start_time=row["start_time"].strftime("%H:%M"), end_time=row["end_time"].strftime("%H:%M"),
                  work_date=row["work_date"].isoformat(), note=row["note"] or "")
    return render_template("overtime_form.html", permit=permit, staff=[], editing=True,
                           default_grace=r["grace"], tab="overtime")


@bp.route("/overtime/<int:permit_id>/cancel", methods=["POST"])
@role_required("AD")
def cancel_overtime(permit_id):
    try:
        row = db.call_function("fn_get_overtime", permit_id, one=True)
        if not row:
            abort(404)
        attendance_store.cancel_overtime(permit_id, row["user_id"])
        flash("Overtime cancelled.", "success")
    except db.DbError as exc:
        flash(str(exc), "error")
    return redirect(url_for("attendance.overtime"))


# ------------------------------------------------------------------ admin: shift schedule
@bp.route("/schedule", methods=["GET", "POST"])
@role_required("AD")
def schedule():
    if request.method == "POST":
        try:
            f = request.form
            attendance_store.save_schedule(time.fromisoformat(f.get("shift_start", "")),
                                           time.fromisoformat(f.get("shift_end", "")), int(f.get("grace_minutes", "")))
            flash("Schedule saved.", "success")
            return redirect(url_for("attendance.schedule"))
        except ValueError:
            flash("Enter the time in, the time out and the grace period in minutes.", "error")
        except db.DbError as exc:
            flash(str(exc), "error")
        return render_template("schedule.html", s=request.form, tab="schedule"), 400
    r = shift_rules()
    s = {"shift_start": r["shift_start"].strftime("%H:%M"), "shift_end": r["shift_end"].strftime("%H:%M"),
         "grace_minutes": r["grace"]}
    return render_template("schedule.html", s=s, tab="schedule")
