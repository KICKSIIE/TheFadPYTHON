from flask import Flask, abort, flash, g, jsonify, render_template, request, session

from urllib.parse import quote

import csrf
import db
import menu
import utils
from config import Config
from modules import register_all


def create_app(testing=False):
    app = Flask(__name__)
    app.config.from_object(Config)
    app.config["TESTING"] = testing

    if not testing:
        db.init_db(app)

    @app.template_filter("peso")
    def peso(value):
        return "" if value is None else f"\u20b1{value:,.2f}"

    @app.template_filter("dt")
    def fmt_dt(value):
        return "" if value is None else value.strftime("%b %d, %Y %I:%M %p")

    app.add_template_filter(utils.color_hex, "color_hex")

    @app.template_filter("label")
    def label(value):
        return (value or "").replace("_", " ")

    app.before_request(csrf.protect)
    register_all(app)

    @app.before_request
    def management_approval():
        session.pop("approval_actor", None)
        if request.method != "POST" or not session.get("user_id"):
            return
        guarded = request.blueprint in {"admin_products", "admin_staff", "admin_promos", "refunds", "inventory"} or (
            request.blueprint == "attendance" and request.endpoint not in {
                "attendance.clock_in", "attendance.clock_out", "attendance.overtime_in", "attendance.overtime_out"})
        if not guarded:
            return
        # Verify attendance and role before processing any management approval.
        from auth.decorators import login_required
        result = login_required(lambda: None)()
        if result is not None:
            return result
        if request.blueprint != "inventory" and session["user_type"] != "AD":
            abort(403)
        username = session["username"] if session["user_type"] == "AD" else request.form.get("approval_username", "").strip()
        try:
            verified = db.call_function("fn_verify_management_pin", username, request.form.get("approval_pin", ""), one=True)
        except db.DbError:
            abort(503)
        if not verified or not verified["verified"]:
            flash("A valid admin approval PIN is required. Set your PIN in Account & security. Five failed attempts lock it for 15 minutes.", "error")
            return render_template("error.html", code=403, heading="Admin approval required",
                                   message="Return to the form and enter a valid approval PIN. Your change was not saved."), 403
        session["approval_actor"] = username

    @app.cli.command("close-shifts")
    def close_shifts():
        """Close expired attendance every 30 seconds, including when there are no web requests."""
        import time
        while True:
            try:
                db.call_function("fn_close_expired_shifts")
            except db.DbError:
                app.logger.exception("Attendance closure failed; retrying")
            time.sleep(30)

    @app.context_processor
    def inject_globals():
        user_type = session.get("user_type")
        user = None
        if "user_id" in session:
            name = (session.get("display_name") or "").strip() or session.get("username") or "Staff"
            user = {
                "name": name,
                "first_name": name.split()[0],
                "username": session.get("username"),
                "role": menu.ROLE_LABELS.get(user_type, user_type),
            }
        locked = user and getattr(g, "staff_access", None) and not g.staff_access["allowed"]
        nav = menu.items_for(user_type) if user else []
        groups = menu.groups_for(user_type) if user else []
        if locked:
            nav = [item for item in nav if item["endpoint"] == "attendance.index"]
            groups = [{"name": "Team", "items": nav}]
        c = app.config
        place = f"{c['STORE_LATITUDE']},{c['STORE_LONGITUDE']}"
        store = {"name": c["STORE_NAME"], "tagline": c["STORE_TAGLINE"], "facebook": c["STORE_FACEBOOK"],
                 "plus_code": c["STORE_PLUS_CODE"], "address": c["STORE_ADDRESS"],
                 "map_embed": f"https://www.google.com/maps?q={quote(place, safe='')}&z=17&output=embed",
                 "map_open": c["STORE_MAP_URL"],
                 "directions": f"https://www.google.com/maps/dir/?api=1&destination={quote(place, safe='')}"}
        return {
            "store": store,
            "csrf_token": csrf.csrf_token,
            "current_user": user,
            "nav_items": nav,
            "nav_groups": groups,
            "low_stock_limit": utils.LOW_STOCK,
            "staff_access": getattr(g, "staff_access", None),
        }

    @app.route("/health")
    def health():
        ok = db.ping()
        return jsonify(database="ok" if ok else "unreachable"), (200 if ok else 503)

    @app.errorhandler(400)
    def bad_request(_):
        return render_template("error.html", code=400, heading="Request could not be verified",
                               message="Reload the page and try again."), 400

    @app.errorhandler(413)
    def too_large(_):
        return render_template("error.html", code=413, heading="That file is too large",
                               message="Each photo must be 3 MB or smaller, and a product can have up to 8. Resize the photos and try again."), 413

    @app.errorhandler(403)
    def forbidden(_):
        return render_template("error.html", code=403, heading="You do not have access to this page",
                               message="This page is for admins. Ask an admin if you need it."), 403

    @app.errorhandler(404)
    def not_found(_):
        return render_template("error.html", code=404, heading="Page not found",
                               message="Check the address or use the menu."), 404

    @app.errorhandler(503)
    def unavailable(_):
        return render_template("unavailable.html"), 503

    return app


if __name__ == "__main__":
    create_app().run(debug=True)
