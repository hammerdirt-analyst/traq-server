Testing And Validation
======================

Purpose
-------

This document defines the canonical validation path for changes in this repo.
It is the primary reference for:

- what to run locally before push
- what GitHub runs on pull requests
- what the deploy workflow runs before and after deployment

Local developer validation
--------------------------

Required local regression command before push::

   cd /home/roger/projects/codex_trial/agent_client/server
   UV_CACHE_DIR=/tmp/uv-cache uv run python scripts/release_verify.py pre-deploy

This is the canonical local validation path for deployment-facing changes.

What it covers
--------------

The current pre-deploy gate runs these test modules:

- ``tests.test_api_routers``
- ``tests.test_admin_cli_devices_and_context``
- ``tests.test_admin_cli_exports_stage_repl``
- ``tests.test_admin_cli_jobs_rounds``
- ``tests.test_admin_cli_customers_artifacts``
- ``tests.test_command_registry``
- ``tests.test_config``
- ``tests.test_export_sync_service``
- ``tests.test_final_report_images_service``
- ``tests.test_media_runtime_service``
- ``tests.test_report_image_runtime_service``
- ``tests.test_staging_sync_service``
- ``tests.test_tree_identification_service``

These tests run with CI-safe local defaults:

- ``TRAQ_DATABASE_URL=sqlite+pysqlite:///:memory:``
- ``TRAQ_ENABLE_DISCOVERY=false``
- ``TRAQ_AUTO_CREATE_SCHEMA=false``
- ``TRAQ_ENABLE_FILE_LOGGING=false``

CI validation
-------------

Pull request workflows:

1. PR verification

   - workflow: ``.github/workflows/server-pr-verification.yml``
   - runs the same canonical pre-deploy gate::

       uv run python scripts/release_verify.py pre-deploy

2. PostgreSQL integration smoke lane

   - workflow: ``.github/workflows/server-postgres-ci.yml``
   - boots temporary PostgreSQL in GitHub Actions
   - runs::

       uv run alembic upgrade head
       uv run python -m unittest tests.test_postgres_ci_smoke

Deployment validation
---------------------

The deploy workflow is:

- ``.github/workflows/server-cloudrun.yml``

It runs:

1. pre-deploy gate
2. image build and push
3. migration job update and execution
4. Cloud Run service deploy
5. post-deploy health verification

Post-deploy verification
------------------------

The canonical post-deploy check is::

   UV_CACHE_DIR=/tmp/uv-cache uv run python scripts/release_verify.py post-deploy

Required environment:

- ``TRAQ_CLOUD_ADMIN_BASE_URL``

Current scope:

- ``GET /health``

Interpretation
--------------

- local regression command:
  developer pre-push check
- PR verification:
  merge gate
- deploy verification:
  release gate
- post-deploy health:
  live-service readiness check

Practical standard
------------------

Before starting a feature branch, assume the required validation path is:

1. targeted tests for the changed area during implementation
2. canonical pre-deploy gate before push or merge
3. PostgreSQL CI lane on pull request
4. deploy workflow on ``main``

If a change is important enough to deploy, it is important enough to survive
the canonical pre-deploy gate.
