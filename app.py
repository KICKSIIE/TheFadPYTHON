from flask import Flask, jsonify, render_template, session

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
        c = app.config
        place = f"{c['STORE_PLUS_CODE']} {c['STORE_ADDRESS']}"
        store = {"name": c["STORE_NAME"], "tagline": c["STORE_TAGLINE"], "facebook": c["STORE_FACEBOOK"],
                 "plus_code": c["STORE_PLUS_CODE"], "address": c["STORE_ADDRESS"],
                 "map_embed": f"https://www.google.com/maps?q={quote(place, safe='')}&z=17&output=embed",
                 "map_open": f"https://www.google.com/maps/search/?api=1&query={quote(place, safe='')}",
                 "directions": f"https://www.google.com/maps/dir/?api=1&destination={quote(place, safe='')}"}
        return {
            "store": store,
            "csrf_token": csrf.csrf_token,
            "current_user": user,
            "nav_items": menu.items_for(user_type) if user else [],
            "nav_groups": menu.groups_for(user_type) if user else [],
            "low_stock_limit": utils.LOW_STOCK,
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

    return app


if __name__ == "__main__":
    create_app().run(debug=True)
