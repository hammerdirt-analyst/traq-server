Deployment and Operations
=========================

Purpose
-------

This document defines the intended operational model for deployment, secrets,
backups, and runtime behavior as the server moves toward GCP.

Target deployment shape
-----------------------

Planned target:

- Cloud Run for the API runtime
- PostgreSQL for authoritative runtime state
- Google Cloud Storage for artifact bytes

Current deployment policy
-------------------------

Production/cloud settings:

- ``TRAQ_ENABLE_DISCOVERY=false``
- ``TRAQ_AUTO_CREATE_SCHEMA=false``
- ``TRAQ_ENABLE_FILE_LOGGING=false``
- ``TRAQ_ARTIFACT_BACKEND=gcs``
- ``TRAQ_GCS_BUCKET=<bucket>``
- optional ``TRAQ_GCS_PREFIX=<prefix>``

Required secrets and config
---------------------------

Required runtime values:

- ``TRAQ_DATABASE_URL``
- ``TRAQ_API_KEY``
- ``OPENAI_API_KEY``
- ``TRAQ_PLANTNET_API_KEY`` when standalone tree identification is enabled
- ``TRAQ_ARTIFACT_BACKEND``
- ``TRAQ_GCS_BUCKET`` when using GCS

Recommended secret handling:

- store secrets in Secret Manager or equivalent
- inject them as environment variables at deploy time
- do not bake secrets into the image
- do not commit secrets to ``.env`` in the repo

Standalone tree-identification policy:

- ``POST /v1/trees/identify`` is a standalone service route
- it depends on ``TRAQ_PLANTNET_API_KEY`` and the configured Pl@ntNet upstream
- when the upstream configuration or upstream service is unavailable, the
  server returns the normalized upstream failure response

Migration workflow
------------------

Production schema changes should run explicitly through Alembic.

Deploy order:

1. build and publish the image
2. run::

      uv run alembic upgrade head

3. deploy the new app revision

The production app should not create schema on startup.

Logging model
-------------

Local development:

- console logging
- optional rotating file logging

Cloud deployment:

- console logging only
- rely on the platform log sink for aggregation and retention

Artifact handling
-----------------

Runtime state is database-authoritative.

Artifact storage is for:

- uploaded audio
- uploaded images
- generated report images
- final PDFs / DOCX
- optional exported GeoJSON files

Initial cloud download policy:

- app-streamed downloads
- signed URLs deferred

Backup expectations
-------------------

Two backup domains matter:

1. PostgreSQL

   This is the system of record for runtime state.

   Protect:

   - jobs
   - assignments
   - rounds
   - review payloads
   - media metadata
   - finals/corrections
   - counters
   - runtime profiles

   Operational requirement:

   - regular database backups must exist before production use

2. Artifact storage

   Artifact bytes are no longer authoritative for workflow state, but they are
   still operationally important.

   Protect:

   - uploaded audio and images
   - generated final outputs
   - report assets

   Operational requirement:

   - storage retention and recovery policy must be defined for production

Security posture
----------------

Minimum expectations:

- no discovery in cloud
- no local file logging dependency in cloud
- no automatic schema creation in cloud
- secrets injected by environment or secret manager
- least-privilege credentials for database and storage access
- operator-only admin model for beta deployment

Operator-only admin model for beta
----------------------------------

The current beta posture is intentionally **not** a public admin surface.

Admin operations are expected to run only from a trusted operator environment:

- ``traq-admin`` on an operator workstation, shell, or controlled runner
- ``TRAQ_API_KEY`` treated as an operator credential, not a field-device secret
- no admin key embedded in the client application
- no admin key entered during device registration or field setup

This means:

- field devices use issued device tokens
- device bootstrap remains limited to registration / status / token issuance
- broad admin mutation workflows remain operator-only

This is acceptable for controlled beta. It is not the final long-term admin
identity model.

Additional controls to define before broad production use:

- database backup retention window
- artifact bucket access policy
- service account scope for Cloud Storage
- deployment rollback procedure
- long-term named admin identity model beyond the shared operator key

Known non-blocking issue
------------------------

Tracked in the remote issue tracker:

- archived jobs can still auto-claim after local restore and should require an
  explicit reopen flow

This is a lifecycle control issue, not a deployment blocker for the first cloud
rollout.

Practical conclusion
--------------------

The repo now supports a clean split between:

- local development
- production deployment behavior

The remaining work is deployment execution and operations policy, not core
runtime-state architecture cleanup.
