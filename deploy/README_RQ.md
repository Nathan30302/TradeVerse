RQ worker deployment and monitoring

This directory contains example configuration for running the RQ worker in production.

Systemd unit (rq_worker.service)
- Copy `deploy/rq_worker.service` to `/etc/systemd/system/rq_worker.service`, update paths and user as appropriate.
- Reload systemd and enable the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable rq_worker
sudo systemctl start rq_worker
sudo journalctl -u rq_worker -f
```

Supervisor config (supervisor_rq.conf)
- Place `deploy/supervisor_rq.conf` into `/etc/supervisor/conf.d/` and run:

```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start tradeverse_rq_worker
```

Docker / Compose
- `docker-compose.yml` includes `redis`, `web`, `worker` (built from `Dockerfile.worker`), and `rq-dashboard`.
- Start locally:

```bash
docker-compose up --build
```

RQ Dashboard
- The compose file exposes `rq-dashboard` at http://localhost:9181 by default for monitoring queues and jobs.

Retry policy and durability
- The app enqueues RQ jobs with a Retry policy (3 attempts with backoff). The job payload and progress are persisted in the DB as well, so the system is resilient if RQ is unavailable (DB jobs will be processed by the fallback polling worker).

Metrics
- Use `rq-dashboard` for human monitoring.
- For Prometheus metrics, run an exporter that scrapes Redis keys used by RQ or instrument application-level metrics using the `prometheus_client` Python package and expose `/metrics`.
Metrics
- `prometheus_client` is used by the application to expose `/metrics`.
- The Docker Compose setup includes Prometheus (http://localhost:9090) and Grafana (http://localhost:3000) for monitoring. Prometheus scrapes the Flask web app at `/metrics`.
- To visualize job metrics in Grafana, add Prometheus as a data source (URL: http://prometheus:9090) and import or create dashboards that query `tradeverse_imports_jobs_saved_total`, `tradeverse_imports_jobs_failed_total`, and `tradeverse_imports_job_duration_seconds`.

Security note
- Ensure Redis is protected in production; do not expose it publicly. Use network firewalling and auth where possible.
