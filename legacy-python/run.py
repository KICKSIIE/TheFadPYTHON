"""Start The Fad:   python run.py     (does the same as:  flask --app app run --debug)

The app itself is built by create_app() in app.py. This file only starts it, and stops with a clear
message if the copy of the project being run is out of date, instead of failing later on a web page.
"""
import sys

import app as app_module
from app import create_app

app = create_app()

REQUIRED_FILTERS = ("peso", "dt", "label", "color_hex")
missing = [f for f in REQUIRED_FILTERS if f not in app.jinja_env.filters]
if missing:
    sys.exit(
        "This copy of the project is out of date or mixed with an older one.\n"
        f"  Missing template filters: {', '.join(missing)}\n"
        f"  app.py being used: {app_module.__file__}\n"
        "Replace the WHOLE project folder with the newest thefad_full.zip (keep your .env) and try again."
    )

if __name__ == "__main__":
    app.run(debug=True)
