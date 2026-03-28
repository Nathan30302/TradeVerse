TradeVerse — Deployment Quick Guide

This file describes the recommended production deployment steps for TradeVerse.

1) Prepare repository
- Ensure `fix/instrument-ui` branch contains the final changes and has been pushed to `origin` (done).
- Create a release branch locally from `fix/instrument-ui` (optional):
  git checkout -b release/fix-instrument-ui fix/instrument-ui
  git push -u origin release/fix-instrument-ui

2) Production environment variables (must be set in your hosting platform or secrets manager)
- SECRET_KEY (strong random string)
- DATABASE_URL (postgres://... or postgresql://...)
- MAIL_SERVER, MAIL_PORT, MAIL_USERNAME, MAIL_PASSWORD (optional)
- STRIPE_API_KEY (if using monetization)
- AWS_* (if using S3 or other AWS services)

3) Recommended platform and start command
- The project includes a `Procfile` that runs Gunicorn:
  web: python -m gunicorn app.wsgi:app
- Ensure build/install runs `pip install -r requirements.txt`.

4) Postgres / DB
- Use managed Postgres in production (Render/Heroku/AWS RDS).
- Run migrations with Alembic (Flask-Migrate): `flask db upgrade` in the deployed environment or via a deploy hook.

5) Static files / uploads
- App uses `/tmp/uploads` in production by default. Configure durable storage (S3) for persistent uploads if needed.
- Avoid writing to local disk in production; configure `UPLOAD_FOLDER` via env var if using persistent storage.

6) Health checks & monitoring
- Expose `/metrics` if running prometheus_client; ensure access control for metrics if public.
- Configure health check on `/` or a lightweight endpoint used by your platform.

7) Deploy steps (Render example)
- Create a new Web Service on Render, connect repository and select branch `release/fix-instrument-ui`.
- Set Environment: `PYTHON_VERSION`, `SECRET_KEY`, `DATABASE_URL`, etc.
- Build Command (default): `pip install -r requirements.txt`
- Start Command: `python -m gunicorn app.wsgi:app`

8) Post-deploy
- Run `flask db upgrade` or `alembic upgrade head` in the production environment (prefer a one-time deploy task).
- Create admin user if necessary via Flask shell.

9) Rollback plan
- Keep backups of DB (automated snapshots) and create a rollback tag in Git for quick redeploy.

10) Security checklist
- Do not commit secrets to Git. Use `.env.example` only.
- Ensure `DEBUG=False` in production environment.
- Use secure HTTPS (platform-managed TLS) and `SESSION_COOKIE_SECURE=True`.

Contact me if you want me to create a PR to `main` or perform the merge for you.
