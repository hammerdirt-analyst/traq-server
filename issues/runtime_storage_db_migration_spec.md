# Runtime Storage DB Migration Spec

## Objective

Move `server/` to a DB-authoritative runtime model.

Rules:

- PostgreSQL is the source of truth for all operational runtime state.
- Local filesystem is used only for artifact bytes and generated deliverables.
- Exported JSON files may remain as debug/compatibility outputs, but they must not drive runtime behavior.

This is the storage boundary required before the server is treated as its own repo and before cloud migration work proceeds.

## Current State

Checkpoint:

- Phase 1 is complete.
- Runtime profile state is now DB-authoritative.
- Exported profile JSON is debug/compatibility output only.
- Phase 2 is complete for recording metadata.
- Runtime recording metadata is now DB-authoritative.
- Exported recording `.meta.json` files are debug/compatibility output only.
- Phase 3 is complete for image metadata.
- Runtime image metadata is now DB-authoritative.
- Exported image `.meta.json` files are debug/compatibility output only.

Already DB-authoritative:

- devices, approval, tokens, assignments
- runtime profiles
- recording metadata
- image metadata
- customers, billing profiles, trees
- jobs
- rounds
- round manifest
- round review payload
- finals/corrections metadata
- assigned-job payload generation

Still file-backed at runtime:

- processed recording tracking in `processed_artifacts.json`
- transcript cache in `*.transcript.txt`
- reprocess manifest synthesis that scans section storage and metadata files

Allowed to remain file-backed:

- audio files
- image files
- generated report images
- generated PDFs / DOCX
- optional exported debug JSON:
  - `job_record.json`
  - `rounds/*/manifest.json`
  - `rounds/*/review.json`

## Problem Statement

The server still depends on filesystem metadata during live runtime operation. That creates three problems:

1. It blocks a clean cloud/storage move.
2. It leaves room for DB/file drift.
3. It keeps live runtime behavior coupled to local directory layout.

The remaining work is not about job shell or round JSON anymore. It is about artifact metadata and profile state.

## Target Model

### DB owns

- device profile state
- recording metadata
- image metadata
- processed-artifact tracking
- transcript text or transcript reference state
- all runtime job/round state

### Filesystem owns

- audio bytes
- image bytes
- generated report-image bytes
- final PDF / DOCX bytes
- optional exported debug copies

## Proposed Runtime Storage Model

### 1. Profile State

Move profile payload off `_profile_path(...)` and into DB.

Required runtime behavior:

- `GET /v1/profile` reads DB
- `PUT /v1/profile` writes DB

Suggested shape:

- key by authenticated identity
  - device identity for device tokens
  - admin identity for admin key if needed

The current file-based profile JSON becomes optional export only, or is removed.

### 2. Recording Metadata

Move recording metadata off `recordings/*.meta.json` into DB.

Required fields:

- `job_id`
- `section_id`
- `recording_id`
- `content_type`
- `bytes`
- `stored_path`
- `uploaded_at`
- audio probe payload
- transcript text or transcript status
- processing status fields as needed

Runtime consequences:

- transcription reads metadata from DB
- submit/reprocess use DB metadata
- no runtime dependence on `.meta.json`

### 3. Image Metadata

Move image metadata off `images/*.meta.json` into DB.

Required fields:

- `job_id`
- `section_id`
- `image_id`
- `content_type`
- `bytes`
- `stored_path`
- `report_image_path`
- `report_bytes`
- `uploaded_at`
- `caption`
- GPS/location fields if present
- `updated_at`

Runtime consequences:

- image patch reads/writes DB
- report-image assembly reads DB metadata
- no runtime dependence on `.meta.json`

### 4. Processed Artifact Tracking

Move `processed_artifacts.json` into DB.

This state is operational runtime state, not a filesystem artifact.

Required use:

- determine whether a recording has already been processed
- support submit/reprocess logic without filesystem JSON

This can be represented either:

- as explicit processed flags on recording rows, or
- as a separate processed-state table keyed by job/section/recording

Preferred direction:

- store processing state on the recording row if that keeps the model simple

### 5. Transcript Cache

Move transcript text off `*.transcript.txt` as runtime authority.

Two valid choices:

1. transcript text stored directly in DB
2. transcript text stored as a file artifact, but referenced and versioned by DB

For the current system, the pragmatic choice is:

- store transcript text in DB on the recording row or in a related transcript table

Reason:

- it is small
- it is operational state
- it is needed during submit/review/reprocess

The text file may still be exported for debugging if needed.

## Runtime Endpoints Affected

These runtime paths must be DB-only after this work:

- `GET /v1/profile`
- `PUT /v1/profile`
- `PUT /v1/jobs/{job_id}/sections/{section_id}/recordings/{recording_id}`
- `PUT /v1/jobs/{job_id}/sections/{section_id}/images/{image_id}`
- `PATCH /v1/jobs/{job_id}/sections/{section_id}/images/{image_id}`
- `POST /v1/jobs/{job_id}/rounds/{round_id}/submit`
- `POST /v1/jobs/{job_id}/rounds/{round_id}/reprocess`
- `GET /v1/jobs/{job_id}/rounds/{round_id}/review`
- `POST /v1/jobs/{job_id}/final`

Some of these already use DB for primary state. The remaining work is to remove file-backed metadata dependencies from their helper paths.

## Non-Goals

Not part of this step:

- moving artifact bytes into PostgreSQL
- cleaning offline tools
- cleaning non-runtime inspection services
- deleting export/debug JSON immediately

Those can be handled later.

## Execution Plan

### Phase 1: Profile

1. add DB storage for profile payloads
2. patch `GET /v1/profile`
3. patch `PUT /v1/profile`
4. keep file export only if needed

Deliverable:

- no runtime profile reads/writes from disk

Status:

- complete

### Phase 2: Recording Metadata

1. add DB model/storage for recordings
2. update recording upload endpoint to write DB metadata
3. update transcription helpers to read DB metadata
4. update submit/reprocess to use DB recording metadata

Deliverable:

- no runtime dependence on `recordings/*.meta.json`

Status:

- complete

### Phase 3: Image Metadata

1. add DB model/storage for images
2. update image upload endpoint to write DB metadata
3. update image patch endpoint to write DB metadata
4. update report-image helper to read DB metadata

Deliverable:

- no runtime dependence on `images/*.meta.json`

Status:

- complete

### Phase 4: Processed State and Transcripts

1. add DB fields/tables for processed state
2. move transcript text into DB-backed state
3. patch processing helpers to stop using:
   - `processed_artifacts.json`
   - `*.transcript.txt`

Deliverable:

- no runtime dependence on processed-state JSON or transcript cache files

### Phase 5: Runtime Verification

After each phase:

- run server unit tests
- verify CLI/API smoke checks
- verify device flow:
  - fetch assigned job
  - edit
  - submit
  - review returned
  - final generation

## Acceptance Criteria

This migration is complete when all of the following are true:

- live runtime endpoints do not read `job_record.json`, `review.json`, or `manifest.json` for authority
- live runtime endpoints do not read `*.meta.json` for recording/image metadata
- live runtime endpoints do not read `processed_artifacts.json`
- live runtime endpoints do not read `*.transcript.txt` for authority
- `GET /v1/profile` and `PUT /v1/profile` are DB-backed
- filesystem is used only for artifact bytes and optional export/debug outputs

## Order of Work

The work should proceed in this order:

1. profile
2. recording metadata
3. image metadata
4. processed state + transcript state
5. runtime verification

Do not start repo extraction work until this runtime boundary is in place.
