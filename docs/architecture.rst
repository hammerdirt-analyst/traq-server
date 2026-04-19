Server Architecture Notes
=========================

Managed Extraction Context by Recording Granularity
---------------------------------------------------

The server's extraction accuracy strategy is to keep context narrow by
processing recordings at section-level granularity.

How context is established:

- The user records under a selected section label in the client, and/or
- The user states section context in audio.

Each uploaded recording is tied to its section context and processed in that
scope, rather than feeding one large mixed transcript through extraction.

Tradeoff:

- Backend load and API traffic are higher (typically one upload call per
  recording, plus manifest/submit processing calls).
- In return, extraction precision is significantly higher and user time-on-task
  is lower due to reduced post-processing corrections.

Operational impact:

- More artifacts to track (`recording_id`, per-section transcript cache).
- Better deterministic merges into section-specific form structures.
- Cleaner review loops when users iterate with additional targeted recordings.


Round Reconciliation Boundary
-----------------------------

Phase 1 timeout/retry hardening keeps the current synchronous workflow model,
but makes round reconciliation more explicit.

The design rule is:

- the round is the reconciliation unit

That means:

- upload identity remains stable-ID based (`recording_id`, `image_id`)
- accepted artifact state is read from DB-backed round metadata
- `client_revision_id` is persisted as round state rather than surviving only
  inside derived review/final payloads
- clients may use the round read surface to reconcile ambiguous timeout or
  interruption outcomes

Current client-facing round recovery route:

- ``GET /v1/jobs/{job_id}/rounds/{round_id}``

This route is intended to answer:

- what round state is authoritative now
- which artifact IDs the server has accepted for that round
- which client/server revision identifiers are current
- whether the round is accepted, processing, completed, or failed

The important boundary is that this does not introduce a server-side queue or a
generic async operation resource. It clarifies reconciliation around the
existing round lifecycle.


Standalone Tree Identification
------------------------------

Tree identification is intentionally outside the job/round/review/final
workflow.

The boundary is:

- route layer in ``app/api/tree_identification_routes.py``
- service layer in ``app/services/tree_identification_service.py``

Responsibilities:

- the route accepts authenticated multipart image uploads and translates service
  exceptions to HTTP
- the service validates input, calls the upstream Pl@ntNet API, and normalizes
  the response to the server contract

This keeps tree identification as a standalone utility capability rather than a
hidden side effect of review or finalization flows.
