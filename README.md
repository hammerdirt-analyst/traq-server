# Demo Server
Authors: Roger Erismann (https://hammerdirt.solutions), OpenAI Codex

Local demo server for Tree Risk assessment.

## Setup

- Install `uv`
- Sync the standalone repo environment:
  - `uv sync`
- Run commands through `uv`:
  - `uv run traq-server --reload --port 8000`
  - `uv run traq-admin`

Optional:

- direct editable install still works:
  - `pip install -e .`

### Documentation publishing

The repo is set up for GitHub Pages to build documentation from source in CI.

- workflow: `.github/workflows/docs.yml`
- source docs: `docs/`
- generated HTML remains local-only and ignored:
  - `docs/_build/`

GitHub Pages should be configured to publish from the GitHub Actions workflow,
not from committed generated HTML.

### PostgreSQL baseline

The server is moving to PostgreSQL as the primary metadata/state store.

- PostgreSQL driver: `psycopg[binary]`
- SQL toolkit/migrations:
  - `sqlalchemy`
  - `alembic`

Example runtime database URL:

- `postgresql+psycopg://traq_app:change-this-password@127.0.0.1:5432/traq_demo`

### Alembic workflow

Use Alembic for explicit schema changes.

Local/dev:

- keep `TRAQ_AUTO_CREATE_SCHEMA=true` if you want automatic bootstrap for ad hoc work
- generate a migration:
  - `uv run alembic revision --autogenerate -m "describe change"`
- inspect the migration before applying it
- apply migrations:
  - `uv run alembic upgrade head`

Existing database adopting Alembic for the first time:

- after reviewing the baseline migration, record the current schema state:
  - `uv run alembic stamp head`

Cloud/production:

- set `TRAQ_AUTO_CREATE_SCHEMA=false`
- run:
  - `uv run alembic upgrade head`
- deploy the app only after migrations succeed

## Run

- `uv run traq-server --reload --port 8000`
- direct module form also works:
  - `uv run python -m app.server_cli --reload --port 8000`

## Container

Build the image:

- `docker build -t traq-server:local .`

Run the image locally:

- `docker run --rm -p 8000:8000 \`
  `-e TRAQ_DATABASE_URL=postgresql+psycopg://traq_app:<password>@host.docker.internal:5432/traq_demo \`
  `-e TRAQ_API_KEY=demo-key \`
  `-e OPENAI_API_KEY=<key> \`
  `traq-server:local`

Cloud-oriented defaults baked into the image:

- `TRAQ_ENABLE_DISCOVERY=false`
- `TRAQ_AUTO_CREATE_SCHEMA=false`
- `TRAQ_ENABLE_FILE_LOGGING=false`

For Cloud Run, also set:

- `TRAQ_ARTIFACT_BACKEND=gcs`
- `TRAQ_GCS_BUCKET=<bucket>`
- optional `TRAQ_GCS_PREFIX=<prefix>`

Default API key: `demo-key` (set `TRAQ_API_KEY` to change).

For beta, treat `TRAQ_API_KEY` as an operator-only credential:

- use it for `traq-admin` and controlled operator scripts
- do not put it on field devices
- do not prompt for it during device registration
- do not treat the mobile client as an admin surface

Default local artifact storage:

- `TRAQ_STORAGE_ROOT` defaults to `./local_data`
- this directory is repo-local and git-ignored
- artifact bytes and generated outputs live there; runtime authority is in PostgreSQL
- set `TRAQ_ARTIFACT_BACKEND=gcs` to use Google Cloud Storage
- when using GCS, set:
  - `TRAQ_GCS_BUCKET`
  - optional `TRAQ_GCS_PREFIX`
- set `TRAQ_ENABLE_DISCOVERY=false` in cloud deployments
- set `TRAQ_AUTO_CREATE_SCHEMA=false` in cloud deployments
- set `TRAQ_ENABLE_FILE_LOGGING=false` in cloud deployments
- current cloud download strategy is app-streamed artifact responses, not signed URLs

## Admin CLI

Required environment:

- `TRAQ_DATABASE_URL=postgresql+psycopg://traq_app:<password>@127.0.0.1:5432/traq_demo`
- optional `TRAQ_ADMIN_BASE_URL=http://127.0.0.1:8000`
- local development can put these in `.env`; `app/config.py` loads that file automatically without overriding already-exported variables

Interactive mode:

- `uv run traq-admin`
- inside the REPL, use the same commands as one-shot mode; a leading `/` is optional, for example `/round reopen --job-id job_1 --round-id round_1`
- customer and billing records have short operator-facing codes, for example `C0001` and `B0001`

Examples:

- `traq-admin device pending`
- `traq-admin device validate --index 1 --role arborist`
- `traq-admin customer create --name "Customer Name" --phone "555-1212" --address "123 Oak St"`
- `traq-admin customer duplicates`
- `traq-admin customer usage C0001`
- `traq-admin customer merge C0002 --into C0001`
- `traq-admin customer delete C0008`
- `traq-admin customer billing create --billing-name "Customer Name" --billing-address "123 Oak St"`
- `traq-admin customer billing duplicates`
- `traq-admin customer billing usage B0001`
- `traq-admin customer billing merge B0002 --into B0001`
- `traq-admin customer billing delete B0001`
- `traq-admin job create --job-id job_1 --job-number J0001 --customer-id C0001 --billing-profile-id B0001 --tree-number 1 --job-name "Valley Oak"`
- `traq-admin job update --job J0001 --customer-id C0001 --billing-profile-id B0001 --tree-number 2 --job-name "Valley Oak Revisit" --status REVIEW_RETURNED`
- `traq-admin job inspect --job J0001`
- `traq-admin round inspect --job J0001 --round-id round_1`
- `traq-admin review inspect --job J0001 --round-id round_1`
- `traq-admin final inspect --job J0001`
- `traq-admin final set-final --job J0001 --from-json ./final.json [--geojson-json ./final.geojson]`
- `traq-admin final set-correction --job J0001 --from-json ./final_correction.json [--geojson-json ./final_correction.geojson]`

Full CLI reference:

- `app/README.md`
- `docs/cli_operations_model.rst`
- `docs/deployment_operations.rst`

## Local Discovery

- The server can advertise itself on the local network via mDNS / DNS-SD as `_traq._tcp.local`.
- Android clients can browse discovered TRAQ servers from Profile / Settings.
- Install `zeroconf` from `requirements.txt` to enable advertisement.
- Optional discovery env vars:
  - `TRAQ_DISCOVERY_PORT` (default: `8000`)
  - `TRAQ_DISCOVERY_NAME` (default: `TRAQ Server`)

## Endpoints

Most endpoints require `X-API-Key: <key>`.

Bootstrap exceptions:

- `POST /v1/auth/register-device`
- `GET /v1/auth/device/{device_id}/status`
- `POST /v1/auth/token`

Those three endpoints are intentionally open for device bootstrap. Admin
approval still happens through the admin CLI/workflow, and the issued device
token is used for normal authenticated requests.

### Health

- `GET /health`
  - Returns basic server status and storage root.

### Auth and profile

- `POST /v1/auth/register-device`
  - Registers a device for approval.
- `GET /v1/auth/device/{device_id}/status`
  - Returns pending / approved / revoked device status.
- `POST /v1/auth/token`
  - Issues a device token for an approved device.
- `GET /v1/profile`
  - Returns the current device profile.
- `PUT /v1/profile`
  - Updates the current device profile.

### Jobs

- `POST /v1/jobs`
  - Creates a server job and returns authoritative job metadata including `job_id`, `job_number`, `status`, and `tree_number`.

- `GET /v1/jobs/assigned`
  - Returns jobs assigned to the authenticated device.

- `GET /v1/jobs/{job_id}`
  - Returns job status, latest round info, and server-authoritative `tree_number`.

### Rounds

- `POST /v1/jobs/{job_id}/rounds`
  - Creates a new round in `DRAFT`.

- `PUT /v1/jobs/{job_id}/rounds/{round_id}/manifest`
  - Replaces the round manifest. Body: list of manifest items.

- `POST /v1/jobs/{job_id}/rounds/{round_id}/submit`
  - Submits the round for processing and resolves authoritative `tree_number`.

- `POST /v1/jobs/{job_id}/rounds/{round_id}/reprocess`
  - Resubmits round recordings for processing.

- `GET /v1/jobs/{job_id}/rounds/{round_id}/review`
  - Returns cached/generated review payload including transcript, form, narrative, and canonical `tree_number`.

### Media uploads (local storage)

- `PUT /v1/jobs/{job_id}/sections/{section_id}/recordings/{recording_id}`
  - Accepts raw audio bytes, writes to `local_data/jobs/<job_id>/sections/<section_id>/recordings/`.

- `PUT /v1/jobs/{job_id}/sections/{section_id}/images/{image_id}`
  - Accepts raw image bytes, writes to `local_data/jobs/<job_id>/sections/<section_id>/images/`.

- `PATCH /v1/jobs/{job_id}/sections/{section_id}/images/{image_id}`
  - Persists caption/GPS updates into the image metadata JSON.

### Final submit

- `POST /v1/jobs/{job_id}/final`
  - Accepts final or correction payload, writes final artifacts, marks job archived, and preserves correction output separately when applicable.

- `GET /v1/jobs/{job_id}/final/report`
  - Returns the current report PDF for the job.

### Admin endpoints

- `GET /v1/admin/jobs/assignments`
  - Lists current device/job assignments.
- `POST /v1/admin/jobs/{job_id}/assign`
  - Assigns or reassigns a job to a device.
- `POST /v1/admin/jobs/{job_id}/unassign`
  - Removes a device assignment from a job.
- `POST /v1/admin/jobs/{job_id}/status`
  - Updates job status and, optionally, round status.
- `POST /v1/admin/jobs/{job_id}/rounds/{round_id}/reopen`
  - Reopens a round back to `DRAFT`.

## Storage layout

- `local_data/jobs/<job_id>/sections/<section_id>/recordings/<recording_id>.<ext>`
- `local_data/jobs/<job_id>/sections/<section_id>/recordings/<recording_id>.meta.json`
- `local_data/jobs/<job_id>/sections/<section_id>/images/<image_id>.<ext>`
- `local_data/jobs/<job_id>/sections/<section_id>/images/<image_id>.meta.json`
- `local_data/jobs/<job_id>/rounds/<round_id>/review.json`
- `local_data/jobs/<job_id>/final.json`
- `local_data/jobs/<job_id>/final_correction.json`

These JSON files are exported debug/compatibility copies. Runtime authority is
in PostgreSQL. Artifact bytes and generated outputs remain on disk.

## Config

Environment variables:

- `TRAQ_API_KEY` (default: demo-key)
- `TRAQ_STORAGE_ROOT` (default: ./local_data)
- `TRAQ_ARTIFACT_BACKEND` (default: `local`; valid values: `local`, `gcs`)
- `TRAQ_GCS_BUCKET` (required when `TRAQ_ARTIFACT_BACKEND=gcs`)
- `TRAQ_GCS_PREFIX` (optional object prefix when `TRAQ_ARTIFACT_BACKEND=gcs`)
- `TRAQ_ENABLE_DISCOVERY` (default: `true`; set to `false` in cloud)
- `TRAQ_AUTO_CREATE_SCHEMA` (default: `true`; set to `false` in cloud and run migrations explicitly)
- `TRAQ_ENABLE_FILE_LOGGING` (default: `true`; set to `false` in cloud to use stdout/stderr only)
- `TRAQ_DATABASE_URL` (required: `postgresql+psycopg://traq_app:<password>@127.0.0.1:5432/traq_demo`)
- `TRAQ_ADMIN_BASE_URL` (default: `http://127.0.0.1:<TRAQ_DISCOVERY_PORT>`)
- `TRAQ_DISCOVERY_PORT` (default: 8000)
- `TRAQ_DISCOVERY_NAME` (default: TRAQ Server)
- `OPENAI_API_KEY` (required for extractor calls)
- `TRAQ_OPENAI_MODEL` (default: gpt-4o-mini)
- `TRAQ_OPENAI_TRANSCRIBE_MODEL` (default: gpt-4o-mini-transcribe)

## Current docs

- runtime and CLI details: `app/README.md`
- CLI/service model: `docs/cli_operations_model.rst`
- DB schema: `docs/database_schema.rst`
- DB workflow: `docs/database_workflow.rst`
- tree identity contract: `docs/tree_identity_contract.rst`
- runtime/export boundary: `docs/runtime_export_boundary.rst`

## API docs (Sphinx)

Doc source is in `docs/` and uses autodoc + napoleon.

- Build:
  - `uv run sphinx-build -E -b html docs docs/_build/html`
- Open:
  - `docs/_build/html/index.html`
