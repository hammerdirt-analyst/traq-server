# Server Timeout And Reconciliation Implementation Plan

Date: 2026-04-18
Branch: `code-review-server-timeout-reconciliation`
Related analysis:
- [docs/technical_notes/server_timeout_and_reconciliation_analysis_note_2026-04-18.md](/home/roger/projects/traq_platform/server/docs/technical_notes/server_timeout_and_reconciliation_analysis_note_2026-04-18.md:1)
Related client note:
- `/home/roger/projects/traq_platform/mvp_client/code_review/server_timeout_and_reconciliation_design_note.md`

## Goal

Add an explicit server-side reconciliation contract so a mobile client can
apply request timeouts without guessing whether long-running or large-payload
operations were accepted, completed, or should be retried.

The design center is:

- preserve current upload and workflow behavior
- add authoritative reconciliation reads
- make stable-ID retries clearly safe
- avoid introducing a queue-first architecture unless needed later

## Recommended Scope

Phase the work in this order:

1. document existing upload retry semantics
2. add client-facing round reconciliation reads
3. persist first-class client revision identity at round level
4. expose explicit operation state for submit/reprocess/final flows
5. tighten tests and docs around timeout ambiguity

This order gives the client immediate value without forcing a large async
refactor up front.

## Non-Goals For This Pass

Do not do these in the first implementation pass:

- full background job queue
- server-side cancellation of in-flight requests
- resumable chunked media upload
- changing upload routes away from stable path IDs
- replacing current synchronous processing with a scheduler-first model

## Current Server Constraints

The current server already has usable primitives:

- stable `recording_id`
- stable `image_id`
- stable `round_id`
- `server_revision_id`
- `client_revision_id` in submit/final payloads
- DB-backed round recording and image metadata

The main gap is the read model, not the raw write path.

## Phase 1: Document Current Retry Contract

### Objective

Make existing upload retry semantics explicit so the client knows how to behave
before any API changes land.

### Required doc changes

Update these docs:

- [README.md](/home/roger/projects/traq_platform/server/README.md:1)
- [app/README.md](/home/roger/projects/traq_platform/server/app/README.md:1)
- [docs/architecture.rst](/home/roger/projects/traq_platform/server/docs/architecture.rst:1)
- [docs/cli_operations_model.rst](/home/roger/projects/traq_platform/server/docs/cli_operations_model.rst:1) if admin troubleshooting guidance is useful

### Contract text to add

Document these rules:

- upload identity is the stable path ID:
  - `recording_id`
  - `image_id`
- retrying the same upload with the same stable ID is allowed
- the upload contract is idempotent-by-stable-ID, not duplicate-reject-by-409
- client timeout does not imply server rollback
- client should reconcile before retrying submit/reprocess/final flows

### Expected value

This gives the client team a safe rule immediately:

- media retries with the same ID are acceptable

## Phase 2: Add A Round Reconciliation Read Endpoint

### Objective

Give the client one authoritative place to answer:

- what round state does the server currently believe?
- which artifact IDs has the server accepted?
- which client revision does the server know about?

### Recommended endpoint

Add a new device-facing route:

- `GET /v1/jobs/{job_id}/rounds/{round_id}`

This should be distinct from `GET /review` because review payload is too heavy
and only exists after processing returns.

### Recommended response shape

Suggested model:

```json
{
  "job_id": "job_123",
  "round_id": "round_1",
  "status": "SUBMITTED_FOR_PROCESSING",
  "server_revision_id": "rev_round_1",
  "client_revision_id": "client-rev-1",
  "review_ready": false,
  "recordings": [
    {
      "section_id": "site_factors",
      "recording_id": "rec_1",
      "upload_status": "uploaded"
    }
  ],
  "images": [
    {
      "section_id": "job_photos",
      "image_id": "img_1",
      "upload_status": "uploaded"
    }
  ],
  "accepted_recording_ids": ["rec_1"],
  "accepted_image_ids": ["img_1"],
  "transcription_failures": [],
  "processing_state": "processing"
}
```

### Why this route matters

This route becomes the primary reconciliation endpoint after:

- upload timeout
- submit timeout
- reprocess timeout

The client should not need to fetch the full review payload just to learn
accepted artifact IDs.

### Implementation notes

Likely files to extend:

- [app/api/job_read_routes.py](/home/roger/projects/traq_platform/server/app/api/job_read_routes.py:1)
- [app/api/models.py](/home/roger/projects/traq_platform/server/app/api/models.py:1)
- [app/db_store.py](/home/roger/projects/traq_platform/server/app/db_store.py:1)

Add a new response model rather than overloading `StatusResponse`.

## Phase 3: Persist First-Class Round Client Revision Identity

### Objective

Stop treating `client_revision_id` as something that only survives inside
review/final payloads.

### Recommended schema change

Add a nullable column to `job_rounds`:

- `client_revision_id`

Likely files:

- [app/db_models.py](/home/roger/projects/traq_platform/server/app/db_models.py:1)
- `alembic/versions/...`
- [app/db_store.py](/home/roger/projects/traq_platform/server/app/db_store.py:1)

### Why this matters

The client needs a direct answer to:

- which logical submit did the server most recently accept for this round?

That is round state, not merely review payload content.

### Write-path changes

On round submit:

- persist incoming `client_revision_id` onto the round row before processing

On reprocess:

- preserve existing `client_revision_id`
- optionally add a separate `reprocess_requested_at` later if needed, but do not
  conflate reprocess with a new client revision

On finalization:

- continue archiving `client_revision_id` in final payload
- use round-level `client_revision_id` as the authoritative current revision if
  the route payload and stored state need consistency checks later

## Phase 4: Expose Explicit Processing State

### Objective

Let the client distinguish:

- request not received
- accepted
- processing
- completed
- failed

without inferring from transport behavior.

### Recommended approach

Do not build a full generic operation table in the first pass.

Instead, derive a stable `processing_state` read model from current round/job
state:

- `not_received`
  when round does not exist or server has no matching client revision / upload
- `accepted`
  when request metadata has been recorded but processing has not started yet
- `processing`
  when round status is `SUBMITTED_FOR_PROCESSING`
- `completed`
  when round status is `REVIEW_RETURNED` or final artifacts exist
- `failed`
  when round status is `FAILED` or finalization failed terminally

### Where to expose it

Expose `processing_state` on:

- new round reconciliation route
- possibly `GET /v1/jobs/{job_id}` for coarse job-level polling

### Later upgrade path

If synchronous processing becomes too opaque, the next step would be a real
operation resource such as:

- `POST /submit` returns `202 Accepted`
- `GET /operations/{operation_id}`

That is a later step, not required for the first reconciliation pass.

## Phase 5: Tighten Upload Metadata For Reconciliation

### Objective

Make upload acceptance visible enough that the client can retry only what is
missing.

### Recommended changes

Use existing DB-backed metadata rows and standardize what they store.

For recordings and images, ensure metadata consistently contains:

- stable ID
- section ID
- upload timestamp
- upload status
- content type when applicable
- stored artifact path

This is mostly already present, but the read model should depend on DB rows, not
filesystem meta files.

### Optional improvement

Add an upload response field like:

```json
{
  "ok": true,
  "accepted": true,
  "already_present": false,
  "recording_id": "rec_1"
}
```

This is optional because the larger need is the reconciliation read endpoint.

## Phase 6: Finalization Timeout Recovery

### Objective

Reduce ambiguity when final submit times out client-side after the server may
already have archived output.

### Recommended first pass

Extend job status or add a final-status read surface that answers:

- does final snapshot exist?
- does correction snapshot exist?
- which `client_revision_id` was archived?
- are final artifacts materialized?

Possible route:

- `GET /v1/jobs/{job_id}/final/status`

Suggested response fields:

- `state`: `not_started | processing | completed | failed`
- `kind`: `final | correction | null`
- `client_revision_id`
- `server_revision_id`
- `report_ready`
- `traq_pdf_ready`
- `geojson_ready`

### Why this can wait until after round reconciliation

Submit and upload ambiguity is more common operationally. Finalization matters,
but the first client timeout rollout can still benefit substantially from round
reconciliation before a dedicated final-status route lands.

## Data Model Changes

Recommended minimal schema changes:

1. `job_rounds.client_revision_id`

Optional later additions if needed:

2. `job_rounds.processing_started_at`
3. `job_rounds.processing_completed_at`
4. `job_rounds.processing_failed_at`
5. `job_rounds.last_error`

Minimal-first is preferable.

## API Model Changes

Add new response models in [app/api/models.py](/home/roger/projects/traq_platform/server/app/api/models.py:1):

- `RoundArtifactStatus`
- `RoundReconciliationResponse`
- optional `FinalStatusResponse`

Do not overload the existing review payload or assigned-job payload with too
many reconciliation-only fields.

## Service And Store Changes

### DB store

Add or extend helpers in [app/db_store.py](/home/roger/projects/traq_platform/server/app/db_store.py:1):

- include `client_revision_id` in round reads/writes
- helper to build accepted recording/image ID sets for a round
- helper to summarize round reconciliation state

### Submit service

Update [app/services/round_submit_service.py](/home/roger/projects/traq_platform/server/app/services/round_submit_service.py:1):

- use stored round `client_revision_id` deliberately
- stop relying on review payload as the only place to retain it

### Read routes

Update [app/api/job_read_routes.py](/home/roger/projects/traq_platform/server/app/api/job_read_routes.py:1):

- add round reconciliation route
- optionally enrich job status with one coarse `processing_state`

## Testing Plan

Add tests in these areas:

- [tests/test_api_routers.py](/home/roger/projects/traq_platform/server/tests/test_api_routers.py:1)
- [tests/test_db_store.py](/home/roger/projects/traq_platform/server/tests/test_db_store.py:1)
- [tests/test_round_submit_service.py](/home/roger/projects/traq_platform/server/tests/test_round_submit_service.py:1)

### Required scenarios

1. recording upload retried with same `recording_id`
   - second upload remains safe
   - no duplicate logical row

2. image upload retried with same `image_id`
   - second upload remains safe
   - accepted image set remains stable

3. round reconciliation route after partial upload set
   - accepted recording/image IDs returned correctly

4. submit with `client_revision_id`
   - round row persists `client_revision_id`
   - reconciliation route exposes it

5. submit timeout simulation
   - client can poll reconciliation route and learn accepted state

6. reprocess timeout simulation
   - reconciliation route shows processing or completed state without requiring
     blind retry

7. finalization status route, if implemented in this pass
   - completed finalization visible after ambiguous client timeout

## Documentation Plan

After the API changes land, update:

- [README.md](/home/roger/projects/traq_platform/server/README.md:1)
- [app/README.md](/home/roger/projects/traq_platform/server/app/README.md:1)
- [docs/architecture.rst](/home/roger/projects/traq_platform/server/docs/architecture.rst:1)
- [docs/api/index.rst](/home/roger/projects/traq_platform/server/docs/api/index.rst:1)
- add a new API note if needed under `docs/`

The docs should answer plainly:

- what timeout means
- what the client should poll after timeout
- which retries are safe
- which retries should only happen after reconciliation

## Rollout Recommendation

Implement in two mergeable slices.

### Slice 1

- doc the upload retry contract
- add `client_revision_id` to `job_rounds`
- add round reconciliation read route
- add tests for accepted artifact IDs and stored client revision

This is the highest-value slice and gives the client a clear timeout recovery
path for uploads and submit.

### Slice 2

- add explicit final-status route if needed
- optionally add richer processing timestamps/error fields
- refine job status payload if the client still needs less-polling UI behavior

## Product / Contract Answer

The client timeout hardening does not inherently break the server contract.

What it does is force the server contract to become more explicit.

Current behavior is usable for stable-ID upload retries, but the contract is too
implicit for submit/reprocess/final timeout recovery. This plan closes that gap
without requiring a full architecture rewrite.

