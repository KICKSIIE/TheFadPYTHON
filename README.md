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

<!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:97728e38f29712fd2ff3c69ca95ec1861fba3f1dc13a87f2369f75da03fcd8a1 -->

## Attendance, approvals and overtime
- All staff, including admins, land on Attendance after sign-in. Work pages and management POSTs require an open attendance row inside its scheduled window. Disabled accounts and changed roles are checked on every protected request. Database failures deny access.
- The regular schedule is Monday–Saturday in Asia/Manila. Clock in once during the scheduled window; late arrivals retain the same closing time. Actual time in is recorded for punctuality and payroll.
- Each clock-in snapshots its end time. Schedule edits affect future clock-ins; open regular shifts keep their snapshot. Regular time is never extended by arriving late.
- Admins authorize a separate overtime window. It cannot overlap regular hours. Once started, its end can only be extended before expiry, with a reason and admin approval. Closed records remain fixed.
- Forgotten clock-outs close at the recorded regular/overtime end. Run the worker alongside the web app, including when nobody is browsing:
  ```sh
  flask --app app close-shifts
  ```
  It sweeps every 30 seconds and writes the exact scheduled timestamp. Protected requests also sweep before authorizing access. Restart the worker after a process restart.
- A forgotten clock-in creates no paid time. Admins correct attendance through Everyone > Add shift / Edit with a reason. Existing historical completed records are retained.
- Admins set their own 6–12 digit approval PIN in Account & security using their current password. Management changes require approval; cashier stock changes require an admin username and PIN. Five failed PIN checks lock that admin PIN for 15 minutes. PINs are hashed; password verification allows replacement.
- Payroll is available to admins. Only completed, non-Absent regular and approved overtime records add hours. Both use the stored hourly rate; this is a gross-pay estimate without statutory deductions or an overtime premium. The current staff form does not edit hourly rates yet.
- Apply `sql/setup_all.sql` to an original restored database, or apply 05 and 06 to an already-updated database; also update the revised sale routine in 04. Migration 06 supplies routines previously only expected in the external backup. Their old implementations were unavailable, so confirm compatibility against your original backup before deployment.
- Audit log is now a searchable admin page backed by database triggers. It records actor, approving admin, entity and before/after data, excluding credentials and binary photos. Audit history rejects UPDATE, DELETE and TRUNCATE. Direct database owners can still change database objects; deploy with restricted database credentials.



<!-- /coderabbit-ai-generated:v1 --><!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:80eb091fe70ad3fd5dfc9bd6fbacaf6b53010787fb2bfcd127010f5aec060723 -->

## Shop and location
The header search is centered with keyboard-accessible product suggestions. Categories sit on the left on desktop and wrap above products on mobile. Search retains the current filters.
The footer uses the supplied [shop location](https://maps.app.goo.gl/fEHAhXsQ6s6VsaWe8), pinned at 10.3100695, 123.9493883, with coordinate-based directions. Store configuration is in `config.py`.



<!-- /coderabbit-ai-generated:v1 -->## Demo data (optional, development database only)
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

<!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:8fb1747bccfeeaf89eb65112a8d9480ad47b0256c4a716673010fb500d979287 -->

## Remaining scope
OTP login, database roles and RLS are still unfinished. The CRUD coverage report supplied with this task lists missing staff profile/password features, inventory ledger corrections/deletions, attendance deletion and standalone sale-item reports. Audit and payroll now have working pages.



<!-- /coderabbit-ai-generated:v1 -->## Who owns what
catalog (shop), admin_products: Batiola | auth, dashboard, attendance, admin_staff: Decembrano
promos, admin_promos, refunds, audit: Po | pos, orders: Pono | inventory: Rivera

## Later phases (hooks already in place)
- `db._prepare()`: SET LOCAL ROLE and `app.current_shift` (phase 2)
- `MFA_ENABLED=true` + `auth/routes.py verify_otp` (phase 2)
<!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:8d07fa3d0814bc922042ba5f25ef7967c971e6e1d6651b369f25f8531d26f09d -->

- `modules/audit.py`: database audit viewer with redacted before/after details.

<!-- /coderabbit-ai-generated:v1 -->

Run tests: `pip install pytest` then `pytest`
