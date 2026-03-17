Legacy Import Validation 2026-03-14
==================================

Purpose
-------

This report captures the first PostgreSQL import run against legacy job data.
It is a historical validation note for the import path, not a description of
the current runtime authority model.

Environment
-----------

- database: ``traq_demo``
- role: ``traq_app``
- driver: ``psycopg 3.2.9``
- importer: ``tools/import_legacy_jobs.py``

Import command used
-------------------

::

   TRAQ_DATABASE_URL='postgresql+psycopg://traq_app:change-this-password@127.0.0.1:5432/traq_demo' \
   /home/roger/anaconda3/envs/traq-demo-server/bin/python tools/import_legacy_jobs.py --init-schema

Importer result
---------------

::

   {
     "jobs": 7,
     "rounds": 18,
     "recordings": 96,
     "images": 14,
     "finals": 8,
     "artifacts": 250,
     "skipped": [
       "<legacy storage root>/jobs/job_1"
     ]
   }

Observed filesystem reality
---------------------------

Job directories under the legacy storage root: ``9``

Breakdown:
- ``7`` jobs with ``job_record.json``
- ``6`` jobs with ``final.json``
- ``3`` jobs with ``final_correction.json``
- ``1`` job directory (``job_1``) has ``final.json`` but no ``job_record.json``

What imported successfully
--------------------------

Jobs
^^^^

Imported jobs in PostgreSQL:

- ``J0001`` -> ``job_2c5b75bdbd35`` -> ``draft``
- ``J0002`` -> ``job_45936377e1f3`` -> ``review_returned``
- ``J0003`` -> ``job_ea452ac859b5`` -> ``archived``
- ``J0004`` -> ``job_e2d40483cd58`` -> ``archived``
- ``J0005`` -> ``job_b46cf3952931`` -> ``archived``
- ``J0006`` -> ``job_c9995ac6e368`` -> ``archived``
- ``J0007`` -> ``job_dd80fca1357a`` -> ``archived``

Counts
^^^^^^

- jobs: ``7``
- archived jobs: ``5``
- rounds: ``18``
- recordings: ``96``
- images: ``14``
- finals: ``8``
  - ``5`` final
  - ``3`` correction

Artifacts indexed
^^^^^^^^^^^^^^^^^

Artifact counts by kind:

- ``audio``: ``96``
- ``transcript_txt``: ``96``
- ``image``: ``28``
- ``review_json``: ``18``
- ``final_json``: ``8``
- ``final_pdf``: ``8``
- ``report_pdf``: ``8``
- ``report_docx``: ``3``
- ``geojson``: ``8``

Per-job working media counts
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

- ``J0001`` -> recordings ``0``, images ``0``
- ``J0002`` -> recordings ``1``, images ``0``
- ``J0003`` -> recordings ``21``, images ``4``
- ``J0004`` -> recordings ``16``, images ``4``
- ``J0005`` -> recordings ``17``, images ``3``
- ``J0006`` -> recordings ``24``, images ``0``
- ``J0007`` -> recordings ``17``, images ``3``

Important findings
------------------

1. Final-only legacy job exists
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

``job_1`` was skipped because it has ``final.json`` but no ``job_record.json``.
The importer currently requires ``job_record.json`` to seed a ``jobs`` row.

Consequence:
- the importer is not yet robust for older archived-only job directories
- we need a fallback job import path based on ``final.json`` alone

2. Round history imports cleanly enough to test the schema
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The existing round/section/media structure maps naturally into:
- ``job_rounds``
- ``round_recordings``
- ``round_images``
- ``artifacts``

This validates the decision to retain round/media tables even though rounds may
later be pruned after archival.

3. Job metadata and archived final metadata can disagree
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Two imported jobs show disagreement between ``job_record.json`` and the archived
final snapshot:

- ``J0004``
  - ``latest_round_id`` = ``round_5``
  - final snapshot ``round_id`` = ``round_2``

- ``J0006``
  - ``latest_round_id`` = ``round_2``
  - final snapshot ``round_id`` = ``round_15``

Consequence:
- final/correction snapshot data must be treated as authoritative for archived
  output provenance
- ``job_record.json`` should not be assumed to be the final truth for archived
  jobs

4. Artifact indexing is already useful
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The current artifact model is sufficient to reference:
- uploaded recordings
- transcript text files
- uploaded images
- report images
- review payloads
- final JSON
- final PDFs
- report PDFs
- report DOCX
- GeoJSON

This is enough to support further query/report work without changing runtime.

Assessment against initial success conditions
---------------------------------------------

Met
^^^

- schema bootstrap works
- real jobs import without fatal schema errors
- archived snapshots are queryable
- artifact indexing is usable
- runtime server behavior remains unchanged

Partially met
^^^^^^^^^^^^^

- imported counts match filesystem reality

Reason:
- the importer skipped one legacy archived-only job because it lacked
  ``job_record.json``
- the importer still needs a fallback path for final-only job directories

Recommended next changes
------------------------

1. Add fallback import for archived-only jobs with ``final.json`` but no
   ``job_record.json``.
2. Add a post-import validation script with explicit comparisons to filesystem
   counts by job.
3. Begin using imported data to design runtime read/write services, starting
   with device/auth and job metadata.
