PostgreSQL Bootstrap
====================

Purpose
-------

This note records the initial PostgreSQL bring-up state for the TRAQ server and
the steps needed to make the local database usable.

Observed host state on 2026-03-13
---------------------------------

Environment:

- host OS: Ubuntu 24.04.3 LTS
- PostgreSQL client: 17.7

What was verified:

- ``psql --version`` returned ``PostgreSQL 17.7``.
- ``postgresql.service`` is installed, enabled, and active.
- ``pg_lsclusters`` reported:

  - version: ``17``
  - cluster: ``main``
  - port: ``5432``
  - status: ``online``

- TCP listener exists on ``127.0.0.1:5432``.
- ``pg_isready -h 127.0.0.1 -p 5432`` reports ``accepting connections`` when run
  outside the sandbox.

Current access problem
----------------------

Two access paths were checked:

1. local socket as the current Linux user

   - ``psql`` fails because PostgreSQL role ``roger`` does not exist.

2. TCP as ``postgres``

   - ``psql -h 127.0.0.1 -U postgres`` reaches the server but requires a
     password.

This means PostgreSQL itself is running correctly. The remaining setup work is
account/bootstrap configuration.

Recommended bootstrap path
--------------------------

Use the system ``postgres`` account once to create:

- an application role for the TRAQ server
- an application database owned by that role

Example bootstrap commands::

   sudo -u postgres psql

Then inside ``psql``::

   CREATE ROLE traq_app WITH LOGIN PASSWORD '<set-a-db-password>';
   CREATE DATABASE traq_demo OWNER traq_app;
   \du
   \l

Optional hardening later:

- create separate read-only/admin roles
- tighten ``pg_hba.conf``
- require password auth only for TCP clients

Connection target for the server
--------------------------------

Initial connection string format::

   postgresql+psycopg://traq_app:<set-a-db-password>@127.0.0.1:5432/traq_demo

Why PostgreSQL is the chosen direction
--------------------------------------

The server needs relational integrity for:

- devices
- device tokens
- jobs
- assignments
- state transitions
- finals and corrections
- audit/event history

Artifacts such as PDFs, audio, and images should remain on disk or move to
object storage later. PostgreSQL should become the system of record for
metadata and workflow state.

Migration direction
-------------------

Target shape:

- PostgreSQL-backed metadata and workflow state
- existing CLI retained for validation, assignment, and status operations
- current FastAPI server retained during the migration
- filesystem reduced to artifact storage rather than source-of-truth metadata
