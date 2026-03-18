Database Schema
===============

Purpose
-------

This document records the initial PostgreSQL schema boundary for the TRAQ
server. The goal is to move metadata and workflow state into PostgreSQL while
keeping binary artifacts on disk.

Design rules
------------

- PostgreSQL is the intended runtime target.
- SQLAlchemy models define the application schema.
- Filesystem storage remains in place for:

  - uploaded audio
  - uploaded images
  - generated PDFs
  - generated DOCX
  - exported GeoJSON

- Working round data may be pruned after archive if final snapshots and audit
  history are preserved.

Model modules
-------------

- ``app/db.py``: engine/session bootstrap, declarative base, and the local
  schema creation helper.

- ``app/db_models.py``: ORM tables for devices, jobs, rounds, media metadata,
  finals, artifacts, and events.

Core tables
-----------

Permanent records:

- ``devices``
- ``device_tokens``
- ``customers``
- ``billing_profiles``
- ``operators``
- ``trees``
- ``jobs``
- ``job_assignments``
- ``job_finals``
- ``job_geojson_exports``
- ``artifacts``
- ``job_events``

Working records:

- ``job_rounds``
- ``round_recordings``
- ``round_images``

Intent by table
---------------

``devices``
  Registered devices and their approval/role state.

``device_tokens``
  Issued bearer tokens for approved devices.

``jobs``
  Top-level job record, job number, current status, and archived final
  snapshots. Jobs reference reusable customer, billing, and operator rows while
  keeping job-specific work fields locally on the job row.

``customers``
  Reusable customer/contact identity imported from ``job_record.json``.

``billing_profiles``
  Reusable billing/contact identity imported from ``job_record.json``.

``operators``
  Reusable assessor/operator identity derived from archived final provenance.

``trees``
  Reusable customer-scoped tree identities. A tree number is unique within a
  customer and may be referenced by multiple jobs over time.

``job_assignments``
  Current one-device-at-a-time assignment mapping.

``job_rounds``
  Working review rounds and cached review payload/manifests.

``round_recordings`` / ``round_images``
  Uploaded media metadata and artifact paths.

``job_finals``
  Final or correction snapshots retained after working rounds may be pruned.

``job_geojson_exports``
  Stored GeoJSON export objects linked to the job and export kind. The raw
  GeoJSON payload is kept in PostgreSQL as JSONB while file exports remain on
  disk.

``artifacts``
  File references for generated and uploaded non-database artifacts.

``job_events``
  Append-only audit trail for status, assignment, and finalization events.

Operational direction
---------------------

Migration order should be:

1. device auth and token state
2. jobs and assignments
3. round metadata and manifests
4. media metadata
5. final/correction metadata
6. audit trail

The runtime storage migration is complete for operational state. The
filesystem remains for artifact bytes and exported debug/compatibility copies.

See also:

- ``docs/runtime_export_boundary.rst``
