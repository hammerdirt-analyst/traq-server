Project Metadata Feature Note
=============================

Purpose
-------

This branch implements first-class optional project metadata owned by the
server. The goal is to make project assignment authoritative at the job level so
admin tooling, staged bundles, the mobile client, and the reporter pipeline all
consume the same identity rather than inventing grouping conventions locally.

Scope
-----

Phase 1 includes:

- a server-managed project registry
- optional project assignment on job create and job update
- job read contracts that expose ``project_id``, ``project``, and
  ``project_slug``
- admin CLI support for managing projects and assigning them to jobs
- staging/export propagation of resolved project fields where job payloads are
  already exposed

Phase 1 explicitly does not include:

- project-based filtering/grouping UX
- free-text project entry from any client
- reporter-specific grouping behavior beyond consuming staged resolved fields

Contract
--------

Project assignment is optional in v1.

- jobs may have ``project_id = null``
- job creation must continue to work when no projects exist
- project assignment must be editable after create

The authoritative write field is ``project_id``. The server resolves and returns
these three fields on job reads:

- ``project_id``
- ``project``
- ``project_slug``

Frontend clients must only choose from server-provided project values.

Implementation Direction
------------------------

The implementation should use a dedicated ``projects`` table and a nullable
foreign key on ``jobs``. This avoids free-text drift and keeps slug generation
canonical.

The initial vertical slice should touch:

- SQLAlchemy models and Alembic migration
- job mutation service
- job read surfaces (DB store, inspection, device/admin responses)
- admin API models/routes
- admin CLI commands for project list/create/update and job assignment
- tests for null assignment, valid assignment, invalid ``project_id``, and read
  contract propagation

Why This Exists
---------------

Reporter/staging work already proved that project grouping is operationally
important, but the current values are manual and provisional. This feature makes
project identity authoritative before UI filtering/grouping is added.
