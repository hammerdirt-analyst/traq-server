# GCP Deployment Runbook

This runbook captures the working GCP setup for the TRAQ server in `traq-server-cloud`.

## Scope
- Deploy FastAPI server to Cloud Run
- Use private-IP Cloud SQL for PostgreSQL
- Use GCS for artifacts
- Use Secret Manager for runtime secrets
- Use Cloud Run Job for Alembic migrations

## Project
- Project ID: `traq-server-cloud`
- Region: `us-west1`
- Organization: `hammerdirt.solutions`

## Resource Inventory

### Artifact Registry
- Repository: `traq-images`
- Image used:
  - `us-west1-docker.pkg.dev/traq-server-cloud/traq-images/traq-server:initial`

### Cloud Run
- Service: `traq-server`
- Migration job: `traq-migrate`
- Runtime service account:
  - `traq-runner@traq-server-cloud.iam.gserviceaccount.com`

### Cloud SQL
- Instance: `traq-postgres`
- Connection name: `traq-server-cloud:us-west1:traq-postgres`
- VPC: `default`
- Private IP: `10.0.16.3`
- Public IP: disabled

### PostgreSQL objects
- Database: `traq`
- Login role used by app: `traq_run`

### Cloud Storage
- Bucket: `traq-server-artifacts-traq-server-cloud`
- Prefix: `prod/`

### Secrets
- `TRAQ_API_KEY`
- `OPENAI_API_KEY`
- `TRAQ_DATABASE_URL`

## Required APIs
Enable:
- Cloud Run Admin API
- Cloud SQL Admin API
- Artifact Registry API
- Secret Manager API
- Cloud Storage API
- Cloud Build API
- Compute Engine API

## Working Network Model

### Cloud SQL
- Private IP enabled
- Private Service Access enabled on VPC `default`

### Cloud Run service and job
Both must have:
- Serverless VPC Access connector: `traq-run-connector`
- Traffic routing: `route only requests to private IPs to the VPC`

Important:
- The Cloud Run service and Cloud Run job are configured separately.
- Fixing networking on the service does not fix the migration job.

## Runtime Secrets

### Working database URL
`TRAQ_DATABASE_URL` must be a full DSN secret, not composed from a password env var.

Working format:
```text
postgresql+psycopg://<db_user>:<db_password>@<private_ip>:5432/traq
```

Notes:
- Use the real PostgreSQL database name, not the instance name.
- Use the real PostgreSQL login role, not an assumed name.
- Do not record the live password in docs; read the current value from Secret Manager.

## Cloud Run Service Configuration

### Service
- Name: `traq-server`
- Allow public access: yes
- Container port: `8000`
- Image:
  - `us-west1-docker.pkg.dev/traq-server-cloud/traq-images/traq-server:initial`

### Service account
- `traq-runner@traq-server-cloud.iam.gserviceaccount.com`

### Env vars
- `TRAQ_ARTIFACT_BACKEND=gcs`
- `TRAQ_GCS_BUCKET=traq-server-artifacts-traq-server-cloud`
- `TRAQ_GCS_PREFIX=prod/`
- `TRAQ_ENABLE_DISCOVERY=false`
- `TRAQ_AUTO_CREATE_SCHEMA=false`
- `TRAQ_ENABLE_FILE_LOGGING=false`

### Secret env vars
- `TRAQ_API_KEY` from secret `TRAQ_API_KEY`
- `OPENAI_API_KEY` from secret `OPENAI_API_KEY`
- `TRAQ_DATABASE_URL` from secret `TRAQ_DATABASE_URL`
- `TRAQ_PLANTNET_API_KEY` from secret `TRAQ_PLANTNET_API_KEY`

### Networking
- VPC connector: `traq-run-connector`
- Route only private IPs to VPC

## Cloud Run Migration Job Configuration

### Job
- Name: `traq-migrate`
- Image:
  - `us-west1-docker.pkg.dev/traq-server-cloud/traq-images/traq-server:initial`

### Command
```text
uv
```

### Arguments
```text
run
alembic
upgrade
head
```

### Env vars
- `TRAQ_ENABLE_DISCOVERY=false`
- `TRAQ_AUTO_CREATE_SCHEMA=false`
- `TRAQ_ENABLE_FILE_LOGGING=false`

### Secret env vars
- `TRAQ_DATABASE_URL` from secret `TRAQ_DATABASE_URL`

### Networking
- VPC connector: `traq-run-connector`
- Route only private IPs to VPC

Important:
- Do not use the old shell-based export of `TRAQ_DATABASE_URL` from `TRAQ_DB_PASSWORD`.
- Do not leave the typo `fasle`; it must be `false`.

## PostgreSQL Setup
Use Cloud SQL Studio.

### Create app database
```sql
CREATE DATABASE traq;
```

### Create/fix app role
```sql
ALTER ROLE traq_run WITH LOGIN PASSWORD '<db_password>';
GRANT CONNECT ON DATABASE traq TO traq_run;
```

### Grant permissions in database `traq`
```sql
GRANT USAGE ON SCHEMA public TO traq_run;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO traq_run;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO traq_run;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO traq_run;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO traq_run;
```

## Deployment Sequence

### 1. Build and push image
```bash
gcloud auth configure-docker us-west1-docker.pkg.dev
cd /home/roger/projects/codex_trial/agent_client/server
docker build -t us-west1-docker.pkg.dev/traq-server-cloud/traq-images/traq-server:initial .
docker push us-west1-docker.pkg.dev/traq-server-cloud/traq-images/traq-server:initial
```

### 2. Ensure DB objects exist
- Cloud SQL instance exists
- database `traq` exists
- role `traq_run` exists and can login
- `TRAQ_DATABASE_URL` secret matches the actual DB role/password/DB name

### 3. Run migration job
- Execute `traq-migrate`
- Wait for success

### 4. Deploy service revision
- Deploy `traq-server`
- Ensure latest revision gets 100% traffic

## Remote Admin Workflow

The cloud operator workflow is now:

1. device registers via `POST /v1/auth/register-device`
2. operator reviews pending devices over admin HTTP
3. operator approves one device
4. operator issues a device token

Working one-shot CLI examples from a laptop:

```bash
cd /home/roger/projects/codex_trial/agent_client/server
UV_CACHE_DIR=/tmp/uv-cache uv run traq-admin device pending \
  --host https://traq-server-589591848994.us-west1.run.app \
  --api-key '<TRAQ_API_KEY>'

UV_CACHE_DIR=/tmp/uv-cache uv run traq-admin device approve <device_id> --role arborist \
  --host https://traq-server-589591848994.us-west1.run.app \
  --api-key '<TRAQ_API_KEY>'

UV_CACHE_DIR=/tmp/uv-cache uv run traq-admin device issue-token <device_id> --ttl 604800 \
  --host https://traq-server-589591848994.us-west1.run.app \
  --api-key '<TRAQ_API_KEY>'
```

Important:
- `traq-admin` does not accept global `--host` / `--api-key`
- pass `--host` and `--api-key` on the specific `device` or `job` subcommand

## Verified Local Tree-Identification Smoke Test

Verified command:

```bash
cd /home/roger/projects/codex_trial/agent_client/server
uv run traq-admin tree identify \
  --image ./bark.jpg \
  --organ bark \
  --host http://127.0.0.1:8000 \
  --api-key demo-key
```

Verified result characteristics:
- request succeeded through the local TRAQ server
- Pl@ntNet response was normalized into the canonical server payload
- observed top-level keys:
  - `query`
  - `predictedOrgans`
  - `bestMatch`
  - `results`
  - `otherResults`
  - `version`
  - `remainingIdentificationRequests`
- observed sample:
  - `bestMatch = Castanopsis sieboldii (Makino) Hatus.`
  - `version = 2026-02-17 (7.4)`
  - `remainingIdentificationRequests = 499`

Notes from the working smoke test:
- the CLI `--api-key` is the TRAQ server admin key, not the Pl@ntNet key
- the server process itself must have `TRAQ_PLANTNET_API_KEY`
- Pl@ntNet key restrictions had to allow the caller public IP
- optional false-valued multipart flags had to be omitted from the upstream request

## GitHub Actions Deployment Automation

Repo workflow:
- `.github/workflows/server-cloudrun.yml`

Required GitHub repository secrets:
- `GCP_WORKLOAD_IDENTITY_PROVIDER`
- `GCP_DEPLOYER_SERVICE_ACCOUNT`

Required GitHub repository variables:
- `GCP_PROJECT_ID`
- `GCP_REGION`
- `GCP_ARTIFACT_REPOSITORY`
- `GCP_IMAGE_NAME`
- `GCP_CLOUD_RUN_SERVICE`
- `GCP_CLOUD_RUN_JOB`
- `GCP_RUNTIME_SERVICE_ACCOUNT`
- `GCP_VPC_CONNECTOR`
- `GCP_GCS_BUCKET`
- optional `GCP_GCS_PREFIX`

Workflow behavior:
1. run server unit tests
2. build and push image to Artifact Registry
3. update the migration job to the new image
4. execute the migration job and wait for success
5. deploy the Cloud Run service with the new image

The workflow assumes these fixed Secret Manager names already exist in GCP:
- `TRAQ_API_KEY`
- `OPENAI_API_KEY`
- `TRAQ_DATABASE_URL`
- `TRAQ_PLANTNET_API_KEY`

## Verification

### Health
```bash
curl https://traq-server-589591848994.us-west1.run.app/health
```

### Admin auth
```bash
curl -H 'X-API-Key: <TRAQ_API_KEY>' \
  https://traq-server-589591848994.us-west1.run.app/v1/jobs/assigned
```

### Device registration
```bash
curl -X POST "https://traq-server-589591848994.us-west1.run.app/v1/auth/register-device" \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "gcp-test-device-1",
    "device_name": "GCP Test Device",
    "app_version": "0.1.0",
    "profile_summary": {
      "name": "Test Operator"
    }
  }'
```

Current status:
- `/health` works
- admin auth works
- device registration works

## Failure Modes We Actually Hit

### 1. Wrong DB transport assumption
- Unix socket `/cloudsql/...` was wrong for this private-IP + VPC-connector setup.
- Correct path is direct private IP `10.0.16.3:5432`.

### 2. Wrong DB user assumption
- We assumed `traq_app`.
- Actual roles showed `traq-app` and `traq_run`.
- App now uses `traq_run`.

### 3. Wrong DB name assumption
- We assumed database `traq` already existed.
- It did not.
- The instance name `traq-postgres` is not the database name.

### 4. Migration job config drift
- Job had `TRAQ_ENABLE_FILE_LOGGING=fasle`
- Job also needed the same VPC connector/routing as the service

### 5. Service and job networking are separate
- The service can work while the job still times out.
- Both need the VPC connector configuration.

## Next Work
1. Add real Pl@ntNet API key to Secret Manager as `TRAQ_PLANTNET_API_KEY`
2. Smoke-test `POST /v1/trees/identify` locally and from Cloud Run
3. Run the first GitHub Actions deploy using the tree-identification endpoint changes
2. Run one full cloud roundtrip job
3. Migrate selected local jobs (`J0004`, `J0005`, `J0007`, plus one more)
4. Automate build/migrate/deploy from GitHub
