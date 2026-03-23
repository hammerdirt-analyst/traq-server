# traq-server

`traq-server` is the server for a capture-first tree risk assessment workflow.

It continues the work started in `handsfreetraq`: observations are captured in the field as audio and images, then turned into structured assessment data on the server. This repo adds the server-side job lifecycle, review artifacts, final submission, archival outputs, and standalone tree identification.

## What matters here

- **TRAQ-aligned structure**
  The server builds against a canonical TRAQ mapping instead of treating the form as loose text.
- **Structured extraction**
  Extraction is done with validated models and shared extractor utilities, so outputs are consistent and machine-usable.
- **Geospatial output**
  GeoJSON is part of the storage/export model, which keeps the assessment useful for mapping and inventory workflows.
- **Standalone tree identification**
  `POST /v1/trees/identify` accepts up to five images outside the job lifecycle and returns a canonical normalized response.

## Quick start

```bash
uv sync
uv run traq-server --reload --port 8000
```

In another terminal:

```bash
uv run traq-admin local
```

## Workflow

1. A client creates a job and uploads section recordings and images.
2. The server processes a round and returns a review package.
3. The client submits a final or correction payload.
4. The server writes final artifacts and archives the job.

## Verified cloud workflow

1. Register device: `POST /v1/auth/register-device`
2. Approve device: `uv run traq-admin cloud device approve <device_id> --role arborist`
3. Issue token: `uv run traq-admin cloud device issue-token <device_id> --ttl 604800`
4. Start job: `POST /v1/jobs`, then `POST /v1/jobs/{job_id}/rounds`
5. Upload media: section recordings and `job_photos` images
6. Submit review: `POST /v1/jobs/{job_id}/rounds/{round_id}/submit`
7. Finalize: `POST /v1/jobs/{job_id}/final`
8. Download docs: `GET /v1/jobs/{job_id}/final/report`

## Main endpoints

- `POST /v1/jobs`
- `POST /v1/jobs/{job_id}/rounds`
- `POST /v1/jobs/{job_id}/rounds/{round_id}/submit`
- `GET /v1/jobs/{job_id}/rounds/{round_id}/review`
- `POST /v1/jobs/{job_id}/final`
- `GET /v1/jobs/{job_id}/final/report`
- `POST /v1/trees/identify`

## Auth boundaries

- Bootstrap endpoints are intentionally open:
  - `POST /v1/auth/register-device`
  - `GET /v1/auth/device/{device_id}/status`
  - `POST /v1/auth/token`
- Normal client requests use issued device tokens.
- Operator workflows use `traq-admin` and the server admin key.

## Admin CLI contexts

- `uv run traq-admin local`
  - local mode
  - uses local services/store for operator workflows
- `uv run traq-admin cloud`
  - remote mode
  - uses `TRAQ_CLOUD_ADMIN_BASE_URL` and `TRAQ_CLOUD_API_KEY`
  - talks to the live server over HTTP only
- one-shot commands can also be context-prefixed:
  - `uv run traq-admin cloud device pending`
  - `uv run traq-admin local tree identify --image ./leaf.jpg --organ leaf`

Mode rule:

- local mode must not silently use remote HTTP as its execution boundary
- remote mode must not silently use local DB/service/file inspection as its execution boundary
- if a remote command is unsupported because the server endpoint does not exist, the CLI should fail explicitly

For covered workflows, current limitations, and smoke-test examples, see
`docs/cli_operations_model.rst`.

## Key docs

- `docs/architecture.rst`
- `docs/api/index.rst`
- `docs/tree_identity_contract.rst`
- `docs/cli_operations_model.rst`
- `app/README.md`

## Setup notes

- local development can put environment variables in `.env`; `app/config.py` loads that file without overriding already-exported values
- the current deployment target is Cloud Run
- deploy automation is intended to run from GitHub Actions on `main`; active development should happen on feature branches

## Release notes

- Cloud end-to-end workflow is now verified on Cloud Run.
- Remote operator path is in place for device approval and token issuance.
- Admin CLI mode selection is now explicit:
  - local mode uses local service/store access
  - remote mode uses HTTP only
- Remote admin inspection/download endpoints now exist for:
  - job inspect
  - round inspect
  - review inspect
  - final inspect
  - artifact fetch
- Round submit now supplements non-empty manifests with DB-backed recordings so uploaded audio is not dropped from processing.
- Generated cloud artifacts follow the backend contract:
  - direct payloads use `write_bytes` / `write_text`
  - generated outputs use `stage_output` / `commit_output`
- Final report download now checks artifact existence before materializing a GCS object and falls back correctly from correction to final report.
- Process rule: do not act on unverified assumptions; verify object existence and runtime contracts first.
