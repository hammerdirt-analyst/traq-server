# GCP Deployment Audit

## Purpose

Audit the current standalone server repo against the intended GCP target:

- Cloud Run
- Cloud SQL for PostgreSQL
- Cloud Storage for artifacts

This is a deployment-readiness audit, not a full implementation plan.

## Current Position

The repo is in a much better state than before:

- runtime operational state is DB-authoritative
- standalone repo hardening is complete
- `uv` bootstrap works
- local device workflow is working
- finalized jobs are now unassigned after final submission

So the remaining work is no longer general cleanup. It is deployment-specific.

## Main Findings

### 1. Artifact storage now has a runtime boundary, but only a local backend

Current runtime now routes artifact access through a storage boundary, but the
only implemented backend is still local filesystem storage.

Covered runtime flows now include:

- audio upload storage
- image upload storage
- report image storage
- final PDF / DOCX / GeoJSON outputs
- final report download responses via `FileResponse`

Representative locations:

- `app/artifact_storage.py`
- `app/main.py`

Impact:

- local path usage is now concentrated behind one runtime boundary
- a Cloud Storage-backed backend is still required before Cloud Run deployment
- inspection/admin paths outside runtime are not yet part of this abstraction

Severity:

- **high**

### 2. Job number allocation is now DB-backed

Current behavior:

- job number allocation now uses a DB-authoritative runtime counter
- the old local counter file dependency has been removed from runtime allocation

Representative locations:

- `app/db_models.py`
- `app/db_store.py`
- `app/main.py`

Impact:

- this is now compatible with multi-instance allocation semantics
- this removes one remaining non-artifact filesystem dependency

Severity:

- **resolved**

### 3. Schema bootstrap is still startup-driven

Current behavior:

- server startup now calls `create_schema()` after `init_database()`

Representative locations:

- `app/main.py`
- `app/db.py`

Impact:

- acceptable for local/dev
- not the final production posture for Cloud Run + Cloud SQL
- deployed environments should move to explicit migrations rather than startup schema creation

Severity:

- **high for production discipline**, but not a blocker for local/dev

### 4. Service discovery is now environment-gated

Current behavior:

- mDNS / zeroconf advertiser is wired into startup
- `TRAQ_ENABLE_DISCOVERY` now gates it explicitly
- discovery is useful on LAN, not in cloud deployment

Representative locations:

- `app/main.py`
- `app/service_discovery.py`

Impact:

- cloud deployment should set `TRAQ_ENABLE_DISCOVERY=false`
- no additional runtime refactor is required

Severity:

- **resolved with deployment config**

### 5. Profile / artifact metadata now depend on DB tables being present

Current behavior:

- local/dev startup creates missing tables automatically
- that fixed the `runtime_profiles` issue

Impact:

- this is good for local/dev continuity
- but reinforces the need for an explicit migration path before production deployment

Severity:

- **medium**

### 6. Final/report downloads still need an explicit cloud policy

Current behavior:

- endpoints still return app-streamed responses
- artifact materialization can now come from the selected backend

Representative location:

- `app/main.py`

Impact:

- the storage abstraction now supports backend materialization
- the remaining choice is the deployment policy for downloads
- initial deployment can keep app-streamed responses and defer signed URLs

Severity:

- **resolved for initial deploy if app-streamed downloads are accepted**

### 7. ffprobe remains a runtime host dependency

Current behavior:

- audio probe/transcode logic uses `TRAQ_FFPROBE_BIN` or `ffprobe`

Representative location:

- `app/main.py`

Impact:

- container image must include ffprobe/ffmpeg tooling
- this is not a design blocker, but it is a deployment requirement

Severity:

- **medium**

### 8. OpenAI connectivity is an external runtime dependency

Current behavior:

- extraction and report summary generation require `OPENAI_API_KEY`
- network connectivity to OpenAI is required at runtime

Representative locations:

- `app/main.py`
- `app/report_letter.py`
- `app/extractors/common.py`

Impact:

- Cloud Run service must have outbound internet access
- secret injection must be configured correctly

Severity:

- **medium**

## What Is Not A Major Blocker Now

### A. Devices / auth / assignments

These are DB-backed and operationally suitable for deployment.

### B. Runtime JSON state

The old filesystem authority problem is no longer the main deployment blocker.

### C. Repo/package shape

The standalone repo is in acceptable shape for containerization.

## Recommended Next Engineering Order

### Phase 1 — Deployment-safe database policy

Do next:

- define production migration policy
- move toward Alembic-managed schema changes
- stop treating startup `create_schema()` as the production contract

### Phase 2 — Wire and validate the Cloud Storage backend

Do next:

- keep the existing local backend
- the runtime code now has a `GCSArtifactStore`
- validate backend selection and dependency install in the deployed environment
- verify runtime flows against GCS for:
  - audio writes/reads
  - image writes/reads
  - report image writes/reads
  - final artifact writes/reads
- keep app-streamed downloads for the initial deployment

### Phase 3 — Cloud deployment controls

Do next:

- set `TRAQ_ENABLE_DISCOVERY=false` in cloud
- document required secrets
- prepare Dockerfile / `.dockerignore`

### Phase 4 — Production migration and containerization

Do next:

- define migration execution outside app startup
- prepare Dockerfile / `.dockerignore`
- define runtime secrets and service account requirements

## Practical Summary

If deployment started today:

- **Cloud SQL** is conceptually ready enough for local-style use
- **Cloud Run** is **not** fully ready because the runtime storage boundary still needs a Cloud Storage backend
- **Cloud Storage** integration is the biggest remaining architectural step

## Immediate Highest-Value Fixes

1. add storage abstraction for artifacts
2. formalize migration policy for production
3. containerize the server for Cloud Run

## Conclusion

The server is no longer blocked by old metadata architecture.

The remaining GCP blockers are now concrete and narrow:

- artifact storage abstraction
- job number allocation
- production migration discipline
- cloud-specific runtime flags

That is a good place to be.
