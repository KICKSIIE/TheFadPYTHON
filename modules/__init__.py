from . import (admin_products, admin_promos, admin_staff, attendance, audit,
               catalog, dashboard, inventory, orders, pos, promos, refunds)
from auth import routes as auth_routes

ALL = [auth_routes, catalog, dashboard, pos, orders, inventory, attendance, promos,
       admin_products, admin_staff, admin_promos, refunds, audit]


def register_all(app):
    for module in ALL:
        app.register_blueprint(module.bp)
