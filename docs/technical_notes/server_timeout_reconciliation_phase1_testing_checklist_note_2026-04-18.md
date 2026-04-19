# Server Timeout / Reconciliation Phase 1 Testing Checklist

Date: 2026-04-18
Branch: `code-review-server-timeout-reconciliation`
Primary refactor frame:
- [server_timeout_reconciliation_phase1_refactor_frame_note_2026-04-18.md](/home/roger/projects/traq_platform/server/docs/technical_notes/server_timeout_reconciliation_phase1_refactor_frame_note_2026-04-18.md:1)

## Purpose

This checklist defines the testing standard for Phase 1 before deployment.

It is intentionally aligned to the Phase 1 refactor frame so implementation and
validation stay coupled to the actual goals:

- round is the reconciliation unit
- important workflow identity is first-class state
- accepted artifact state is directly readable
- the current synchronous processing model is preserved

This is not a generic test wishlist. It is the minimum defensible validation
set for the Phase 1 server refactor.

## Test Philosophy

Phase 1 changes must be tested at three levels:

1. persistence behavior
2. API contract behavior
3. PostgreSQL-backed integration behavior

SQLite-only fast tests are necessary but not sufficient for this refactor.
Because the work explicitly strengthens DB-backed metadata, at least one
PostgreSQL-backed integration scenario must cover the new contract before
deployment.

## Mapping To Phase 1 Goals

### Goal 1: Make the round the reconciliation unit

Tests must prove:

- one round has one authoritative reconciliation state
- reconciliation reads do not depend on review payload accidents
- accepted artifacts and revision identity can be read directly for one round

### Goal 2: Make important workflow identity first-class state

Tests must prove:

- `client_revision_id` is stored on the round row
- round reads expose that value
- submit logic does not lose or silently replace it

### Goal 3: Make accepted artifact state directly readable

Tests must prove:

- accepted `recording_id`s come from DB-backed round recording metadata
- accepted `image_id`s come from DB-backed round image metadata
- duplicate upload with same stable ID stays logically single

### Goal 4: Preserve the current processing model

Tests must prove:

- existing submit/review behavior still works
- no regression in current routes required by the working client flow
- the added reconciliation read does not require a workflow redesign to keep
  the current path functioning

## Required Test Buckets

## 1. Persistence Tests

Primary file:

- [tests/test_db_store.py](/home/roger/projects/traq_platform/server/tests/test_db_store.py:1)

These tests validate the authoritative persistence layer directly.

### Must-have persistence scenarios

1. Round stores `client_revision_id`
- create a job and round
- call `upsert_job_round(... client_revision_id="client-rev-1")`
- assert `get_job_round(...)` returns `client_revision_id="client-rev-1"`
- assert `list_job_rounds(...)` also returns that value

2. Round updates preserve expected revision identity
- write a round with `client_revision_id`
- update status and/or review payload
- assert the stored round still carries the same `client_revision_id` unless
  explicitly replaced

3. Duplicate recording upload is logically single
- create a round
- call `upsert_round_recording(...)` twice with same `section_id` and
  `recording_id`
- assert one logical recording row exists for that round/artifact identity
- assert latest metadata is visible as expected

4. Duplicate image upload is logically single
- create a round
- call `upsert_round_image(...)` twice with same `section_id` and `image_id`
- assert one logical image row exists for that round/artifact identity
- assert latest metadata is visible as expected

5. Accepted recording IDs can be derived from DB-backed round state
- persist multiple round recordings
- assert helper/read model returns expected accepted recording ID set

6. Accepted image IDs can be derived from DB-backed round state
- persist multiple round images
- assert helper/read model returns expected accepted image ID set

### Persistence pass criteria

- all round reads consistently return stored `client_revision_id`
- duplicate stable-ID writes do not create duplicate logical state
- accepted artifact-state derivation does not depend on review payload data

## 2. API Contract Tests

Primary file:

- [tests/test_api_routers.py](/home/roger/projects/traq_platform/server/tests/test_api_routers.py:1)

These tests validate the client-facing contract.

### Must-have API scenarios

1. Round reconciliation route returns authoritative round state
- create job and round through the existing test harness
- call `GET /v1/jobs/{job_id}/rounds/{round_id}`
- assert:
  - `round_id`
  - `status`
  - `server_revision_id`
  - `client_revision_id`
  - `review_ready`
  - `processing_state`

2. Round reconciliation route exposes accepted recording IDs
- upload at least one recording through the route layer
- call round reconciliation route
- assert returned recording list and `accepted_recording_ids`

3. Round reconciliation route exposes accepted image IDs
- upload at least one image through the route layer
- call round reconciliation route
- assert returned image list and `accepted_image_ids`

4. Submit persists and exposes `client_revision_id`
- submit a round with `client_revision_id`
- call round reconciliation route
- assert returned `client_revision_id`
- assert returned `status` is coherent with current processing result

5. Duplicate upload by stable recording ID remains logically single
- upload same recording ID twice through HTTP route
- call round reconciliation route
- assert no duplicate logical recording identity appears

6. Duplicate upload by stable image ID remains logically single
- upload same image ID twice through HTTP route
- call round reconciliation route
- assert no duplicate logical image identity appears

7. Existing review route still works
- process a round through current submit path
- call `GET /v1/jobs/{job_id}/rounds/{round_id}/review`
- assert current review payload contract still behaves

8. Existing job status route still works
- call `GET /v1/jobs/{job_id}`
- assert prior status fields still behave unless intentionally extended

### API pass criteria

- the new round route is sufficient for reconciliation use
- current core routes do not regress
- API contract reflects DB-backed round state rather than route-local inference

## 3. Submit-Orchestration Tests

Primary file:

- [tests/test_round_submit_service.py](/home/roger/projects/traq_platform/server/tests/test_round_submit_service.py:1)

These tests are narrower and protect against orchestration regressions.

### Must-have orchestration scenarios

1. Submit review override carries `client_revision_id`
- build base review override from submit payload
- assert `client_revision_id` survives the override path

2. Post-process review mutation does not erase reconciliation-critical identity
- apply client patch post-processing
- assert review payload mutation does not become the only place where revision
  identity survives

3. Manifest supplementation does not alter revision identity behavior
- exercise manifest recovery/supplement logic
- assert no hidden coupling between manifest behavior and revision persistence

### Orchestration pass criteria

- round revision identity is not fragile to submit-service merge order
- review payload mutation remains projection logic, not the source of truth

## 4. PostgreSQL Integration Tests

Primary file to extend:

- [tests/test_postgres_ci_smoke.py](/home/roger/projects/traq_platform/server/tests/test_postgres_ci_smoke.py:1)

This is the critical validation for the DB-backed metadata boundary.

### Must-have PostgreSQL smoke scenario

Add one end-to-end Postgres-backed scenario that does the following:

1. create a job
2. create a round
3. upload one recording
4. upload one image
5. submit with `client_revision_id`
6. fetch round reconciliation state
7. assert:
   - `client_revision_id` is persisted
   - accepted recording IDs are correct
   - accepted image IDs are correct
   - round status / processing state is coherent

### Optional second PostgreSQL scenario

If inexpensive, add:

8. retry same recording or image upload by stable ID
9. assert no duplicate logical state appears in reconciliation read

### PostgreSQL pass criteria

- migration applies cleanly
- round-level revision identity persists under PostgreSQL
- accepted artifact state is correct under PostgreSQL
- no SQLite-only assumptions are masking broken DB behavior

## 5. Documentation Verification

Docs to update:

- [README.md](/home/roger/projects/traq_platform/server/README.md:1)
- [app/README.md](/home/roger/projects/traq_platform/server/app/README.md:1)
- [docs/architecture.rst](/home/roger/projects/traq_platform/server/docs/architecture.rst:1)

Documentation review checklist:

- upload identity is described in terms of stable IDs
- retrying same upload with same stable ID is documented as allowed
- docs do not claim duplicate upload contract is `409 already exists` unless
  implementation intentionally changes to that
- reconciliation route is documented as authoritative for round recovery
- timeout is described as ambiguous outcome, not definitive rollback

## Pre-Deploy Gate

Before deployment, Phase 1 should satisfy all of the following:

1. migration runs successfully
2. targeted persistence tests pass
3. targeted API contract tests pass
4. targeted submit-orchestration tests pass
5. PostgreSQL-backed smoke test covering new round metadata passes
6. existing canonical pre-deploy regression gate still passes

## Suggested Execution Order

Run tests in this order while implementing:

1. DB store tests
- fastest proof that the authoritative metadata model is correct

2. API router tests
- validates the client-facing reconciliation contract

3. submit-service tests
- protects merge/orchestration behavior

4. PostgreSQL smoke test
- validates the real persistence boundary before deploy

5. full pre-deploy gate
- validates no broader regression

## Review Standard

Phase 1 is not ready to deploy if any of these remain unproven:

- round-level `client_revision_id` persistence
- direct accepted artifact-state reads for one round
- duplicate stable-ID upload remaining logically single
- PostgreSQL-backed correctness of the new metadata path

If those are not tested, then the refactor is still relying on assumptions
rather than on locked-in behavior.
