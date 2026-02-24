Title: Release — Instrument UI & Dynamic Island polish (release/fix-instrument-ui)

Summary
-------
This PR contains UI polish for the Dynamic Island, curated instrument rotator, server-side simulated market quotes, and pre-deployment cleanup. It prepares the app for production deployment (Render) and includes a Render manifest and pre-deploy checks.

Key changes
-----------
- UI: Improved Dynamic Island styling and unified rotator across landing and dashboard.
- Backend: Added `app/services/simulated_market.py` to provide consistent live-feeling percent changes when no market feed is connected.
- API: `/api/db/instruments/quotes` now returns curated trader-focused symbols (XAUUSD, US30, NAS100, US500, BTCUSD, EURUSD) with percent changes.
- Stats: Fixed `User.get_stats()` and added `/dashboard/api/stats` for server-authoritative metrics used by the Dynamic Island and mini-board.
- Cleanup: `.gitignore` updated, local `tradeverse.db`, pyc and venv artifacts untracked, `.env.example` added.
- Deployment: `render.yaml` (Render manifest), `Procfile`, and `README_DEPLOY.md` added/updated.
- Safety: `run.py` now respects `DEBUG` from configuration.
- Tools: `scripts/predeploy_check.py` added to validate prod readiness.

Migration / Post-deploy steps
----------------------------
1. Configure environment variables in Render (or chosen host):
   - `SECRET_KEY` (strong random string)
   - `DATABASE_URL` (Postgres)
   - `MAIL_*`, `STRIPE_*`, `AWS_*` as required
2. Deploy the `release/fix-instrument-ui` branch (Render will detect `render.yaml`).
3. Run DB migrations in production once:
   - `flask db upgrade` (run as a one-off job or via deploy hook)
4. Verify the homepage, login, dashboard, and Dynamic Island rotator.

Testing & verification
----------------------
- Run `python scripts/predeploy_check.py` locally (or CI) — it verifies key production settings.
- App factory tested in production mode using `create_app('production')` locally.

Deployment checklist (to tick in PR)
------------------------------------
- [ ] Secrets configured in Render (SECRET_KEY, DATABASE_URL)
- [ ] Render service connected to repo and uses `release/fix-instrument-ui` branch
- [ ] `flask db upgrade` executed in production
- [ ] Smoke-test: homepage loads, login works, dashboard metrics show
- [ ] Monitoring/health checks configured (optional)

Notes
-----
- No fake prices are shown anywhere — the Dynamic Island shows only instrument symbol, percent change, and an arrow. When a live feed is unavailable, percent changes are simulated consistently by `simulated_market`.
- This PR is intentionally non-breaking and primarily adds UI polish, defensive guards, and deployment preparation.

If you want me to merge this into `main` after review, tell me and I'll perform the merge and push.
