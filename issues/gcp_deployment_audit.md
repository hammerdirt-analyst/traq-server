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

### 1. Artifact storage is still path-based in runtime code

Current runtime still writes and reads local filesystem paths directly for:

- audio upload storage
- image upload storage
- report image storage
- final PDF / DOCX / GeoJSON outputs
- final report download responses via `FileResponse`

Representative locations:

- `app/main.py`
- `app/services/inspection_service.py`

Impact:

- this is not compatible with Cloud Run as the long-term storage model
- a Cloud Storage-backed artifact service is still required

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

### 4. Service discovery is still enabled by default

Current behavior:

- mDNS / zeroconf advertiser is wired into startup
- discovery is useful on LAN, not in cloud deployment

Representative locations:

- `app/main.py`
- `app/service_discovery.py`

Impact:

- cloud deployment should disable discovery explicitly
- this should be environment-gated

Severity:

- **medium**

### 5. Profile / artifact metadata now depend on DB tables being present

Current behavior:

- local/dev startup creates missing tables automatically
- that fixed the `runtime_profiles` issue

Impact:

- this is good for local/dev continuity
- but reinforces the need for an explicit migration path before production deployment

Severity:

- **medium**

### 6. Final/report downloads assume local files are directly readable

Current behavior:

- endpoints return `FileResponse` from local paths

Representative location:

- `app/main.py`

Impact:

- this will need a storage abstraction for Cloud Storage
- either:
  - stream bytes from GCS
  - or generate signed URLs

Severity:

- **high**

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

### Phase 2 — Introduce artifact storage abstraction

Do next:

- create a storage service boundary for:
  - audio writes/reads
  - image writes/reads
  - report image writes/reads
  - final artifact writes/reads
- implement:
  - local filesystem backend
  - Cloud Storage backend

### Phase 3 — Cloud deployment controls

Do next:

- add explicit env flag to disable discovery in cloud
- document required secrets
- prepare Dockerfile / `.dockerignore`

### Phase 4 — Download/serve strategy for cloud artifacts

Do next:

- decide whether download endpoints should:
  - stream from Cloud Storage through the app
  - or issue signed URLs

## Practical Summary

If deployment started today:

- **Cloud SQL** is conceptually ready enough for local-style use
- **Cloud Run** is **not** fully ready because artifact storage and downloads still rely on local filesystem semantics
- **Cloud Storage** integration is the biggest remaining architectural step

## Immediate Highest-Value Fixes

1. add storage abstraction for artifacts
2. disable discovery in cloud environments
3. formalize migration policy for production

## Conclusion

The server is no longer blocked by old metadata architecture.

The remaining GCP blockers are now concrete and narrow:

- artifact storage abstraction
- job number allocation
- production migration discipline
- cloud-specific runtime flags

That is a good place to be.
