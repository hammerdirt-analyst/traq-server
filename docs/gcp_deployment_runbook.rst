GCP Deployment Runbook
======================

Purpose
-------

This runbook defines the first controlled beta deployment path for the TRAQ
server on GCP.

Deployment model
----------------

Target services:

- Cloud Run for the API container
- Cloud SQL for PostgreSQL
- Cloud Storage for artifact bytes
- Artifact Registry for container images
- Secret Manager for runtime secrets

The current beta security model is operator-only for admin actions.

Prerequisites
-------------

Before starting:

- Docker image builds and runs locally
- Alembic migrations are clean
- docs build cleanly
- a GCP project exists
- billing is enabled
- ``gcloud`` is installed and authenticated

Required local tools:

- ``gcloud``
- ``docker``
- ``uv``

Suggested environment variables
-------------------------------

Set these locally before running the commands in this document::

   export GCP_PROJECT_ID=<project-id>
   export GCP_REGION=us-central1
   export GCP_REPOSITORY=traq-server
   export GCP_SERVICE=traq-server
   export GCP_BUCKET=<artifact-bucket-name>
   export GCP_SQL_INSTANCE=traq-postgres
   export GCP_DB_NAME=traq_demo
   export GCP_DB_USER=traq_app

Project bootstrap
-----------------

Select the project and enable the required APIs::

   gcloud config set project "$GCP_PROJECT_ID"
   gcloud services enable \
     run.googleapis.com \
     sqladmin.googleapis.com \
     artifactregistry.googleapis.com \
     secretmanager.googleapis.com \
     storage.googleapis.com

Provision Artifact Registry
---------------------------

Create the Docker repository once::

   gcloud artifacts repositories create "$GCP_REPOSITORY" \
     --repository-format=docker \
     --location="$GCP_REGION"

Configure Docker auth::

   gcloud auth configure-docker "$GCP_REGION-docker.pkg.dev"

Provision Cloud Storage
-----------------------

Create the artifact bucket once::

   gcloud storage buckets create "gs://$GCP_BUCKET" \
     --location="$GCP_REGION"

Provision Cloud SQL
-------------------

Create a PostgreSQL instance, database, and application user::

   gcloud sql instances create "$GCP_SQL_INSTANCE" \
     --database-version=POSTGRES_16 \
     --region="$GCP_REGION"

   gcloud sql databases create "$GCP_DB_NAME" \
     --instance="$GCP_SQL_INSTANCE"

   gcloud sql users create "$GCP_DB_USER" \
     --instance="$GCP_SQL_INSTANCE" \
     --password='<set-a-db-password>'

You will then need the Cloud SQL connection name::

   gcloud sql instances describe "$GCP_SQL_INSTANCE" \
     --format='value(connectionName)'

Record that value for the Cloud Run deploy step.

Create runtime secrets
----------------------

Create or update the runtime secrets in Secret Manager::

   printf '%s' '<set-a-strong-admin-api-key>' | \
     gcloud secrets create traq-api-key --data-file=- || \
     printf '%s' '<set-a-strong-admin-api-key>' | \
     gcloud secrets versions add traq-api-key --data-file=-

   printf '%s' '<set-your-openai-api-key>' | \
     gcloud secrets create traq-openai-api-key --data-file=- || \
     printf '%s' '<set-your-openai-api-key>' | \
     gcloud secrets versions add traq-openai-api-key --data-file=-

   printf '%s' 'postgresql+psycopg://<user>:<password>@/<db>?host=/cloudsql/<connection-name>' | \
     gcloud secrets create traq-database-url --data-file=- || \
     printf '%s' 'postgresql+psycopg://<user>:<password>@/<db>?host=/cloudsql/<connection-name>' | \
     gcloud secrets versions add traq-database-url --data-file=-

Build and push the image
------------------------

Build and push the image to Artifact Registry::

   export IMAGE_URI="$GCP_REGION-docker.pkg.dev/$GCP_PROJECT_ID/$GCP_REPOSITORY/traq-server:$(git rev-parse --short HEAD)"

   docker build -t "$IMAGE_URI" .
   docker push "$IMAGE_URI"

Run migrations
--------------

Run Alembic against Cloud SQL before deploying the new revision.

For the first controlled beta, the simplest operator path is to run the
migration from a trusted operator environment using the production
``TRAQ_DATABASE_URL``::

   TRAQ_DATABASE_URL='postgresql+psycopg://<user>:<password>@/<db>?host=/cloudsql/<connection-name>' \
   UV_CACHE_DIR=/tmp/uv-cache \
   uv run alembic upgrade head

This step must succeed before deploying the new Cloud Run revision.

Deploy Cloud Run
----------------

Deploy the service with cloud-safe runtime flags::

   gcloud run deploy "$GCP_SERVICE" \
     --image "$IMAGE_URI" \
     --region "$GCP_REGION" \
     --platform managed \
     --allow-unauthenticated \
     --add-cloudsql-instances <connection-name> \
     --set-env-vars TRAQ_ARTIFACT_BACKEND=gcs,TRAQ_GCS_BUCKET="$GCP_BUCKET",TRAQ_ENABLE_DISCOVERY=false,TRAQ_AUTO_CREATE_SCHEMA=false,TRAQ_ENABLE_FILE_LOGGING=false \
     --set-secrets TRAQ_API_KEY=traq-api-key:latest,OPENAI_API_KEY=traq-openai-api-key:latest,TRAQ_DATABASE_URL=traq-database-url:latest

Notes:

- ``--allow-unauthenticated`` is acceptable because the app enforces its own
  device/bootstrap/auth model.
- admin actions remain operator-only because the admin credential is not shared
  with field devices.

Post-deploy validation
----------------------

After deploy, verify:

1. health endpoint responds
2. device registration works
3. approved device can get token
4. assigned jobs endpoint works with device token
5. upload / submit / final flow works
6. artifacts land in Cloud Storage

Recommended checks::

   curl https://<service-url>/health

   UV_CACHE_DIR=/tmp/uv-cache uv run traq-admin \
     --host https://<service-url> \
     --api-key '<operator-api-key>' \
     device list

Rollback
--------

If deploy validation fails:

1. roll Cloud Run back to the previous revision
2. inspect logs
3. inspect Cloud SQL connectivity
4. verify secrets and bucket config
5. only roll forward again after the failure is understood

Operator notes
--------------

- keep ``TRAQ_API_KEY`` only in trusted operator environments
- do not enter the admin key on field devices
- do not use the admin key as a registration bootstrap secret
- treat ``traq-admin`` as the operator interface for beta
