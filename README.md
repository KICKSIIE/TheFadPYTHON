# The Fad — web app (Node.js + PostgreSQL)

Shop, point of sale and staff system for The Fad.

**Stack:** HTML · CSS · JavaScript · Node.js (Express) · PostgreSQL.
Templates use Nunjucks (Jinja-style syntax) and are rendered on the server, so every page still works
without a front-end build step.

---

## 1. Database

1. Restore your backup into a database named `THEFAD` (or use the one you already have).
2. In pgAdmin's Query Tool (or `psql`), run `sql/setup_all.sql` once, then `sql/check_setup.sql` — every
   row should say `OK`.

Connection details come from `.env`:

```
DATABASE_URL=postgresql://postgres:1234@localhost:5432/THEFAD
SECRET_KEY=change-this-to-a-long-random-string
MFA_ENABLED=false
```

## 2. Run the app (Windows)

```powershell
npm install
node run.js          # or: npm start
```

Open <http://127.0.0.1:5000> and check <http://127.0.0.1:5000/health> (should say `database: ok`).

Sign in with `dev_admin / Admin@1234` or `dev_cashier / Cashier@1234`.
Admins confirm management changes with the approval PIN `123456` (set in Account & security).

### Navigation copy for prototyping

```powershell
node prototype/run_prototype.js     # or: npm run prototype
```

Same app and database on <http://127.0.0.1:5001>, with the shift gate switched off so every page opens.
A yellow banner marks it. See `prototype/README.md`.

## 3. Project layout

| Path | Purpose |
|---|---|
| `app.js` | Express app: sessions, CSRF, approval middleware, routes, error pages |
| `run.js` | Entry point (starts the server and the attendance sweeper) |
| `config.js` | Environment, shop settings, store details |
| `db.js` | The only database layer: `callFunction`, `callFunctionOne`, `callProcedure`, `withClient` |
| `render.js` | Template context (user, menu, store, flashes) |
| `approval.js` | Management POSTs require a valid admin approval PIN |
| `csrf.js` | Session-bound CSRF token |
| `attendance_store.js` | Attendance rules in the application (no attendance DB routines needed) |
| `sweeper.js` | Closes forgotten shifts every 30 seconds |
| `menu.js` | Sidebar per role |
| `modules/` | One file per screen group (catalog, pos, orders, inventory, attendance, admin, …) |
| `templates/` | Nunjucks views (same markup as before) |
| `static/` | CSS, JS and logos, served from `/static` |
| `sql/` | Schema, routines, migrations and the setup check |
| `tests/` | Node test suite and the routine cross-check |
| `docs/` | Design spec for Figma and troubleshooting notes |
| `legacy-python/` | The previous Flask implementation, kept for reference |

## 4. Stored routines

Most screens call PostgreSQL functions and procedures (`sql/*.sql`). All access goes through `db.js`, so no
module talks to the driver directly:

```js
const rows = await db.callFunction('fn_list_discounts');
const product = await db.callFunctionOne('fn_get_product', 30);
const result = await db.callProcedure('sp_create_sale', userId, 'Walk-in', 'Cash', '', '', '', itemsJson, null);
```

Catch `db.DbError` and flash `error.message` — the database's own message is safe to show.
Add `{{ csrf_token() }}` as a hidden `_csrf` field in every POST form.

Attendance is different: `attendance_store.js` reads and writes the existing `users`,
`daily_time_record` and `overtime_permit` tables in one transaction, so no attendance routine or trigger
is installed.

## 5. Attendance, approvals and overtime

- Every role lands on **Attendance** after sign-in. Until a shift is running (clocked in, or approved
  overtime) only Attendance opens; the other pages redirect back to it.
- The regular schedule is Monday–Saturday in Asia/Manila. Clock in once during the scheduled window; late
  arrivals keep the same closing time. Actual time in is recorded for punctuality.
- Forgotten clock-outs close automatically at the scheduled end. The server sweeps every 30 seconds, and
  protected requests close expired shifts before authorising access.
- Admins approve overtime; a running window can only be extended before it ends, with a reason.
- Admins set their own 6–12 digit approval PIN in Account & security. Management changes require that PIN;
  cashier stock changes require an admin username and PIN. Wrong PINs are rejected without locking the PIN.
- Cashiers do not see Account & security, Products, Staff, Refunds or the audit log.
- The audit log records actor, approving admin and the changed fields; credentials and photo data never appear.

## 6. Shop and location

The storefront is public: search, category pills, in-stock filter, sorting, product pages with a gallery,
and a footer with the map. Store configuration lives in `config.js`.

## 7. Checks

```powershell
npm test          # node --test tests/ : renders every page, CSRF and approval are enforced
npm run check     # every routine called from JavaScript exists in sql/ with matching arguments
```

## 8. Demo data

The demo database is already seeded (products, staff, attendance, orders, refunds). The original seeding
script is `legacy-python/seed_demo.py` and still runs with Python 3 if you need to rebuild it.

## 9. Who owns what

catalog (shop), admin_products: Batiola | auth, dashboard, attendance, admin_staff: Decembrano
promos, admin_promos, refunds, audit: Po | pos, orders: Pono | inventory: Rivera
