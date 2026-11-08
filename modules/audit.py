"""Audit log. Owner: Po (AUDIT_LOGS (phase 3))."""
from flask import Blueprint, render_template

from auth.decorators import role_required

bp = Blueprint("audit", __name__, url_prefix="/admin/audit")


@bp.route("/")
@role_required("AD")
def index():
    # TODO(Po): call stored routines with db.call_function / db.call_procedure.
    return render_template("placeholder.html", title="Audit log", owner="Po", tables="AUDIT_LOGS (phase 3)")
