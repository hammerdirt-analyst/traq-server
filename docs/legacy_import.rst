Legacy Import
=============

Purpose
-------

The legacy importer is the first non-runtime validation step for the PostgreSQL
migration. It allows the schema to be exercised against real job data without
changing the live server workflow.

Tool
----

- ``server/tools/import_legacy_jobs.py``

Current import scope
--------------------

The importer reads the current filesystem-backed job layout and loads it into
PostgreSQL:

- ``job_record.json``
- ``rounds/*/manifest.json``
- ``rounds/*/review.json``
- recording ``*.meta.json``
- image ``*.meta.json``
- ``final.json``
- ``final_correction.json``
- artifact paths for uploaded media and generated outputs

What this phase is for
----------------------

This phase is not yet the runtime migration. It is for:

- validating the schema against real jobs
- discovering missing columns or weak table boundaries
- testing import logic for jobs, rounds, finals, and artifact indexing
- building confidence before replacing any file-backed runtime metadata path

Initial success conditions
--------------------------

The first phase is successful when all of the following are true:

1. Schema bootstrap works
   - PostgreSQL tables can be created from the current SQLAlchemy models.

2. Real jobs import cleanly
   - legacy jobs under ``server_data/jobs`` import without fatal errors.

3. Imported counts match filesystem reality
   - job count in PostgreSQL matches imported job directories
   - round count matches ``rounds/*`` directories
   - recording/image counts match section metadata files
   - final/correction counts match the archived files on disk

4. Archived snapshots are queryable
   - ``final.json`` and ``final_correction.json`` land in the database as
     retained snapshots.

5. Artifact indexing is usable
   - uploaded audio, transcript text, uploaded images, report images, PDFs,
     DOCX, and GeoJSON are represented as artifact path records.

6. No runtime behavior changes
   - the live server still runs from the filesystem-backed metadata path while
     the importer is being developed.

Recommended verification queries
--------------------------------

After import, verify:

- jobs by status
- archived jobs with finals
- jobs with correction snapshots
- rounds per job
- recordings per section
- artifacts per job/final/round
- job number uniqueness

Next phase after success
------------------------

Once the importer and schema are stable, begin replacing runtime metadata areas
incrementally:

1. device auth and tokens
2. job metadata and assignments
3. round metadata and manifests
4. media metadata
5. final and correction metadata
