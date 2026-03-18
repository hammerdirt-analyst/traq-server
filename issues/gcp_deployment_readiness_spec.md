# GCP Deployment Readiness Spec

## Objective

Prepare the standalone `server/` repo for deployment to Google Cloud Platform with:

- the TRAQ API server running remotely
- PostgreSQL running remotely
- artifact storage moved off local disk when appropriate

This document is for deployment planning and execution order. It is not a code-change dump.

## Current Baseline

The server is now in a usable standalone-repo state.

Current state:

- runtime operational state is DB-authoritative
- local filesystem is limited to:
  - uploaded artifact bytes
  - generated outputs
  - exported debug/compatibility copies
- `uv` is the primary package/install workflow
- standalone entrypoints exist:
  - `traq-server`
  - `traq-admin`
- local device workflow has been tested successfully

This is the baseline we deploy from.

## Deployment Goal

Target a hosted runtime where:

- the API server runs from a remote GCP service
- PostgreSQL is a managed remote service
- secrets are injected through environment/config management
- artifacts no longer depend on local machine storage semantics

## Key Deployment Decisions

### 1. App Runtime Target

Choose one:

- Cloud Run
- GCE VM
- GKE

Current recommendation:

- start with **Cloud Run** unless there is a hard requirement for persistent local disk semantics

Why:

- simplest operational model
- easy env var/secret injection
- easy image-based deployment
- aligns well with stateless API runtime

Constraint:

- Cloud Run does **not** support local persistent artifact storage as an operational dependency
- that means artifact storage must move to cloud object storage if Cloud Run is selected

### 2. PostgreSQL Target

Choose one:

- Cloud SQL for PostgreSQL
- self-managed PostgreSQL on GCE

Current recommendation:

- start with **Cloud SQL for PostgreSQL**

Why:

- managed backups/patching
- straightforward connection model
- aligns with the server already treating PostgreSQL as authoritative runtime state

### 3. Artifact Storage Target

Choose one:

- Google Cloud Storage
- persistent local disk on a VM

Current recommendation:

- move artifacts to **Google Cloud Storage**

Why:

- uploaded audio/images and generated PDFs are the remaining local-storage dependency
- Cloud Run requires this anyway
- object storage is the right long-term fit for:
  - uploaded audio
  - uploaded images
  - report images
  - final PDFs/DOCX
  - exported GeoJSON if retained as files

## Current Gaps Before GCP Deployment

### A. Artifact storage is still local-path based

Today the server assumes:

- `TRAQ_STORAGE_ROOT`
- local file writes for audio/image uploads
- local file reads for report/final artifact serving

This is acceptable locally, but not the final cloud architecture if using Cloud Run.

### B. Database migration discipline needs a decision

The repo has:

- SQLAlchemy models
- schema bootstrap helpers
- Alembic dependency installed

But deployment needs one explicit policy:

- are schema changes managed only through migrations?
- is `create_schema()` still allowed in deployment?

Current recommendation:

- move to explicit Alembic migrations for deployed environments
- keep bootstrap helpers for local/dev only

### C. Secrets/config need deployment rules

At minimum:

- `TRAQ_DATABASE_URL`
- `TRAQ_API_KEY`
- `OPENAI_API_KEY`
- optional discovery/runtime flags

Need a deployment policy for:

- GCP Secret Manager vs plain env vars
- how admin CLI authenticates against deployed service

### D. Service discovery may not belong in cloud deployment

Local mDNS discovery is useful on LAN.

For GCP deployment, this is likely not needed and may need to be:

- disabled
- or made environment-dependent

## Proposed Execution Order

### Phase 1. Database Readiness Audit

Define and verify:

- required tables and indexes
- migration/bootstrap policy
- backup expectations
- local-to-remote data promotion path

Deliverable:

- DB deployment/readiness note

### Phase 2. Runtime Packaging for Deployment

Add:

- Dockerfile
- `.dockerignore`
- documented runtime command

Deliverable:

- containerized server runnable locally and in CI

### Phase 3. Artifact Storage Abstraction

Refactor storage access behind a service boundary.

Current state is path-based. Introduce a storage interface for:

- recording write/read
- image write/read
- report image write/read
- final PDF/DOCX write/read

Implementations:

- local filesystem backend
- cloud storage backend

Deliverable:

- no endpoint depends directly on local path assumptions

### Phase 4. Cloud Runtime Config

Add environment-driven deployment settings for:

- DB connection
- storage backend selection
- bucket names
- discovery disablement
- base URLs / admin endpoints

Deliverable:

- deployable config matrix for local vs cloud

### Phase 5. GCP Deployment Path

Choose and document one first deployment target:

- recommended: Cloud Run + Cloud SQL + Cloud Storage

Deliverable:

- one deployment runbook

## Recommended Immediate Next Task

Start with **Phase 1: Database Readiness Audit**.

Reason:

- PostgreSQL is now the runtime authority
- the database is the most critical persistent boundary in the deployed system
- deployment is weak until schema migration/backup/bootstrap policy is explicit

## Acceptance Criteria for This Planning Phase

This planning phase is successful when:

- runtime target is chosen
- DB target is chosen
- artifact storage target is chosen
- migration policy is chosen
- the next engineering step is unambiguous

## Current Recommendation Summary

If no stronger constraint appears, proceed toward:

- **Cloud Run** for app runtime
- **Cloud SQL (PostgreSQL)** for database
- **Cloud Storage** for artifacts
- **Alembic migrations** for deployed schema changes
- local filesystem backend retained only for local/dev mode
