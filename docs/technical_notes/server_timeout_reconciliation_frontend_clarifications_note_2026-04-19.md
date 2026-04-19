# Server Timeout / Reconciliation Frontend Clarifications

Date: 2026-04-19
Audience: frontend developer
Related notes:
- [server_timeout_reconciliation_frontend_note_2026-04-19.md](/home/roger/projects/traq_platform/server/docs/technical_notes/server_timeout_reconciliation_frontend_note_2026-04-19.md:1)
- `/home/roger/projects/traq_platform/mvp_client/code_review/server_timeout_reconciliation_frontend_feedback_note_2026-04-19.md`

## Purpose

This note answers the four concrete frontend clarification requests about the
Phase 1 round reconciliation contract.

The goal is to confirm how the frontend should interpret the current server
behavior without broadening the Phase 1 API surface.

## 1. Meaning Of `processing_state=accepted`

The frontend interpretation in the feedback note is correct.

For Phase 1, `processing_state=accepted` should be read as:

- the round exists server-side
- the server knows this round as current persisted state
- the round is not currently in a clearer `processing`, `completed`, or
  `failed` state

In current server terms, `accepted` is the coarse fallback state for a known
round when:

- round status is not `SUBMITTED_FOR_PROCESSING`
- round status is not `REVIEW_RETURNED`
- round status is not `FAILED`

What `accepted` does not mean:

- it does not mean upload rollback
- it does not mean the server rejected the round
- it does not mean the client should blindly retry submit

For Phase 1 queue logic, the frontend can treat `accepted` as:

- known by server
- non-terminal
- not yet clearly processing/completed/failed

That is the intended interpretation.

## 2. Expected Response When A Round Is Not Found

Current route:

- `GET /v1/jobs/{job_id}/rounds/{round_id}`

Current response behavior:

- `404` with detail `"Job not found"` when the job cannot be resolved
- `404` with detail `"Round not found"` when the job exists but the round does
  not

This is the intended Phase 1 behavior.

Frontend guidance:

- treat `404 Round not found` as authoritative evidence that the server does not
  currently know that round ID for that job
- do not reinterpret that as an ambiguous processing state

If the frontend needs a future distinction like “round previously existed but
was pruned” versus “round never existed,” that would be a future contract
extension. Phase 1 does not make that distinction.

## 3. Whether Accepted Artifact IDs Are Sufficient To Suppress Retry

Yes.

For Phase 1, if an artifact ID appears in:

- `accepted_recording_ids`
- `accepted_image_ids`

the frontend may treat that as sufficient evidence to suppress re-upload of
that same stable ID.

That is the intended server contract for current queue/reconciliation logic.

In other words:

- if `recording_id=rec_1` appears in `accepted_recording_ids`, do not re-upload
  `rec_1`
- if `image_id=img_1` appears in `accepted_image_ids`, do not re-upload
  `img_1`

Important boundary:

- this statement is about retry suppression for the same stable ID
- it is not a statement about whether the artifact was semantically perfect for
  every downstream purpose

If the server later needs to distinguish:

- accepted
- accepted but rejected for validation
- accepted but requires user action

that will require additional fields. Phase 1 does not expose those distinctions.

So for the current contract, accepted ID means:

- known by server
- safe to suppress same-ID re-upload

## 4. `client_revision_id` Mismatch Policy

Yes.

The frontend should treat `client_revision_id` mismatch as likely
staleness/conflict, not as an ordinary retry case.

If:

- local queue item has one `client_revision_id`
- server round read returns a different authoritative `client_revision_id`

the intended interpretation is:

- the local queued submit is probably stale relative to server state
- blind resubmit is not the correct default behavior

Recommended frontend handling for Phase 1:

- treat mismatch conservatively
- block automatic retry
- surface operator-visible caution or require an explicit recovery path

What mismatch does not mean:

- it does not automatically mean the server is wrong
- it does not automatically mean the local queue item should overwrite server
  state

For Phase 1, mismatch should be treated as a likely conflict/staleness signal.

## Practical Frontend Guidance

For the current queue phase, the intended decision rules are:

### Upload recovery

- if stable artifact ID is present in accepted ID set, suppress same-ID retry
- if stable artifact ID is absent, retry may still be appropriate

### Submit recovery

- if server `client_revision_id` matches local queue item, suppress duplicate
  submit retry unless other state clearly requires action
- if server `client_revision_id` differs from local queue item, treat as likely
  stale/conflicting work

### Round lookup failure

- `404 Round not found` means the server does not currently know that round
  under that job
- do not collapse that into ordinary processing ambiguity

## Bottom Line

The Phase 1 server contract for the frontend is:

- `processing_state=accepted` means known, non-terminal round state
- `404 Round not found` means the server does not currently know that round
- accepted artifact IDs are sufficient to suppress same-ID upload retry
- `client_revision_id` mismatch should be treated as likely
  conflict/staleness, not as an ordinary retry path

No additional API fields are required for these clarifications at this time.
