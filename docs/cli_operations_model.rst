CLI Operations Model
====================

Purpose
-------

This note defines the intended operational model for ``admin_cli.py``.
The CLI is not a separate admin toy. It should exercise the same workflow
surfaces that the mobile client depends on, using the same service boundaries
and the same underlying state model.

Why this matters
----------------

The operational runtime is now DB-backed. Local storage exists for binary
artifacts and debug/export copies only. The CLI should inspect and control that
runtime model without treating exported JSON on disk as an authoritative
workflow source.

The CLI should let an operator inspect and control the same lifecycle in a way
that is modular, service-backed, and easy to debug.

Client contract boundary
------------------------

The CLI must not invent a parallel operational model. The client contract is
defined by the live FastAPI API. Any payload change exposed by the server must
be reflected in the client/UI specification.

Current client-facing workflow surfaces are:

- device registration / approval / token issuance
- assigned-job listing
- job create
- job status lookup
- round create
- manifest upload
- round submit / reprocess
- review fetch
- final submit / correction outputs

The CLI is a server operator tool for driving and inspecting that same model.

Operational layers
------------------

The intended server layering is:

- CLI layer
  - thin command parser and presentation
- service layer
  - device/auth service
  - job/assignment service
  - round/review service
  - final/correction/archive service
  - import/query service
- persistence layer
  - PostgreSQL for runtime metadata/state
  - local artifact storage for uploaded media and generated outputs

Business rules should live in services, not in the CLI.

Mode purity rule
----------------

The CLI execution boundary must be explicit and mode-pure.

``local`` mode
  Uses only local services, local database access, and local artifact access.

``remote`` mode
  Uses only HTTP against the live server.

Operational consequence:

- no command may silently fall back from remote mode to local DB/service/file
  access
- no command may silently fall back from local mode to remote HTTP as its
  execution boundary
- unsupported remote commands should fail explicitly until the server endpoint
  exists

Current CLI command set
-----------------------

Implemented command groups:

``device``
  - ``list``
  - ``pending``
  - ``validate``
  - ``approve``
  - ``revoke``
  - ``issue-token``

``job``
  - ``list-assignments``
  - ``assign``
  - ``unassign``
  - ``set-status``
  - ``inspect``

``round``
  - ``reopen``
  - ``inspect``

``review``
  - ``inspect``

``final``
  - ``inspect``

``net``
  - ``ipv4``
  - ``ipv6``

Current command-to-boundary map
-------------------------------
The correct mapping is now by mode, not by individual command fallback.

Local mode:

- device commands use local store/service boundaries
- customer and billing commands use ``CustomerService``
- job create/update use ``JobMutationService``
- inspect commands use ``InspectionService``
- final mutation commands use ``FinalMutationService``
- artifact fetch uses ``ArtifactFetchService``
- net commands are local utility commands

Remote mode:

- device commands use HTTP admin endpoints
- job assignment/status/unlock commands use HTTP admin endpoints
- round reopen uses HTTP admin endpoint
- job inspect uses HTTP ``GET /v1/admin/jobs/{job_id}/inspect``
- round inspect uses HTTP ``GET /v1/admin/jobs/{job_id}/rounds/{round_id}/inspect``
- review inspect uses HTTP ``GET /v1/admin/jobs/{job_id}/rounds/{round_id}/review/inspect``
- final inspect uses HTTP ``GET /v1/admin/jobs/{job_id}/final/inspect``
- artifact fetch uses HTTP ``GET /v1/admin/jobs/{job_id}/artifacts/{kind}``
- tree identify uses HTTP ``POST /v1/trees/identify``

Remote helper endpoint:

- job reference resolution uses HTTP ``GET /v1/admin/jobs/resolve`` so remote
  CLI commands do not depend on local database lookup

What is structurally sound already
----------------------------------

- Mode selection now defines the execution boundary instead of individual
  commands making ad hoc local/remote decisions.
- Assignment administration has a clear contract surface via admin endpoints.
- Remote job reference resolution now has an explicit admin endpoint rather
  than depending on local database lookup.
- Lifecycle inspection for jobs, rounds, reviews, and final/correction outputs
  now exists both as local ``InspectionService`` behavior and as remote admin
  read endpoints backed by that service.
- The tree identity contract is now live in the FastAPI job/create/status/review
  paths.
- Import/query tooling exists to validate the schema against real job data.

What is still missing from the CLI
----------------------------------

The CLI does not yet cover the full operational lifecycle that the client uses.

Missing command groups or subcommands:

``job create``
  Create a job through the same service/contract path used by the client.

``round list``
  List all rounds for a job with statuses and revision ids.

``round submit``
  Drive the same contract surface as the client submit path for controlled
  testing.

``round reprocess``
  Trigger reprocess through the same contract surface and inspect the result.

``archive inspect``
  Show prune candidates, retained rounds, transcript retention, and artifact
  retention decision for a job.

``geojson inspect``
  Show stored/exported GeoJSON payload summary for a job.

Recommended next service boundaries
-----------------------------------

To support the missing commands cleanly, the next service modules should be:

``device_service``
  registration, approval, revoke, issue token, status/list

``job_service``
  create, inspect, assign, unassign, status, tree resolution

``round_service``
  create, manifest write/read, submit, reprocess, inspect

``review_service``
  review fetch/inspect and transcript/form payload inspection

``final_service``
  final inspect, correction inspect, retained artifact summary

``archive_service``
  retention decision and prune candidate inspection

The CLI should call these services directly where possible, or call the same
HTTP contract that the client uses when the purpose is contract verification.

Recommended command discipline
------------------------------

Use direct service calls when the goal is:

- administrative control
- local inspection
- debugging persistence and state transitions

Use HTTP-backed CLI calls when the goal is:

- verifying the live client contract
- confirming payload shapes and endpoint behavior

This distinction should now be explicit per mode rather than hidden inside
individual command implementations.

Reference operational example
-----------------------------

Use a real imported job under ``local_data/jobs/<job_id>`` as the reference
example for:

- job record shape
- round manifest/review lifecycle
- final vs correction outputs
- audio/image artifact layout
- the artifact layout the database references, but does not replace

Definition of done for the CLI layer
------------------------------------

The CLI is in good shape when:

- every major client workflow surface has a corresponding server operator
  command or inspect command
- each command maps to a defined service boundary
- no unique business logic is trapped only in the CLI
- current payload changes are reflected in the client/UI spec
- the CLI can inspect a full job lifecycle from assigned job to final/correction
