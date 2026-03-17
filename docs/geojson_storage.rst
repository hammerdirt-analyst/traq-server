GeoJSON Storage
===============

Purpose
-------

This note defines how GeoJSON exports are stored during the PostgreSQL
migration.

Current approach
----------------

Use PostgreSQL JSONB as the canonical database storage for exported GeoJSON
objects.

Table:
- ``job_geojson_exports``

Fields:
- job reference
- export kind (``final`` or ``correction``)
- raw GeoJSON payload as JSONB

Why JSONB first
---------------

This preserves the full exported object:
- geometry
- properties
- scrubbed form data
- image metadata

It is enough for:
- map serving
- export retrieval
- analysis in Python
- future migration to PostGIS if spatial indexing/querying becomes necessary

PostGIS direction
-----------------

PostGIS is still a reasonable future step, but not required for the initial
migration.

If spatial querying becomes necessary later, add derived geometry columns while
keeping the original GeoJSON payload intact.

Current tooling
---------------

Import:
- ``server/tools/import_legacy_jobs.py``

Read-only query:
- ``server/tools/query_imported_jobs.py geojson-exports``

Test:
- ``server/tests/test_geojson_export_storage.py``
