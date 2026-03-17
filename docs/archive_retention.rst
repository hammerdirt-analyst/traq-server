Archive Retention
=================

Purpose
-------

This note defines the current archive retention policy for final and correction
work.

Policy
------

When a job is archived:

Keep
^^^^

- immutable original final snapshot
- current correction snapshot, if present
- transcript text for the final round
- transcript text for the correction round, if present
- generated outputs:

  - final JSON
  - final/correction TRAQ PDF
  - final/correction report PDF
  - final/correction report DOCX
  - final/correction GeoJSON

- retained report images and image artifacts referenced by final/correction
- audit/event history

Prune
^^^^^

- raw audio files from archived rounds
- correction audio after correction transcript exists
- review JSON for archived rounds
- working rounds not referenced by the retained final/correction provenance

Why
---

The reporting and legal record is the retained final/correction snapshot plus
its transcript and generated outputs. Raw audio is processing input, not part of
the retained archive.

Implementation boundary
-----------------------

The current implementation is descriptive and testable, not yet destructive.

Code:
- ``server/app/archive_policy.py``

Tests:
- ``server/tests/test_archive_policy.py``

Query support:
- ``server/tools/query_imported_jobs.py archive-retention``
