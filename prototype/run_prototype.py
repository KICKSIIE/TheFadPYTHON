"""Run a navigable copy of The Fad for prototyping.

This is the same code and the same database as the real app, with one difference: every signed-in
staff page opens even when no shift is active, so you can click through the whole system without
clocking in. The real app (`python run.py` or `flask --app app run`) never sets this flag, so its
shift gate stays enforced.

Run it from anywhere:
    .\venv\Scripts\python.exe prototype\run_prototype.py
Then open http://127.0.0.1:5001/staff and sign in as dev_admin / Admin@1234 or dev_cashier / Cashier@1234.
"""
import os
import sys
from pathlib import Path

# Must be set before app/config.py is imported: it is read when the Config class is defined.
os.environ["NAV_UNLOCKED"] = "true"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402  (import after the flag is set)

app = create_app()


if __name__ == "__main__":
    print("Prototype copy: navigation unlocked, no clock-in required.")
    print("Open http://127.0.0.1:5001/staff and sign in. Stop it with Ctrl+C.")
    # No reloader: one process, so it can sit next to the real app without duplicate workers.
    app.run(host="127.0.0.1", port=5001, debug=True, use_reloader=False)
