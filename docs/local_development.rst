Local Development
=================

Purpose
-------

This document defines the supported local development and testing workflow for
the standalone ``server/`` repo.

Supported local modes
---------------------

Use one of these modes locally:

1. native ``uv`` workflow
   - primary development mode
   - fastest for editing, tests, and manual API work

2. local Docker workflow
   - smoke test for the production container image
   - useful before Cloud Run deployment

Use the native ``uv`` workflow for day-to-day development. Use Docker to
validate packaging and runtime parity.

Prerequisites
-------------

Required:

- Python 3.12
- ``uv``
- PostgreSQL reachable from the local machine

Required for full media/final flows:

- ``ffprobe`` / ``ffmpeg``
- ``OPENAI_API_KEY`` for live extraction and summary generation

Repo bootstrap
--------------

From the repo root::

   cd /path/to/server
   uv sync

This creates the local virtual environment and installs the pinned toolchain.

Environment file
----------------

Local development may use ``server/.env``.

Minimum required values:

- ``TRAQ_DATABASE_URL``
- ``TRAQ_API_KEY``

Common local values:

- ``TRAQ_STORAGE_ROOT=./local_data``
- ``TRAQ_ENABLE_DISCOVERY=true``
- ``TRAQ_AUTO_CREATE_SCHEMA=true``
- ``TRAQ_ENABLE_FILE_LOGGING=true``

The server loads ``.env`` automatically unless variables are already set in the
shell.

Local PostgreSQL workflow
-------------------------

Recommended local pattern:

- use a dedicated local database for active development
- keep a separate working database if you want to preserve current data

Development modes:

1. convenience bootstrap

   - leave ``TRAQ_AUTO_CREATE_SCHEMA=true``
   - useful for ad hoc local work and quick experiments

2. migration-driven local work

   - set ``TRAQ_AUTO_CREATE_SCHEMA=false``
   - run::

       uv run alembic upgrade head

   - use this when validating deployment-like behavior

If you are changing schema, use Alembic even locally.

Running the server
------------------

Normal local run::

   uv run traq-server --reload --port 8000

If ``ffprobe`` is not on the default ``PATH``, set ``TRAQ_FFPROBE_BIN`` in the
shell before starting the server.

Running the admin CLI
---------------------

Interactive mode::

   uv run traq-admin

One-shot examples::

   uv run traq-admin device list
   uv run traq-admin job list-assignments
   uv run traq-admin customer list

Automated tests
---------------

Core regression set::

   UV_CACHE_DIR=/tmp/uv-cache uv run python -m unittest \
     tests.test_config \
     tests.test_artifact_storage \
     tests.test_tree_identity_api \
     tests.test_db_store

Use the narrower target first when iterating on one area. Run the broader suite
before committing deployment-facing changes.

Manual smoke testing
--------------------

Recommended order:

1. start the server
2. verify CLI access
3. fetch assigned jobs on device
4. edit and submit one review
5. test one audio/transcript path
6. test one image path
7. submit final
8. verify the finalized job is unassigned and does not reappear as active work

Local Docker smoke test
-----------------------

Build::

   docker build -t traq-server:local .

Run against local PostgreSQL on Linux::

   docker run --rm --network host \
     -e TRAQ_DATABASE_URL='postgresql+psycopg://traq_app:<password>@127.0.0.1:5432/traq_demo' \
     -e TRAQ_API_KEY='demo-key' \
     -e OPENAI_API_KEY='<key>' \
     -e TRAQ_ARTIFACT_BACKEND='local' \
     -e TRAQ_STORAGE_ROOT='/tmp/traq-local-data' \
     traq-server:local

Then verify::

   curl -H 'X-API-Key: demo-key' http://127.0.0.1:8000/health

Local data handling
-------------------

``TRAQ_STORAGE_ROOT`` is local-only and git-ignored.

It contains:

- artifact bytes
- generated outputs
- debug/export compatibility files
- local rotating log files when file logging is enabled

It is disposable if the database remains intact, but deleting it will remove
local artifacts and logs.

Practical guidance
------------------

- use native ``uv`` mode for normal coding
- use Docker only to validate the deployment package
- use Alembic for schema changes
- do not treat local artifact storage as authoritative runtime state
