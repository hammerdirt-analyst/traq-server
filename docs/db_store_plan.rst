Database Store Plan
===================

Purpose
-------

This note records the first database-backed operational store that mirrors the
existing file-backed auth/assignment/job metadata contracts.

Module
------

- ``app/db_store.py``

Scope
-----

The database store currently covers:
- device registration
- device approval and revocation
- token issuance and validation
- job assignment and unassignment
- job lookup and listing
- job upsert for future admin-created jobs

Contract goal
-------------

The database store is designed to return dictionaries compatible with the
current API/CLI patterns so the server can be moved over incrementally.

Why this matters first
----------------------

Operationally, the first live PostgreSQL-backed behaviors should be:
- add jobs
- assign jobs to a device
- validate devices and roles
- issue tokens
- list assigned jobs

Those are the controls needed before round/media/runtime migration.

Current status
--------------

- schema exists
- importer exists
- query tooling exists
- database-backed store exists as a service layer
- live server runtime now uses the database-backed store for:

  - device registration
  - token validation
  - token issuance
  - job assignment listing
  - admin assign / unassign
  - job metadata upsert during job record persistence

- ``admin_cli.py`` device approval, revocation, listing, and token
  issuance now use the database-backed store directly
  and runtime auth/assignment state is DB-backed

Next migration step
-------------------

Continue reducing remaining legacy file-backed helpers so runtime inspection and
operational paths depend on PostgreSQL for state and local storage only for
artifacts/exports.
