import os
from datetime import time, timedelta
from decimal import Decimal

from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")
    DATABASE_URL = os.environ.get(
        "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/THEFAD"
    )
    DB_SCHEMA = "thefad"

    # Product photos are stored in the database. Reject bigger uploads before reading them.
    MAX_CONTENT_LENGTH = 26 * 1024 * 1024  # up to 8 photos of 3 MB each

    # Phase 2: set MFA_ENABLED=true in .env once /verify-otp is implemented.
    MFA_ENABLED = os.environ.get("MFA_ENABLED", "false").lower() == "true"

    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    # ---- Defaults used until an admin saves the shift schedule (Attendance > Schedule).
    SHIFT_START = time(9, 0)             # regular shift time in
    SHIFT_END = time(17, 0)              # regular shift time out
    GRACE_MINUTES = 15                   # clocking in later than this after time in counts as Late
    SHIFT_HOURS = Decimal(8)
    MAX_SHIFT_HOURS = Decimal(24)        # a shift left open longer than this is a missed clock-out
    WORK_DAYS = "1,2,3,4,5,6"            # Monday=1 ... Sunday=7. Absent is counted on these days only
    LOW_STOCK_DEFAULT = 5                # "low" stock means this many or fewer; can be changed per search

    # ---- Shop details shown in the footer of the public shop.
    STORE_NAME = "The Fad"
    STORE_TAGLINE = "Fashion You Always Deserve"
    STORE_FACEBOOK = "https://www.facebook.com/profile.php?id=61580609323200"
    STORE_PLUS_CODE = "8W6X+2QC"
    STORE_ADDRESS = "G.Y. Dela Serna St, Lapu-Lapu, Cebu"
