"""One place that decides what each role sees in the staff menu, grouped into sections."""

ROLE_LABELS = {"CA": "Cashier", "AD": "Admin"}

# (section, label, endpoint, roles, short description for tiles)
MENU = [
    ("Overview", "Dashboard", "dashboard.index", ("CA", "AD"), ""),
    ("Sell", "New sale", "pos.index", ("CA", "AD"), "Ring up walk-in and delivery orders."),
    ("Sell", "Orders", "orders.index", ("CA", "AD"), "Track orders, deliveries and receipts."),
    ("Stock", "Inventory", "inventory.index", ("CA", "AD"), "Stock in, out, counts and history."),
    ("Stock", "Products", "admin_products.index", ("AD",), "Products, colors, sizes and photos."),
    ("Stock", "Promos", "promos.index", ("CA",), "See which promos are running."),
    ("Stock", "Promos", "admin_promos.index", ("AD",), "Create, edit and end promos."),
    ("Team", "Attendance", "attendance.index", ("CA", "AD"), "Clock in and out; admins manage schedule and overtime."),
    ("Team", "Payroll", "payroll.index", ("AD",), "Completed hours and gross pay."),
    ("Team", "Staff", "admin_staff.index", ("AD",), "Staff accounts and roles."),
    ("Admin", "Refunds", "refunds.index", ("AD",), "Process refunds and see the refund report."),
    ("Admin", "Audit log", "audit.index", ("AD",), "Who changed what, and when."),
]


def items_for(user_type):
    return [
        {"section": sec, "label": label, "endpoint": ep, "desc": desc}
        for sec, label, ep, roles, desc in MENU
        if user_type in roles
    ]


def groups_for(user_type):
    """Menu items grouped by section, in order, for the sidebar."""
    groups = []
    for item in items_for(user_type):
        if not groups or groups[-1]["name"] != item["section"]:
            groups.append({"name": item["section"], "items": []})
        groups[-1]["items"].append(item)
    return groups
