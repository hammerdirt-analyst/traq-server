Runtime vs Export Boundary
==========================

Purpose
-------

This note defines the current storage boundary for the standalone server repo.

Rule
----

PostgreSQL is authoritative for runtime operational state.

The filesystem is limited to:

- uploaded artifact bytes
- generated outputs
- exported debug/compatibility copies

Runtime authority
-----------------

The following state is DB-backed and must not be reconstructed from exported
JSON files on disk:

- devices, tokens, and assignments
- customers, billing profiles, operators, and trees
- jobs and job shell metadata
- rounds and round status
- round manifest payloads
- round review payloads
- runtime profile state
- recording metadata and processed/transcript state
- image metadata
- finals, corrections, and GeoJSON rows

Artifact storage
----------------

The filesystem remains the storage location for artifact bytes and generated
outputs, including:

- uploaded audio files
- uploaded image files
- generated report images
- generated PDFs and DOCX

Export/debug copies
-------------------

The server may still write compatibility or inspection-oriented files under the
storage root. These files are not authoritative runtime state.

Examples:

- ``local_data/jobs/<job_id>/job_record.json``
- ``local_data/jobs/<job_id>/rounds/<round_id>/manifest.json``
- ``local_data/jobs/<job_id>/rounds/<round_id>/review.json``
- ``local_data/jobs/<job_id>/sections/<section_id>/recordings/<recording_id>.meta.json``
- ``local_data/jobs/<job_id>/sections/<section_id>/images/<image_id>.meta.json``

Operational rule
----------------

If a DB row and an exported JSON file disagree:

- the DB row wins for runtime behavior
- the exported file is treated as stale debug output

Why this matters
----------------

This boundary is required for:

- cloud migration of operational state
- predictable device/client behavior
- avoiding split-brain bugs between in-memory, DB, and disk JSON
- keeping local storage focused on artifacts rather than workflow authority
