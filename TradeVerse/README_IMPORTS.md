Background import worker and secrets integration

What's added
- DB-backed ImportJob model and ImportedTradeSource to track uploaded files.
- A lightweight DB-polling worker (app/worker.py) that processes queued import jobs and persists trades into the `trades` table.
- Route `/api/imports/upload` now creates an ImportedTradeSource and enqueues a background ImportJob. Use `dry_run=1` to parse synchronously.
- Credential manager (`app/utils/credential_manager.py`) now attempts to read the Fernet key from:
  1. Environment variable `CREDENTIAL_ENCRYPTION_KEY`
  2. HashiCorp Vault at `VAULT_ADDR` with `VAULT_TOKEN` and `VAULT_SECRET_PATH` (calls Vault HTTP API)
  3. AWS Secrets Manager (requires `boto3` and env `AWS_SECRETS_MANAGER_SECRET`)
  4. Fallback: generates a development key (not for production)

Running the worker (dev)
- Start your Flask app normally. Then run a worker in a separate process with the app context:

```powershell
$env:FLASK_APP='run.py'; python -c "from app import create_app; app=create_app('development'); app.app_context().push(); from app.worker import run_worker; run_worker()"
```

- Or, run the worker non-looping (process one job) by editing the last call in `run_worker(loop=False)` accordingly.

Production notes
  - RQ (Redis Queue) is supported by the codebase: if `REDIS_URL` is set, the upload endpoint will enqueue an RQ job and you can run `rq worker imports` to process jobs.
  - Example: Start Redis, then run an RQ worker in the project venv:

```powershell
# start redis-server separately (platform-specific)
- Do NOT rely on the dev fallback Fernet key. Provision a secret in Vault or AWS Secrets Manager and set the corresponding env variables:
  - For Vault: VAULT_ADDR, VAULT_TOKEN, VAULT_SECRET_PATH (e.g., secret/data/tradeverse/fernet)
```

API usage

Vault deployment example (high-level)

1. Create secret in KV v2 at `secret/data/tradeverse/fernet` with key `CREDENTIAL_ENCRYPTION_KEY`.

2. On app startup, the code calls Vault HTTP API using `VAULT_ADDR` and `VAULT_TOKEN` and reads the secret. In production, avoid static tokens; instead use an auth method (Kubernetes auth, AppRole, or EC2) and grant minimal permissions to the app role.

Minimal Terraform snippet (KV v2 secret)

```hcl
resource "vault_kv_secret_v2" "tradeverse_fernet" {
  mount = "secret"
  name  = "tradeverse/fernet"
  Background import worker and secrets integration

  What's added
  - DB-backed `ImportJob` model and `ImportedTradeSource` to track uploaded files.
  - A lightweight DB-polling worker (`app/worker.py`) that processes queued import jobs and persists trades into the `trades` table.
  - Route `/api/imports/upload` now creates an `ImportedTradeSource` and enqueues a background `ImportJob`. Use `dry_run=1` to parse synchronously.
  - Credential manager (`app/utils/credential_manager.py`) now attempts to read the Fernet key from:
    1. Environment variable `CREDENTIAL_ENCRYPTION_KEY`
    2. HashiCorp Vault at `VAULT_ADDR` with `VAULT_TOKEN` and `VAULT_SECRET_PATH` (calls Vault HTTP API)
    3. AWS Secrets Manager (requires `boto3` and env `AWS_SECRETS_MANAGER_SECRET`)
    4. Fallback: generates a development key (not for production)

  Running the worker (dev)
  - Start your Flask app normally. Then run the polling worker in a separate process with the app context:

  ```powershell
  $env:FLASK_APP='run.py'; python -c "from app import create_app; app=create_app('development'); app.app_context().push(); from app.worker import run_worker; run_worker()"
  ```

  - Or, run the worker non-looping (process one job) by running `run_worker(loop=False)`.

  Production notes
  - RQ (Redis Queue) is supported by the codebase: if `REDIS_URL` is set, the upload endpoint will enqueue an RQ job and you can run `rq worker imports` to process jobs.
  - Example: Start Redis, then run an RQ worker in the project venv:

  ```powershell
  # start redis-server separately (platform-specific)
  $env:REDIS_URL='redis://localhost:6379/0'
  rq worker imports
  ```

  Docker / Compose example
  - A `docker-compose.yml` and `Dockerfile.worker` were added to the repository. They include a Redis service, a `web` Flask app, a `worker` service that runs `rq worker imports`, and `rq-dashboard` for monitoring.

  Start with:

  ```powershell
  docker-compose up --build
  ```

  Do NOT rely on the dev fallback Fernet key. Provision a secret in Vault or AWS Secrets Manager and set the corresponding env variables:
    - For Vault: `VAULT_ADDR`, `VAULT_TOKEN`, `VAULT_SECRET_PATH` (e.g., `secret/data/tradeverse/fernet`)
    - For AWS: `AWS_SECRETS_MANAGER_SECRET` and `AWS_REGION` (ensure IAM permissions)

  API usage
  - Upload endpoint: `POST /api/imports/upload`
    - form-data: file=<file>, broker=<broker_id>, dry_run=1 (optional)
    - If `dry_run=1` returns parsed preview; otherwise enqueues an import job and returns `job_id`.

  Vault deployment example (high-level)

  1. Create secret in KV v2 at `secret/data/tradeverse/fernet` with key `CREDENTIAL_ENCRYPTION_KEY`.

  2. On app startup, the code calls Vault HTTP API using `VAULT_ADDR` and `VAULT_TOKEN` and reads the secret. In production, avoid static tokens; instead use an auth method (Kubernetes auth, AppRole, or EC2) and grant minimal permissions to the app role.

  Minimal Terraform snippet (KV v2 secret)

  ```hcl
  resource "vault_kv_secret_v2" "tradeverse_fernet" {
    mount = "secret"
    name  = "tradeverse/fernet"
    data_json = jsonencode({
      CREDENTIAL_ENCRYPTION_KEY = "<base64-fernet-key>"
    })
  }
  ```

  In deployment pipelines, fetch the Vault secret into environment or let the app call Vault using a short-lived token (recommended). See Vault docs for AppRole/Kubernetes auth patterns.

  Next steps
  - Add authentication checks to ensure only the file owner can enqueue jobs.
  - Add job progress endpoints and a simple UI (already included: `/api/imports/jobs` and `/api/imports/ui/jobs/<id>`).
  - Replace DB polling with RQ workers for scale (example `docker-compose.yml` and systemd/supervisor configs provided).
