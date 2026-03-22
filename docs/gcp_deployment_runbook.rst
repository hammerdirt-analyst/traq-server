GCP Deployment Runbook
======================

Purpose
-------

This document records the verified Cloud Run deployment path for the TRAQ
server.

Deployment model
----------------

Verified runtime components:

- Cloud Run service for the API
- Cloud Run job for Alembic migrations
- Cloud SQL for PostgreSQL
- Secret Manager for runtime secrets
- Artifact Registry for container images
- Cloud Storage for artifact bytes

Working network model:

- Cloud SQL uses private IP
- Cloud Run service uses a Serverless VPC Access connector
- Cloud Run migration job uses the same VPC connector
- both the service and the job route only private IP ranges into the VPC

Verified GCP resources
----------------------

- Project ID: ``traq-server-cloud``
- Region: ``us-west1``
- Cloud Run service: ``traq-server``
- Cloud Run job: ``traq-migrate``
- Cloud SQL instance: ``traq-postgres``
- PostgreSQL database: ``traq``
- PostgreSQL role: ``traq_run``
- VPC connector: ``traq-run-connector``
- Cloud SQL private IP: ``10.0.16.3``

Runtime secrets
---------------

The database URL is stored as one complete Secret Manager value. Do not build
it from separate password variables in the job or service definition.

Working DSN format::

   postgresql+psycopg://<db_user>:<db_password>@<private_ip>:5432/traq

Do not record the live password in docs. Read the current value from Secret
Manager.

Required Secret Manager secrets:

- ``TRAQ_API_KEY``
- ``OPENAI_API_KEY``
- ``TRAQ_DATABASE_URL``
- ``TRAQ_PLANTNET_API_KEY``

Cloud Run service configuration
-------------------------------

Required env vars:

- ``TRAQ_ARTIFACT_BACKEND=gcs``
- ``TRAQ_GCS_BUCKET=<artifact bucket>``
- optional ``TRAQ_GCS_PREFIX=<prefix>``
- ``TRAQ_ENABLE_DISCOVERY=false``
- ``TRAQ_AUTO_CREATE_SCHEMA=false``
- ``TRAQ_ENABLE_FILE_LOGGING=false``

Required secret env vars:

- ``TRAQ_API_KEY``
- ``OPENAI_API_KEY``
- ``TRAQ_DATABASE_URL``
- ``TRAQ_PLANTNET_API_KEY``

Required network settings:

- VPC connector: ``traq-run-connector``
- VPC egress: ``private-ranges-only``

Cloud Run migration job configuration
-------------------------------------

Command::

   uv

Arguments::

   run
   alembic
   upgrade
   head

Required env vars:

- ``TRAQ_ENABLE_DISCOVERY=false``
- ``TRAQ_AUTO_CREATE_SCHEMA=false``
- ``TRAQ_ENABLE_FILE_LOGGING=false``

Required secret env vars:

- ``TRAQ_DATABASE_URL``

Required network settings:

- VPC connector: ``traq-run-connector``
- VPC egress: ``private-ranges-only``

Important:

- the migration job is configured separately from the service
- fixing the service network path does not fix the job
- the typo ``fasle`` in ``TRAQ_ENABLE_FILE_LOGGING`` will break migrations

PostgreSQL bootstrap
--------------------

Use Cloud SQL Studio to create the application database and role access.

Create the application database::

   CREATE DATABASE traq;

Grant the application role access::

   ALTER ROLE traq_run WITH LOGIN PASSWORD '<db_password>';
   GRANT CONNECT ON DATABASE traq TO traq_run;

Then, against database ``traq``, grant schema privileges::

   GRANT USAGE ON SCHEMA public TO traq_run;
   GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO traq_run;
   GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO traq_run;
   ALTER DEFAULT PRIVILEGES IN SCHEMA public
     GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO traq_run;
   ALTER DEFAULT PRIVILEGES IN SCHEMA public
     GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO traq_run;

Manual deployment sequence
--------------------------

Build and push the image::

   gcloud auth configure-docker us-west1-docker.pkg.dev
   cd /home/roger/projects/codex_trial/agent_client/server
   docker build -t us-west1-docker.pkg.dev/traq-server-cloud/traq-images/traq-server:initial .
   docker push us-west1-docker.pkg.dev/traq-server-cloud/traq-images/traq-server:initial

Then:

1. confirm database ``traq`` exists
2. confirm role ``traq_run`` can log in
3. execute ``traq-migrate`` and wait for success
4. deploy the new ``traq-server`` revision

Remote operator workflow
------------------------

Cloud operator actions are now performed over admin HTTP endpoints.

Configure these optional CLI context variables in ``.env`` or the shell::

   TRAQ_CLOUD_ADMIN_BASE_URL=https://traq-server-589591848994.us-west1.run.app
   TRAQ_CLOUD_API_KEY=<TRAQ_API_KEY>

Examples from a laptop::

   cd /home/roger/projects/codex_trial/agent_client/server
   UV_CACHE_DIR=/tmp/uv-cache uv run traq-admin cloud device pending
   UV_CACHE_DIR=/tmp/uv-cache uv run traq-admin cloud device approve <device_id> --role arborist
   UV_CACHE_DIR=/tmp/uv-cache uv run traq-admin cloud device issue-token <device_id> --ttl 604800

Verified cloud workflow
-----------------------

The currently verified remote workflow is:

1. register a device
2. approve the device over the admin HTTP path
3. issue a device token
4. create a job
5. create a round
6. upload section recordings and ``job_photos`` images
7. submit the round for review
8. finalize the job
9. download the final report PDF

Verified local tree-identification smoke test::

   cd /home/roger/projects/codex_trial/agent_client/server
   uv run traq-admin tree identify \
     --image ./bark.jpg \
     --organ bark \
     --host http://127.0.0.1:8000 \
     --api-key demo-key

Observed successful response characteristics:

- canonical top-level keys were returned
- ``bestMatch`` resolved to ``Castanopsis sieboldii (Makino) Hatus.``
- ``version`` resolved to ``2026-02-17 (7.4)``
- ``remainingIdentificationRequests`` resolved to ``499``

Lessons from the successful smoke test:

- CLI ``--api-key`` is the TRAQ server admin key, not the Pl@ntNet key
- ``TRAQ_PLANTNET_API_KEY`` must be present in the server process environment
- Pl@ntNet upstream IP restrictions must allow the caller public IP
- optional false-valued multipart flags must be omitted from the upstream request

GitHub Actions automation
-------------------------

Workflow file:

- ``.github/workflows/server-cloudrun.yml``

Required GitHub repository secrets:

- ``GCP_WORKLOAD_IDENTITY_PROVIDER``
- ``GCP_DEPLOYER_SERVICE_ACCOUNT``

Required GitHub repository variables:

- ``GCP_PROJECT_ID``
- ``GCP_REGION``
- ``GCP_ARTIFACT_REPOSITORY``
- ``GCP_IMAGE_NAME``
- ``GCP_CLOUD_RUN_SERVICE``
- ``GCP_CLOUD_RUN_JOB``
- ``GCP_RUNTIME_SERVICE_ACCOUNT``
- ``GCP_VPC_CONNECTOR``
- ``GCP_GCS_BUCKET``
- optional ``GCP_GCS_PREFIX``

Workflow behavior:

1. run server unit tests
2. build and push the server image
3. deploy the migration job with the new image
4. execute the migration job and wait for success
5. deploy the Cloud Run service

Verification
------------

Health check::

   curl https://traq-server-589591848994.us-west1.run.app/health

Device registration smoke test::

   curl -X POST "https://traq-server-589591848994.us-west1.run.app/v1/auth/register-device" \
     -H "Content-Type: application/json" \
     -d '{
       "device_id": "gcp-test-device-1",
       "device_name": "GCP Test Device",
       "app_version": "0.1.0",
       "profile_summary": {
         "name": "Test Operator"
       }
     }'

Current verified state:

- health works
- device registration works
- migration job succeeds
- schema exists in database ``traq``
- end-to-end cloud job cycle works through final report download

Tree identification note:

- the standalone route ``POST /v1/trees/identify`` requires ``TRAQ_PLANTNET_API_KEY``
- until that secret exists in Cloud Run, the route will return an upstream configuration error

Release notes
-------------

The fixes that made the cloud workflow work end to end were:

- remote admin device operations over HTTP
- explicit migration-job networking parity with the Cloud Run service
- manifest supplementation so uploaded recordings are not skipped when the round already contains other items
- artifact backend contract fixes for generated outputs:
  - image report derivatives now use ``stage_output`` / ``commit_output``
  - final report lookup now checks ``exists(...)`` before materializing a GCS object

Process note:

- unverified assumptions caused avoidable time loss
- verify existence and runtime contracts before acting
