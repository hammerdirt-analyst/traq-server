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

``device list`` / ``device pending``
  Service boundary:
    ``DatabaseStore.list_devices()``

  Persistence touched:
    ``devices``

``device validate`` / ``device approve``
  Service boundary:
    ``DatabaseStore.approve_device()``

  Persistence touched:
    ``devices``

``device revoke``
  Service boundary:
    ``DatabaseStore.revoke_device()``

  Persistence touched:
    ``devices``, ``device_tokens``

``device issue-token``
  Service boundary:
    ``DatabaseStore.issue_token()``

  Persistence touched:
    ``device_tokens`` and ``devices.last_seen_at``

``job list-assignments``
  Contract boundary:
    HTTP ``GET /v1/admin/jobs/assignments``

  Current runtime backing:
    DB-backed assignment listing

``job assign`` / ``job unassign``
  Contract boundary:
    HTTP admin endpoints

  Current runtime backing:
    DB-backed assignment service

  Job reference resolution:
    official ``job_id`` passes through directly; official ``job_number`` is
    resolved through the database-backed operational store.

``job set-status``
  Contract boundary:
    HTTP admin status endpoint

  Current runtime backing:
    job record + round status mutation in server runtime

``job inspect``
  Service boundary:
    ``InspectionService.inspect_job()``

  Persistence touched:
    DB-backed job/assignment metadata plus filesystem job root inspection

``round reopen``
  Contract boundary:
    HTTP admin reopen endpoint

  Current runtime backing:
    round/job status mutation in server runtime

``round inspect``
  Service boundary:
    ``InspectionService.inspect_round()``

  Persistence touched:
    DB-backed round state plus local artifact/debug file inspection

``review inspect``
  Service boundary:
    ``InspectionService.inspect_review()``

  Persistence touched:
    DB-backed review payload plus exported debug file inspection

``final inspect``
  Service boundary:
    ``InspectionService.inspect_final()``

  Persistence touched:
    filesystem final/correction outputs plus DB-backed job resolution

``net ipv4`` / ``net ipv6``
  Local utility only; not part of the client/server state contract.

What is structurally sound already
----------------------------------

- Device approval and token issuance are now DB-backed in the CLI.
- Assignment administration has a clear contract surface via admin endpoints.
- Job reference resolution now uses the operational store rather than reading
  exported ``local_data/jobs/*/job_record.json`` files directly.
- Lifecycle inspection for jobs, rounds, reviews, and final/correction outputs
  now lives behind ``InspectionService`` instead of ad hoc CLI file reads.
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

This distinction should be explicit per command.

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
