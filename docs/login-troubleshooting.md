# Sign-in troubleshooting

## "Sign-in is temporarily unavailable"

The sign-in page reached the app but the database check failed. Work through these in order:

1. **Is the database up?** Open <http://127.0.0.1:5000/health>. It should return
   `{"database":"ok"}`. If it says `unreachable`, check the PostgreSQL service.
2. **Is `.env` pointing at the right database?** `DATABASE_URL` must contain the host, port, user,
   password and database name, for example
   `postgresql://postgres:1234@localhost:5432/THEFAD`. The Node app reads it on start — restart after edits.
3. **Is the schema installed?** Run `sql/check_setup.sql`; every row must say `OK`. If `fn_login_user` is
   missing, run `sql/01_auth.sql` (or `sql/setup_all.sql`).
4. **Does the login function exist and work?**

   ```sql
   SELECT * FROM fn_login_user('dev_admin', 'Admin@1234');
   ```

   One row means the account and password are fine; no rows means the password is wrong or the account
   is inactive.
5. **Is `pgcrypto` installed?** `fn_login_user` uses `crypt()`. `sql/01_auth.sql` runs
   `CREATE EXTENSION IF NOT EXISTS pgcrypto`.

## "Incorrect username or password"

- Usernames are stored exactly as typed; check `users.username` and `users.is_active`.
- Demo accounts: `dev_admin / Admin@1234`, `dev_cashier / Cashier@1234`.
- An admin can deactivate an account; inactive accounts cannot sign in.

## Sign-in works but every page sends me back to Attendance

That is the shift gate, not an error. Until a shift is running (clocked in during the scheduled window, or
an approved overtime window) only Attendance opens. Clock in from the Attendance page, or run the prototype
copy (`node prototype/run_prototype.js`, port 5001) while prototyping.

## The server does not start

- Run `npm install` in the project root (Node 20 or newer).
- `EADDRINUSE` means the port is taken: `PORT=5001 node run.js` (PowerShell: `$env:PORT='5001'; node run.js`).
- A missing `.env` falls back to `postgresql://postgres:postgres@localhost:5432/THEFAD` and the development
  secret key — fine for local work, never for deployment.

## Pages render but numbers or dates look odd

All timestamps are shop time (Asia/Manila, UTC+08:00). `time.js` parses database timestamps with that fixed
offset, so the server's own time zone does not matter.

## Other features still need their database routines

Attendance and automatic shift closing need no new routines; they use the existing `users`,
`daily_time_record` and `overtime_permit` tables. PIN approval, refunds, promos and the audit viewer use the
routines in `sql/`. Run `npm run check` to confirm every routine the code calls exists with the right
arguments.
