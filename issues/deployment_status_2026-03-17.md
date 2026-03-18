# Deployment Status 2026-03-17

## Purpose

Record the current deployment readiness state of the standalone `server/` repo
before containerization and first GCP deployment work begins.

## Current Ready State

The server is now in a deployable engineering shape, subject to containerization
and cloud runtime validation.

Confirmed state:

- standalone `server/` repo is active and versioned independently
- `uv` is the primary package and command workflow
- console entrypoints work:
  - `traq-server`
  - `traq-admin`
- runtime operational state is DB-authoritative
- filesystem authority has been reduced to artifact bytes and exported
  debug/compatibility copies only
- artifact storage boundary exists
- local and GCS artifact backends both exist
- cloud-safe runtime flags exist:
  - `TRAQ_ENABLE_DISCOVERY`
  - `TRAQ_AUTO_CREATE_SCHEMA`
  - `TRAQ_ENABLE_FILE_LOGGING`
  - `TRAQ_ARTIFACT_BACKEND`
  - `TRAQ_GCS_BUCKET`
  - `TRAQ_GCS_PREFIX`
- Alembic baseline exists and the working database is aligned to it
- Sphinx docs build cleanly from source
- manual end-to-end device workflow has been retested successfully after the
  migration and repo-hardening work

## Validated Runtime Capabilities

Validated locally:

- device registration / approval / auth
- assigned job fetch
- restored job hydration
- form edits surviving review submit
- audio upload and transcription
- image upload and metadata update
- final generation
- finalized job unassignment
- completed job surviving `Check for New Jobs` after the client sync fix path
- Alembic baseline applying to an empty PostgreSQL schema

## Deployment-Relevant Decisions Already Made

### App runtime

Planned target:

- Cloud Run

### Database

Planned target:

- PostgreSQL
- Alembic-managed migrations for deployed schema changes

### Artifact storage

Planned target:

- Google Cloud Storage

Current policy:

- artifact downloads are app-streamed for the initial cloud deployment
- signed URLs are deferred

### Cloud runtime policy

Expected cloud settings:

- `TRAQ_ENABLE_DISCOVERY=false`
- `TRAQ_AUTO_CREATE_SCHEMA=false`
- `TRAQ_ENABLE_FILE_LOGGING=false`
- `TRAQ_ARTIFACT_BACKEND=gcs`
- `TRAQ_GCS_BUCKET=<bucket>`
- optional `TRAQ_GCS_PREFIX=<prefix>`

## Known Open Issues

### 1. Archived job auto-claim is too permissive

Tracked in:

- `issues/archived_job_auto_claim_too_permissive.md`

This is not a deployment blocker, but it is a lifecycle control issue that
should be addressed after deployment basics are in place.

### 2. Containerization is not implemented yet

No `Dockerfile` or `.dockerignore` exists yet.

This is the next concrete deployment task.

### 3. Cloud deployment workflow is not automated yet

Still missing:

- container image build/publish workflow
- migration execution workflow for deployed environments
- runtime service deployment workflow on GCP

### 4. Real GCS integration has not been validated in a deployed runtime

The backend exists and local tests pass, but real bucket-backed runtime testing
still needs to happen.

## Recommended Next Steps

1. Add containerization:
   - `Dockerfile`
   - `.dockerignore`
   - runtime image with ffprobe/ffmpeg available

2. Define first deployment workflow:
   - build image
   - publish image
   - run Alembic upgrade
   - deploy app revision

3. Validate cloud runtime behavior:
   - Cloud Run startup
   - Cloud SQL connection
   - GCS artifact reads/writes
   - final artifact generation and download

4. After first deployment is stable, tighten lifecycle issues:
   - archived job auto-claim
   - optional signed URL strategy
   - broader deployment automation

## Practical Conclusion

The repo is ready to move into Docker/GCP deployment work.

The remaining work is now deployment integration, not core server architecture
cleanup.
