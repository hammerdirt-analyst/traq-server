CLI User Guide
==============

Purpose
-------

``traq-admin`` is the operator CLI for the server. It is meant to help with:

- device approval and token issuance
- customer, billing, and job administration
- round lifecycle testing
- inspection of review/final state
- artifact download
- standalone tree identification

This document is a user manual. It explains what the CLI covers today, what is
still missing, and how to run the common workflows.


Modes
-----

The CLI has two execution modes.

``local``
  Uses local services, the local database, and local artifact access.

``cloud``
  Uses HTTP against the deployed server only.

Examples::

   uv run traq-admin local
   uv run traq-admin cloud
   uv run traq-admin cloud device pending
   uv run traq-admin local tree identify --image ./leaf.jpg

Mode rule:

- local mode should not silently use remote HTTP as its execution boundary
- cloud mode should not silently inspect the local database or local files as
  its execution boundary
- if a cloud command is not implemented remotely yet, it should fail
  explicitly


Prerequisites
-------------

For local mode:

- a working local database configuration
- the usual local server environment variables in ``.env`` or the shell

For cloud mode:

- ``TRAQ_CLOUD_ADMIN_BASE_URL``
- ``TRAQ_CLOUD_API_KEY``

The CLI reads those automatically for ``uv run traq-admin cloud ...``.


Interactive Use
---------------

Start the REPL::

   uv run traq-admin local
   uv run traq-admin cloud

Useful meta-commands inside the REPL::

   show
   use local
   use cloud
   set host https://example.run.app
   set api-key <admin-key>
   help
   exit

Operational commands use the same syntax as one-shot commands. A leading
``/`` is optional.


What Is Covered
---------------

The current CLI surface is:

``device``
  ``list``, ``pending``, ``validate``, ``approve``, ``revoke``,
  ``issue-token``

``customer``
  ``list``, ``duplicates``, ``create``, ``update``, ``usage``, ``merge``,
  ``delete``

``customer billing``
  ``list``, ``duplicates``, ``create``, ``update``, ``usage``, ``merge``,
  ``delete``

``job``
  ``create``, ``update``, ``list-assignments``, ``assign``, ``unassign``,
  ``set-status``, ``unlock``, ``inspect``

``round``
  ``create``, ``manifest get``, ``manifest set``, ``submit``, ``reprocess``,
  ``reopen``, ``inspect``

``review``
  ``inspect``

``final``
  ``inspect``

``artifact``
  ``fetch``

``stage``
  ``sync``, ``exclusions``, ``exclude``, ``include``

``tree``
  ``identify``

``net``
  ``ipv4``, ``ipv6``


Known Limits
------------

These areas are still intentionally incomplete:

``final set-final`` / ``final set-correction``
  Present locally, but not yet part of the current cloud parity work.

``archive`` workflows
  No dedicated CLI command group yet for archive inspection or retention
  decisions.

``round submit`` and ``round reprocess`` in local mode
  These currently fail explicitly. The remote HTTP contract exists and is the
  supported testing path today. A clean local service seam for those flows has
  not been extracted yet.


Common Cloud Workflows
----------------------

Device approval::

   uv run traq-admin cloud device pending
   uv run traq-admin cloud device approve <device_id> --role arborist
   uv run traq-admin cloud device issue-token <device_id> --ttl 604800

Customer and billing administration::

   uv run traq-admin cloud customer list --search Arboretum
   uv run traq-admin cloud customer create --name "Customer Name" --phone "555-1212"
   uv run traq-admin cloud customer billing list --search Customer
   uv run traq-admin cloud customer billing create --billing-name "Customer Billing"

Project administration::

   uv run traq-admin cloud project list
   uv run traq-admin cloud project create --project "Briarwood"
   uv run traq-admin cloud project update --project-ref project_abc123 --project "Briarwood West"

Job administration::

   uv run traq-admin cloud job create --job-id job_1 --job-number J0001 --customer-id C0001
   uv run traq-admin cloud job create --job-id job_2 --job-number J0002 --customer-id C0001 --project-id project_abc123
   uv run traq-admin cloud job update --job J0001 --job-name "Valley Oak Revisit" --project-id project_abc123
   uv run traq-admin cloud job update --job J0001 --clear-project
   uv run traq-admin cloud job inspect --job J0001
   uv run traq-admin cloud job list-assignments
   uv run traq-admin cloud job assign --job J0001 --device-id <device_id>
   uv run traq-admin cloud job unlock --job J0001 --round-id round_1 --device-id <device_id>

Round lifecycle::

   uv run traq-admin cloud round create --job J0001
   uv run traq-admin cloud round manifest set --job J0001 --round-id round_1 --file ./manifest_smoke.json
   uv run traq-admin cloud round manifest get --job J0001 --round-id round_1
   uv run traq-admin cloud round submit --job J0001 --round-id round_1 --file ./templates/round_submit.template.json
   uv run traq-admin cloud round reprocess --job J0001 --round-id round_1
   uv run traq-admin cloud round inspect --job J0001 --round-id round_1

Review, final, and artifact inspection::

   uv run traq-admin cloud review inspect --job J0001 --round-id round_1
   uv run traq-admin cloud final inspect --job J0001
   uv run traq-admin cloud artifact fetch --job J0001 --kind final-json
   uv run traq-admin cloud artifact fetch --job J0001 --kind geo-json
   uv run traq-admin cloud artifact fetch --job J0001 --kind report-pdf

Export image and GeoJSON retrieval for downstream reporting::

   uv run traq-admin cloud export image-fetch --job-id job_1 --image-ref img_1 --variant report
   uv run traq-admin cloud export images-fetch-all --job J0001 --variant report
   uv run traq-admin cloud export geojson-fetch --job-id job_1

Local staging curation for downstream reporter flow::

   uv run traq-admin cloud stage sync --root /home/roger/projects/codex_trial/agent_client/server/staging
   uv run traq-admin stage exclude --job J0001 --root /home/roger/projects/codex_trial/agent_client/server/staging
   uv run traq-admin stage exclusions --root /home/roger/projects/codex_trial/agent_client/server/staging
   uv run traq-admin stage include --job J0001 --root /home/roger/projects/codex_trial/agent_client/server/staging

Standalone tree identification::

   uv run traq-admin cloud tree identify --image ./bark.jpg


Round Test Files
----------------

Two files in the repo are meant to make round smoke tests easier:

``manifest_smoke.json``
  Minimal example manifest for ``round manifest set``.

``templates/round_submit.template.json``
  Minimal example submit payload for ``round submit --file``.

Recommended smoke-test sequence:

1. create a round
2. set manifest from ``manifest_smoke.json``
3. copy and edit ``templates/round_submit.template.json`` if needed
4. submit the round
5. inspect the round and review payload
6. reprocess if needed


How To Read Failures
--------------------

For most cloud commands, the useful question is:

- did the CLI fail locally, or
- did the server reject/process the request and return a real response?

Examples:

- ``HTTP 404`` usually means the job or round could not be resolved remotely
- ``HTTP 405`` usually means the deployed server revision does not yet have the
  requested route/method
- an ``accepted`` or ``status`` response from ``round submit`` / ``round
  reprocess`` means the CLI path worked and any remaining issue is in runtime
  processing rather than command dispatch


What To Update When Commands Change
-----------------------------------

If the CLI command surface changes, keep this document current by updating:

- covered command groups
- known limits
- smoke-test examples
- any committed fixture/template paths used for testing
- local staging curation commands when downstream handoff workflows change
