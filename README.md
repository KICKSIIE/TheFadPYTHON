# The Fad - web app starter

Flask + PostgreSQL. The web app only calls stored routines (see `db.py`).

## 1. Database
1. Restore your backup into a database named `THEFAD` (or use the one you already have).
2. In pgAdmin's Query Tool, run these in order:
   easiest: paste `sql/setup_all.sql` and press F5 (runs 00 to 04 as one transaction), then run `sql/check_setup.sql`; every row should say OK.

## 2. Run the app (Windows)
```
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env      (then edit DATABASE_URL and SECRET_KEY)
flask --app app run --debug
```
Or simply `python run.py` (it also refuses to start, with a clear message, if the project folder is out of date).
Open http://127.0.0.1:5000 and check http://127.0.0.1:5000/health (should say `database: ok`).
Sign in with `dev_admin / Admin@1234` or `dev_cashier / Cashier@1234`.

## 3. Add your screen
Each module has its own file in `modules/`. Replace the placeholder:
```python
import db
rows = db.call_function("fn_view_discounts", "Active")
result = db.call_procedure("sp_create_discount", name, pct, start, end, "NONE", None, None)
```
Catch `db.DbError` and `flash(str(e), "error")` to show the database's own error message.
Add `{{ csrf_token() }}` as a hidden `_csrf` field in every POST form.

## Attendance and overtime (admin: Attendance tabs)
- **Schedule:** the admin sets the regular shift time in, time out and the grace period for clocking in.
  Saved in the database (table `shift_setting`); `config.py` only holds the starting defaults.
- **Clock in:** after time in plus grace it is recorded as Late. One regular shift per person per day.
- **Clock out:** opens after a full shift (time out minus time in). Counted hours never exceed a full shift.
- **Overtime:** an admin allows it per person and day (Attendance > Overtime > Allow overtime), setting the overtime
  time in, time out and grace for clocking in. The person starts and ends it on their own Attendance page.
  It can only start inside that window and ends at the time out at the latest. Without permission, extra time is not counted.
- **Missed clock-out:** after 24 hours the person is asked for the time they finished.
- **Forgot to clock in, or a mistake:** only admins can fix it (Everyone > Add shift / Edit), with a reason.
- **Absent:** worked out for work days (Monday to Saturday) with no regular shift; counted from the staff member's start date.
- Other defaults in `config.py`: work days, longest shift (24 h), "low stock" level (5), and the shop details below.

## Shop footer (config.py)
The public shop footer shows how to order (the official Facebook page), the address with its Plus Code, a map with a pin,
Open in Google Maps and Get directions buttons. Change `STORE_FACEBOOK`, `STORE_PLUS_CODE`, `STORE_ADDRESS` in `config.py`.

## Demo data (optional, development database only)
After `setup_all.sql`: `python seed_demo.py`. Adds 12 products with colors, sizes and drawn placeholder photos, stock,
promos, staff, two weeks of attendance (late, absences, allowed overtime), about 35 orders and a refund.
Already seeded an earlier version? `python seed_demo.py --attendance` adds only the attendance and start dates.
Replace the placeholder photos under Products > Manage photos. Staff logins it creates use `Cashier@1234`.

## What works now
- **Shop (public):** search, category pills, in-stock toggle, sort; color dots, stock, gallery, full-screen photos.
- **Products:** colors and sizes, each with its own stock and photo gallery.
- **Staff area:** New sale (cart, delivery, receipts), Orders, Inventory (you set what "low" means), Products,
  Promos, Attendance, Staff, Refunds. Menu grouped into Sell, Stock, Team and Admin.
- **Dashboard:** today's numbers, 7-day chart and best sellers.

## Checks
`python tests/check_routines.py` confirms every routine the Python code calls exists in `sql/` with the right
number of arguments. `pytest` runs the app tests.

## Still to do (phases 2 and 3 of the security activity)
audit log page (`modules/audit.py`), OTP login, roles and RLS in `db._prepare()`.

## Who owns what
catalog (shop), admin_products: Batiola | auth, dashboard, attendance, admin_staff: Decembrano
promos, admin_promos, refunds, audit: Po | pos, orders: Pono | inventory: Rivera

## Later phases (hooks already in place)
- `db._prepare()`: SET LOCAL ROLE and `app.current_shift` (phase 2)
- `MFA_ENABLED=true` + `auth/routes.py verify_otp` (phase 2)
- `modules/audit.py` wired to `audit_logs` (phase 3)

Run tests: `pip install pytest` then `pytest`
