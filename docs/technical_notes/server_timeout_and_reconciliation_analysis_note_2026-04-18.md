# Server Timeout And Reconciliation Analysis

Date: 2026-04-17
Branch: `code-review-server-timeout-reconciliation`
Related client note:
`/home/roger/projects/traq_platform/mvp_client/code_review/server_timeout_and_reconciliation_design_note.md`

## Summary

The client design note is directionally correct. A client-side timeout creates
an ambiguous outcome for larger uploads and long-running workflow operations.
This server already has some of the primitives needed for reconciliation, but
it does not yet expose a complete client-facing reconciliation contract.

The most important conclusion is:

- the current UI timeout changes do not automatically break the server contract
- they do increase pressure on weak parts of the current contract
- uploads are relatively close to safe retry behavior already
- submit, reprocess, and finalization still rely too much on inference instead
  of explicit reconciliation state

## What The Server Already Supports

### Stable artifact identity

The server already uses stable IDs in the upload route shape:

- recordings:
  `PUT /v1/jobs/{job_id}/sections/{section_id}/recordings/{recording_id}`
- images:
  `PUT /v1/jobs/{job_id}/sections/{section_id}/images/{image_id}`

Relevant files:

- [app/api/recording_routes.py](/home/roger/projects/traq_platform/server/app/api/recording_routes.py:1)
- [app/api/image_routes.py](/home/roger/projects/traq_platform/server/app/api/image_routes.py:1)

These IDs are also persisted with round-scoped uniqueness:

- `UniqueConstraint("round_pk", "recording_id", ...)`
- `UniqueConstraint("round_pk", "image_id", ...)`

Relevant file:

- [app/db_models.py](/home/roger/projects/traq_platform/server/app/db_models.py:1)

In practice, duplicate uploads with the same stable ID are mostly safe because
the DB layer uses upsert behavior and the artifact key is deterministic.

### Revision and round identity

The server already has:

- `round_id`
- `server_revision_id`
- `client_revision_id` in submit/final payload models

Relevant files:

- [app/api/models.py](/home/roger/projects/traq_platform/server/app/api/models.py:1)
- [app/api/round_submit_routes.py](/home/roger/projects/traq_platform/server/app/api/round_submit_routes.py:1)
- [app/api/final_routes.py](/home/roger/projects/traq_platform/server/app/api/final_routes.py:1)

The submit flow accepts `client_revision_id`, and finalization persists both
client and server revision identifiers in the archived final payload.

### Some server-visible status surfaces

The server already exposes coarse state through:

- `GET /v1/jobs/{job_id}`
- `GET /v1/jobs/{job_id}/rounds/{round_id}/review`
- `GET /v1/jobs/assigned`

Relevant files:

- [app/api/job_read_routes.py](/home/roger/projects/traq_platform/server/app/api/job_read_routes.py:1)
- [app/services/assigned_job_service.py](/home/roger/projects/traq_platform/server/app/services/assigned_job_service.py:1)

These routes can tell the client:

- top-level job status
- latest round status
- review availability
- current `server_revision_id`
- current normalized review payload when it exists

## What The Server Does Not Yet Provide Cleanly

### No strong reconciliation endpoint for accepted artifact IDs

The client note asks for a way to answer:

- which recording IDs has the server accepted?
- which image IDs has the server accepted?
- which artifacts failed?
- which are still missing?

The current server does not expose a dedicated device-facing endpoint that
returns a complete accepted-artifact set for a round.

Current limitations:

- review payload exposes hydrated images, but not a symmetrical recording list
- job status is too coarse for artifact reconciliation
- manifest is a workflow input, not a durable accepted-upload receipt

This is the largest current gap for timeout recovery.

### Duplicate upload contract is not explicit `409 already exists`

The client note asks whether `409 already exists` is the intended duplicate
upload contract.

Current answer:

- no, not for standard recording/image upload retries
- the current behavior is closer to idempotent overwrite/upsert by stable ID
- retried uploads generally return success rather than a dedicated duplicate
  response

That is workable, but it should be documented clearly so the client does not
build against the wrong expectation.

### Submit reconciliation is still indirect

Round submit accepts `client_revision_id`, but the server does not yet expose a
first-class answer to:

- did you accept this exact logical submit?
- which `client_revision_id` is the authoritative accepted one for this round?

The client can infer by checking:

- `GET /v1/jobs/{job_id}`
- `GET /v1/jobs/{job_id}/rounds/{round_id}/review`

But there is no explicit accepted-submit record or submit-status resource.

### Reprocess and finalization are still too opaque after timeout

Reprocess and finalization are synchronous request/response operations.

If the client times out locally while the server continues to work, the client
does not have a first-class operation-status endpoint that distinguishes:

- not received
- accepted
- processing
- completed
- failed

Today the client would have to infer from later job state, review availability,
or final artifact presence.

## Direct Answers To The Client Note

### 1. Are artifact uploads already idempotent by stable artifact ID?

Mostly yes.

The route structure, DB uniqueness, deterministic artifact keys, and upsert
behavior all push uploads toward duplicate-safe behavior.

### 2. Is `409 already exists` the intended duplicate-upload contract?

No.

Current upload behavior is not built around explicit duplicate `409` responses.
It behaves more like stable-ID upsert/overwrite.

### 3. Which endpoint is the preferred authoritative source for accepted artifact IDs after timeout?

There is no strong dedicated client-facing answer today.

That is a real API gap if the client wants robust timeout reconciliation.

### 4. Can job or round status expose enough information to reconcile client-sent artifacts against server-received artifacts?

Not fully.

Current status routes expose coarse workflow state and revision info, but not a
complete accepted-artifact set.

### 5. Can the server expose accepted `client_revision_id` consistently for round submit?

Not consistently enough today.

The value can survive in persisted review-related payloads, but it is not yet a
first-class round status field.

### 6. For final submit and reprocess, what is the preferred status source after timeout?

There is no ideal dedicated source today.

Current fallback sources are:

- `GET /v1/jobs/{job_id}`
- `GET /v1/jobs/{job_id}/rounds/{round_id}/review`
- final artifact presence / inspection paths

### 7. Are any retries unsafe even with stable IDs?

Yes.

Upload retries are relatively safe.

Blind retries of submit, reprocess, and especially finalization are less safe
because the server does not yet provide enough explicit accepted/processing
state to make retries mechanically reliable.

## Does The UI Change Break The Current Contract?

Not automatically.

The timeout hardening described by the client does not inherently break the
current server contract. What it does is expose where the current contract is
too weak or too implicit.

More concretely:

- if the client adds timeouts for uploads, current behavior is probably still
  workable because stable upload IDs already make retries relatively safe
- if the client adds timeouts for submit/reprocess/finalization, the current
  contract becomes much more fragile because the client must infer state after
  ambiguous outcomes

So the right framing is:

- the UI changes do not break a strong contract
- they reveal that the current contract is incomplete for timeout-safe
  reconciliation

## Recommended Server Improvements

The highest-value server changes would be:

1. Add a round reconciliation/status endpoint that returns:
   - `round_id`
   - `status`
   - `server_revision_id`
   - accepted `client_revision_id`
   - accepted `recording_ids`
   - accepted `image_ids`
   - known failed artifact IDs where available

2. Treat `client_revision_id` as a first-class persisted round field instead of
   relying on it to survive only in review/final payload structures.

3. Expose explicit operation states for long-running mutations:
   - `accepted`
   - `processing`
   - `completed`
   - `failed`

4. Document upload retry semantics clearly:
   - duplicate upload by stable ID is allowed
   - the client should treat repeated success as idempotent
   - the contract is not `409 already exists`

