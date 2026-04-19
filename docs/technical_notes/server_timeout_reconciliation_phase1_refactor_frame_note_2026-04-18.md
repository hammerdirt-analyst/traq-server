# Server Timeout / Reconciliation Phase 1 Refactor Frame

Date: 2026-04-18
Branch: `code-review-server-timeout-reconciliation`
Related notes:
- [server_timeout_and_reconciliation_analysis_note_2026-04-18.md](/home/roger/projects/traq_platform/server/docs/technical_notes/server_timeout_and_reconciliation_analysis_note_2026-04-18.md:1)
- [server_timeout_reconciliation_implementation_plan_note_2026-04-18.md](/home/roger/projects/traq_platform/server/docs/technical_notes/server_timeout_reconciliation_implementation_plan_note_2026-04-18.md:1)

## Purpose

This note reframes Phase 1 as a server-side refactor with explicit boundaries.

The intent is to prevent Phase 1 from turning into route-by-route patchwork.
Phase 1 should strengthen authoritative workflow state around the current
synchronous processing model. It should not become a partial async architecture
or a pile of UI-specific exceptions.

## Goals

Phase 1 should achieve these goals and no broader ones.

### 1. Make the round the reconciliation unit

The server should have one coherent answer to:

- what does it believe about round `R` right now?

That answer should not depend on reconstructing state from multiple incidental
payloads.

### 2. Make important workflow identity first-class state

`client_revision_id` should be persisted as round state, not merely carried
inside review or final payloads.

The server should be able to answer:

- which logical client revision is current for this round?

without reading derived artifacts.

### 3. Make accepted artifact state directly readable

The client should not need to infer accepted uploads from:

- review payloads
- manifest echoes
- local artifact files

The server should expose accepted round artifact state directly from persistent
round-backed metadata.

### 4. Preserve the current processing model

Phase 1 is not an async architecture rewrite.

It should improve reconciliation around the current system, not replace the
current system.

## Invariants

These are the constraints Phase 1 must preserve.

### 1. One authoritative round state

Round reconciliation state must come from authoritative persistent state, not
from whichever route happens to know the most.

### 2. Review payload is a projection, not the source of truth

The persisted review payload remains useful, but it must not be treated as the
authoritative home of reconciliation-critical data such as current client
revision identity.

### 3. Upload identity remains stable-ID based

The stable identities already in use remain the contract:

- `recording_id`
- `image_id`

Phase 1 must not introduce a second upload identity model.

### 4. Existing workflow routes remain valid

Phase 1 must preserve the existing working flow:

- create round
- upload recordings/images
- submit round
- review
- final

The refactor may add read capability, but it should not require a client
workflow rewrite to keep basic operations working.

### 5. Do not duplicate state unnecessarily

If a new field is introduced, it must have a clear authoritative home.

Phase 1 should not scatter the same concept across:

- round row
- review payload
- assigned-job payload
- final payload

without clearly declaring which one is authoritative.

## Phase 1 Boundary

Phase 1 includes only what is needed to make reconciliation explicit around the
current round model.

### Included

- a first-class round-level `client_revision_id`
- a round reconciliation/status read model
- direct exposure of accepted artifact IDs for one round
- coarse processing-state visibility for one round
- documentation of stable-ID upload retry semantics
- tests that lock the contract in place

### Explicitly excluded

- server-side job queue
- background worker orchestration
- generic operation resources
- cancellation semantics
- upload session redesign
- resumable chunked upload
- finalization orchestration redesign
- route-specific UI convenience fields that are not needed for reconciliation

If a proposed change does not strengthen authoritative round reconciliation, it
should not be in Phase 1.

## Concrete Changes Mapped To Goals

### Change A: Persist `client_revision_id` on `job_rounds`

Goal served:

- make important workflow identity first-class state

Why:

- current behavior lets `client_revision_id` survive indirectly inside review
  or final payload structures
- that is incidental persistence, not round state

Implementation shape:

- add nullable `client_revision_id` to `job_rounds`
- thread it through DB store reads/writes
- write it during submit before processing starts
- preserve it on reprocess unless explicitly changed by a future design

Files likely affected:

- [app/db_models.py](/home/roger/projects/traq_platform/server/app/db_models.py:1)
- [app/db_store.py](/home/roger/projects/traq_platform/server/app/db_store.py:1)
- [app/api/round_submit_routes.py](/home/roger/projects/traq_platform/server/app/api/round_submit_routes.py:1)
- Alembic migration under `alembic/versions/`

### Change B: Add a round reconciliation read route

Goal served:

- make the round the reconciliation unit
- make accepted artifact state directly readable

Recommended route:

- `GET /v1/jobs/{job_id}/rounds/{round_id}`

Why:

- current read surfaces are split between coarse job status and heavy review
  payload retrieval
- the server needs one direct answer for round reconciliation

Recommended fields:

- `job_id`
- `round_id`
- `status`
- `server_revision_id`
- `client_revision_id`
- `review_ready`
- `recordings`
- `images`
- `accepted_recording_ids`
- `accepted_image_ids`
- `processing_state`
- `transcription_failures` when known

Files likely affected:

- [app/api/job_read_routes.py](/home/roger/projects/traq_platform/server/app/api/job_read_routes.py:1)
- [app/api/models.py](/home/roger/projects/traq_platform/server/app/api/models.py:1)
- [app/db_store.py](/home/roger/projects/traq_platform/server/app/db_store.py:1)

### Change C: Build accepted artifact state from DB-backed round metadata

Goal served:

- make accepted artifact state directly readable
- keep one authoritative round state

Why:

- accepted artifact state should come from round recording/image rows
- it should not be inferred from review payload hydration or filesystem layout

Implementation shape:

- use `list_round_recordings(...)`
- use `list_round_images(...)`
- derive accepted ID sets from those DB-backed rows

Files likely affected:

- [app/db_store.py](/home/roger/projects/traq_platform/server/app/db_store.py:1)
- [app/api/job_read_routes.py](/home/roger/projects/traq_platform/server/app/api/job_read_routes.py:1)

### Change D: Add a coarse round `processing_state`

Goal served:

- make the round the reconciliation unit
- preserve the current processing model while making it more observable

Why:

- client timeout handling needs a stable read model
- Phase 1 does not need generic operations or background workers

Recommended derived values:

- `accepted`
- `processing`
- `completed`
- `failed`

These should be derived from existing round state, not from a new async system.

Suggested rule:

- `processing` when round status is `SUBMITTED_FOR_PROCESSING`
- `completed` when round status is `REVIEW_RETURNED`
- `failed` when round status is `FAILED`
- `accepted` when server has round state and accepted artifacts but processing
  has not clearly transitioned yet

Files likely affected:

- [app/api/job_read_routes.py](/home/roger/projects/traq_platform/server/app/api/job_read_routes.py:1)
- [app/db_store.py](/home/roger/projects/traq_platform/server/app/db_store.py:1)

### Change E: Document stable-ID retry semantics

Goal served:

- preserve the current processing model
- keep upload identity stable and explicit

Why:

- the current server behavior is already mostly duplicate-safe by stable ID
- the client should not implement against an assumed `409 already exists`
  contract if that is not the actual server behavior

Docs to update:

- [README.md](/home/roger/projects/traq_platform/server/README.md:1)
- [app/README.md](/home/roger/projects/traq_platform/server/app/README.md:1)
- [docs/architecture.rst](/home/roger/projects/traq_platform/server/docs/architecture.rst:1)

### Change F: Add tests that assert the new round contract

Goal served:

- keep the refactor from devolving into route-local behavior

Why:

- without tests, the new contract will drift back into incidental behavior

Test focus:

- round row persists `client_revision_id`
- round read returns that `client_revision_id`
- round read returns accepted `recording_id`s
- round read returns accepted `image_id`s
- duplicate upload with same stable ID stays logically single

Files likely affected:

- [tests/test_api_routers.py](/home/roger/projects/traq_platform/server/tests/test_api_routers.py:1)
- [tests/test_db_store.py](/home/roger/projects/traq_platform/server/tests/test_db_store.py:1)
- [tests/test_round_submit_service.py](/home/roger/projects/traq_platform/server/tests/test_round_submit_service.py:1)

## What Does Not Belong In Phase 1

These items should be rejected or deferred if they come up during implementation:

- any queue-specific server API
- any attempt to make submit asynchronous in this pass
- operation tables or operation polling resources
- storing reconciliation state only in review payloads
- deriving accepted artifact state from manifest or local files
- adding route-local special cases that bypass shared round state

## Review Standard

A proposed Phase 1 change is in-bounds if it answers yes to at least one of:

- does it strengthen authoritative round state?
- does it reduce client inference after timeout/interruption?
- does it move important identity out of incidental payloads?

It is out-of-bounds if:

- it adds a new workflow model instead of clarifying the current one
- it duplicates state without a clear authoritative home
- it primarily serves UI convenience rather than reconciliation

## One-Sentence Definition

Phase 1 refactors reconciliation around authoritative round state without
changing the current synchronous processing model.
