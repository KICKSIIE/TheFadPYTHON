<!-- coderabbit-ai-generated:v1 -->

# Login and attendance troubleshooting

1. Open `http://127.0.0.1:5000/login` in the browser on the same computer as the Flask server. The sign-in form is available even if an older session exists. Choose **Sign out** there to end that session. In the task web UI, use its Preview instead; `127.0.0.1` on your own computer is a different server.
2. Open `http://127.0.0.1:5000/health`. If it reports `database: unreachable`, start PostgreSQL and check that `DATABASE_URL` in your local `.env` points to your intended database. Restart Flask after changing `.env`. Do not share the URL or credentials in logs or screenshots.
<!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:cbbbb4215a5be1d1694ee7867f83fb31d14aba8624221a2837b42d67325506c0 -->

3. If `/health` says `database: ok` but staff pages return 503, check the Flask server log for `Attendance verification failed`. The backend reads existing users and attendance tables; it does not call `fn_staff_access`. Check the logged table or column name against your existing database and share the non-sensitive error with the database maintainer.

<!-- /coderabbit-ai-generated:v1 -->
<!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:c861b9fb3de9f16954812fee3d3fafcd512ac3c952b85bbab7820eb35c33afe0 -->

4. Attendance access and automatic closing require no new database function or trigger. They use the existing `users` and `daily_time_record` tables; schedule and overtime management also need their existing tables. Other features, including the PIN and audit viewer, still use their own database routines. Check compatibility and take a backup before applying any optional migration; do not seed production with demo data.

<!-- /coderabbit-ai-generated:v1 -->
5. After database access and setup are restored, reload `/login` and sign in. You will go to Attendance; clock in inside the scheduled shift or an approved overtime window. Protected pages remain unavailable if attendance cannot be verified. Start the separate `flask --app app close-shifts` worker so missed clock-outs close even when no one is using the site.

A 503 can also have other causes; the request log alone does not identify them. If the issue persists, share the non-sensitive `Attendance verification failed` message and whether `/health` is OK; omit credentials and personal data.
