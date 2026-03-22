# Remote CLI Plan

Purpose
-------

This document records the refactor plan for making the admin CLI mode-pure for
remote operator use during field testing.

Requirement
-----------

The CLI must no longer mix local service/store access with remote HTTP calls
inside the same execution mode.

Mode rules:

- ``local`` mode uses only local services, local database access, and local
  artifact access.
- ``remote`` mode uses only HTTP against the live server.
- No command may silently fall back across that boundary.

Immediate priority
------------------

The first priority is remote operator access for field testing of the UI.

That means the work should proceed in two ordered phases:

1. make remote mode honest
2. add remote inspection parity

The design should follow the existing repo precedent:

- thin CLI/parser layer
- service-backed business logic
- API/router layer for remote contract surfaces
- no mixed operational model hidden in the CLI


Phase 1: Make Remote Honest
===========================

Goal
----

Remote mode must be HTTP-only, even if that means some commands are temporarily
unsupported.

Acceptance criteria
-------------------

- In remote mode, no CLI command touches local ``DatabaseStore``,
  ``InspectionService``, ``CustomerService``, ``JobMutationService``,
  ``FinalMutationService``, or ``ArtifactFetchService``.
- Supported remote commands use only live HTTP endpoints.
- Unsupported remote commands fail explicitly with a clear message.
- No command-level fallback remains.

Implementation checklist
------------------------

1. Add a remote CLI backend abstraction.

   Suggested shape:

   - ``app/cli/remote_backend.py``
   - one backend bundle/object exposing domain methods for:
     - devices
     - jobs
     - rounds
     - tree identification
     - later: inspect/final/artifact methods

2. Refactor ``admin_cli.py`` to choose one backend for the whole invocation.

   Current problem:

   - execution mode is decided ad hoc per command
   - some commands branch on ``--host`` / ``--api-key``
   - some commands are always local even in cloud context

   Required change:

   - context selection happens once
   - ``remote`` / ``cloud`` context injects the remote backend
   - command handlers call backend methods instead of branching on transport

3. Remove or retire command-level transport branching.

   Current examples in ``admin_cli.py``:

   - ``_should_use_remote_device_api()``
   - device command wrappers that decide local vs remote internally
   - direct use of local service factories in commands that should eventually be
     mode-pure

4. Keep only the currently supported remote command set enabled in remote mode.

   Use existing server endpoints for:

   - ``device list``
   - ``device pending``
   - ``device validate``
   - ``device approve``
   - ``device revoke``
   - ``device issue-token``
   - ``job list-assignments``
   - ``job assign``
   - ``job unassign``
   - ``job set-status``
   - ``job unlock``
   - ``round reopen``
   - ``tree identify``

5. Mark unsupported remote commands explicitly.

   For phase 1, remote mode should reject:

   - ``customer ...``
   - ``customer billing ...``
   - ``job create``
   - ``job update``
   - ``job inspect``
   - ``round inspect``
   - ``review inspect``
   - ``final inspect``
   - ``final set-final``
   - ``final set-correction``
   - ``artifact fetch``

   Required behavior:

   - fail immediately
   - explain that the command is not yet exposed by the remote admin API
   - do not fall back to local

6. Keep shared transport helpers but treat them as infrastructure only.

   Existing helpers in ``admin_cli.py`` can remain initially:

   - ``_http()``
   - ``_encode_multipart()``

   They should be used by the remote backend, not by command wrappers making
   their own transport decisions.

7. Make REPL/context behavior explicit.

   Requirements:

   - ``use cloud`` or ``use remote`` must switch the whole backend
   - ``show`` must make mode obvious
   - remote mode must stay remote for the whole REPL session


Phase 2: Add Remote Inspection Parity
=====================================

Goal
----

After remote mode is honest, add the missing server read/admin endpoints needed
for operator visibility during field testing.

Acceptance criteria
-------------------

- Operators can inspect job, round, review, and final state remotely.
- Operators can fetch relevant artifacts remotely.
- CLI output remains aligned with the current inspect/artifact service payloads
  where practical.

Implementation checklist
------------------------

1. Add remote admin inspection endpoints on the server.

   Preferred approach:

   - follow existing router/service precedent
   - keep router layer thin
   - reuse ``InspectionService`` rather than duplicating inspection logic

   Suggested endpoints:

   - ``GET /v1/admin/jobs/{job_id}``
   - ``GET /v1/admin/jobs/{job_id}/rounds/{round_id}``
   - ``GET /v1/admin/jobs/{job_id}/rounds/{round_id}/review``
   - ``GET /v1/admin/jobs/{job_id}/final``

2. Add remote artifact download/export endpoints.

   Reuse the existing artifact resolution logic where possible.

   Suggested initial scope:

   - report PDF
   - TRAQ PDF
   - transcript
   - final JSON

3. Reuse service boundaries already present in the repo.

   Existing services to reuse:

   - ``InspectionService``
   - ``ArtifactFetchService``

   Existing auth/admin enforcement to reuse:

   - ``AccessControlService``
   - admin route patterns already used in ``app/api/admin_routes.py``

4. Add remote backend methods for the new inspection and artifact endpoints.

   New remote methods should back:

   - ``job inspect``
   - ``round inspect``
   - ``review inspect``
   - ``final inspect``
   - ``artifact fetch``

5. Keep payload shapes aligned where practical.

   The CLI should avoid separate display logic for local and remote where
   possible.

   Preferred rule:

   - local and remote backends return the same command payload shape
   - command handlers remain thin presentation wrappers


Architecture Notes
==================

The repo already has the right precedent for this work:

- ``admin_cli.py`` should be a composition/parser shell
- ``app/cli/*.py`` should stay thin
- services own business rules
- routers expose remote contracts

This refactor should move the CLI toward a clean backend-selection model, not
deeper inline branching.

The remote branch should not try to solve all parity at once.

Correct intermediate state:

- local mode remains complete
- remote mode is honest but partial
- no hidden mixing


Testing Checklist
=================

Phase 1 tests
-------------

- remote mode does not instantiate local service/store factories
- supported remote commands call HTTP only
- unsupported remote commands fail explicitly
- REPL context switching preserves backend purity

Phase 2 tests
-------------

- admin inspection endpoints return expected payloads
- remote inspect commands use those endpoints only
- remote artifact fetch uses server endpoints only
- payload shapes remain stable between local and remote command backends


Definition of Done
==================

Phase 1 done:

- remote mode is HTTP-only
- currently supported field-test commands work remotely
- unsupported commands do not fall back to local

Phase 2 done:

- job/round/review/final inspection works remotely
- artifact retrieval works remotely
- remote CLI supports live operator workflows needed during field testing
