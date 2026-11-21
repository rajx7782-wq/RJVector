# RJVector — Tuition Management Platform

A new Flask + PostgreSQL tuition management app with a responsive PWA interface and an Android WebView wrapper project.

## Important status

This is a **working foundation / MVP**, not yet a fully audited production release. Included working modules: role-specific login, forced first-login password change, student management, attendance, MCQ test creation and submission, study material links, classes, announcements, results, fee records, homework, CSV attendance export, and dashboard counts. Push/email notifications, assignment uploads/submissions, doubts, timetable/calendar, full leaderboard, PDF reports, and automatic object-storage upload are not implemented yet.

No app can honestly be guaranteed bug-free. Run the checks below and complete the deployment steps before real student use.

## Requirements

- Python 3.12+
- PostgreSQL 14+
- Render web service (or another Python host)
- Persistent object storage such as Cloudinary or S3-compatible storage for uploaded files. Render's local filesystem is not used for uploads.

## Local setup

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL='postgresql://USER:PASSWORD@HOST:5432/DBNAME'
export SECRET_KEY='use-a-long-random-secret-value'
export ADMIN_USERNAME='RAJ JADHAV'
export ADMIN_INITIAL_PASSWORD='set-a-temporary-secret-here'
export COOKIE_SECURE='false' # local HTTP only; use true on HTTPS production
python app.py
```

Open http://127.0.0.1:5000. `/health` checks the DB connection. The first startup creates the schema and seeds the first admin only if no admin exists. The initial password is hashed and `must_change_password` is set. Change it immediately on first login. Do not commit secrets or put them in source code.


## Neon PostgreSQL setup (recommended)

This project is a **Python Flask application**, not a Node.js application. It has no `package.json`, no Node build step, and does not need `npm run build` or a Neon `neon.ts` service definition. The Neon CLI workflow in a Node-oriented setup guide is therefore not the correct deployment path for this repository.

1. In Neon Console, open the `rjvector` project and select the `production` branch.
2. Open **Connect**, choose the database and role, and copy the PostgreSQL connection string. Keep it private. For a Render-hosted Flask app, use the Neon pooled connection string if available; retain the `sslmode=require` option supplied by Neon.
3. In Render, open the RJVector Web Service → **Environment** and set `DATABASE_URL` to that connection string. Do not put it in Git, source files, or chat.
4. Set `SECRET_KEY` to a long random secret, `ADMIN_USERNAME=RAJ JADHAV`, and `ADMIN_INITIAL_PASSWORD` to a temporary bootstrap password. Set `COOKIE_SECURE=true`.
5. Deploy the Flask service. On startup, the app creates its database tables. Visit `/health`; it must report `database: connected`.
6. Log in as Admin, change the temporary password, then remove `ADMIN_INITIAL_PASSWORD` from Render's environment.

For a local connection, copy `.env.example` to `.env`, fill in your Neon URL and secrets, then export those variables in your shell before running `python app.py`. Never upload `.env` to Git.

**What this setup does not do:** the Neon CLI `neon init` / `neon deploy` workflow provisions Node/TypeScript-defined services and pulls their environment variables into a local Node project. This Flask repository already has a PostgreSQL driver (`psycopg[binary,pool]`) and expects `DATABASE_URL`; connecting it through Render's environment is the simpler supported integration.

## Render deployment

1. Create a PostgreSQL database (Render PostgreSQL or another managed PostgreSQL provider).
2. Create a Render Web Service from this repository.
3. Use `pip install -r requirements.txt` as the build command.
4. Use `gunicorn app:app --workers 2 --threads 4 --timeout 120` as the start command.
5. Set `DATABASE_URL` to the database's **internal** connection URL when hosted in the same provider/region.
6. Set `SECRET_KEY` to a long random secret, `ADMIN_USERNAME=RAJ JADHAV`, and `ADMIN_INITIAL_PASSWORD` to a temporary password. Set `COOKIE_SECURE=true`.
7. Deploy and visit `/health`. Confirm it returns `{"status":"ok","database":"connected","app":"RJVector"}`.
8. Sign in with Admin role and change the temporary password immediately. Remove `ADMIN_INITIAL_PASSWORD` from the service environment after the admin account is created; the app does not reset an existing admin password.

`render.yaml` is a blueprint template; review it before applying. Never paste database credentials into chat or commit them to Git.

## Persistent file storage

Study Material currently stores a **permanent HTTPS file URL** in PostgreSQL. Upload each PDF/image to Cloudinary or S3-compatible object storage using that provider's dashboard, then paste its secure URL into RJVector. Do not save uploads to the Render app directory: that filesystem can be replaced during deploy/restart. Direct in-app file upload integration is a remaining implementation item.

## Data persistence and backups

All core records are stored in PostgreSQL. Browser cache is used only for static shell assets; `/api/*` responses are never cached. Configure automated backups/PITR with your database provider and periodically test restoration. Example manual backup:

```bash
pg_dump "$DATABASE_URL" --format=custom --file=rjvector-backup.dump
pg_restore --clean --if-exists --dbname "$DATABASE_URL" rjvector-backup.dump
```

Keep backups encrypted and outside the web-service filesystem.

## Android app wrapper

The `android/` folder contains an Android Studio WebView wrapper. It requires a deployed HTTPS URL before it can be built. Open the `android/` folder in Android Studio, set `BASE_URL` in `android/app/build.gradle` to your deployed URL, build a signed APK using **Build → Generate Signed Bundle / APK → APK**, and install it on your Android device. This source bundle does **not** contain a compiled/signed APK yet. The PWA can also be installed from Chrome after deployment using **⋮ → Add to Home screen / Install app**.

## Current API / security notes

- Role is verified on the server for admin-only operations.
- Passwords use Werkzeug's password hashing.
- Sessions use HttpOnly, SameSite=Lax cookies; HTTPS secure-cookie mode is enabled by default.
- Use HTTPS in production. For a public production launch, add CSRF protection, login rate limiting, audit review, automated tests, object-storage upload integration, and a dedicated migration runner before onboarding real users.
- The initial admin password is only a bootstrap secret. Never keep `12345` as a permanent password.
