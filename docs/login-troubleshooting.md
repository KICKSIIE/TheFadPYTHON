<!-- coderabbit-ai-generated:v1 -->

# Login and attendance troubleshooting

1. Open `http://127.0.0.1:5000/login` in the browser on the same computer as the Flask server. The sign-in form is available even if an older session exists. Choose **Sign out** there to end that session. In the task web UI, use its Preview instead; `127.0.0.1` on your own computer is a different server.
2. Open `http://127.0.0.1:5000/health`. If it reports `database: unreachable`, start PostgreSQL and check that `DATABASE_URL` in your local `.env` points to your intended database. Restart Flask after changing `.env`. Do not share the URL or credentials in logs or screenshots.
3. If `/health` says `database: ok` but staff pages return 503, check the Flask server log for `Attendance verification failed`. Connectivity alone does not prove the attendance routines and tables exist. In pgAdmin, select the intended database and run `sql/check_setup.sql`; check the attendance-related rows. Give the error and any missing row names to the person maintaining the database.
4. If routines are missing, compare the database with `sql/05_attendance_audit.sql` and the setup instructions in `README.md`. Take a backup and check compatibility with your existing schema before applying any migration. The repository expects an existing base database; `sql/setup_all.sql` is not a substitute for that backup. Do not apply demo seed data to a production database.
5. After database access and setup are restored, reload `/login` and sign in. You will go to Attendance; clock in inside the scheduled shift or an approved overtime window. Protected pages remain unavailable if attendance cannot be verified. Start the separate `flask --app app close-shifts` worker so missed clock-outs close even when no one is using the site.

A 503 can also have other causes; the request log alone does not identify them. If the issue persists, share the non-sensitive `Attendance verification failed` message and whether `/health` is OK; omit credentials and personal data.
