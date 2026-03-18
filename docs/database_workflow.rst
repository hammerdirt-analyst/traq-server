Database Workflow
=================

Purpose
-------

This note describes how imported legacy data should be queried, edited, pruned,
and reconsolidated into reporting outputs as the server moves from filesystem
metadata to PostgreSQL.

Read model
----------

Use PostgreSQL as the system of record for metadata and workflow state.

Read paths should converge on:

- ``customers`` and ``billing_profiles`` for reusable operational identity data
- ``operators`` for reusable assessor identity
- ``jobs`` for current job identity and status
- ``job_rounds`` for working review history
- ``round_recordings`` and ``round_images`` for uploaded media metadata
- ``job_finals`` for archived final and correction snapshots
- ``artifacts`` for file references
- ``job_events`` for audit/history

Write model
-----------

Do not edit archived output artifacts directly.

Editing rules:

- active work updates database rows
- uploaded media files remain immutable artifacts on disk
- archived final rows are immutable
- correction rows may be overwritten as the current correction copy
- generated PDFs, DOCX, and GeoJSON are replaced by regenerating them from the
  current final/correction payload

In practice:

- metadata is edited in PostgreSQL
- artifacts are regenerated or replaced at known paths
- the database stores the authoritative payload and references the artifact files

Pruning model
-------------

Pruning should happen only after a job is archived and the final/correction
snapshots are intact.

Keep permanently:

- ``jobs``
- ``job_finals``
- ``artifacts`` for retained outputs
- ``job_events``
- any assignment/auth history needed for audit

Prune candidates after archive:

- ``job_rounds`` not referenced by the retained final/correction snapshots
- ``round_recordings`` and ``round_images`` tied only to pruned rounds
- transient manifest/review artifacts tied only to pruned rounds

The current schema keeps working rounds so pruning policy can be tested before
any deletion logic is automated.

Reporting model
---------------

The reporting structure should be driven from ``job_finals.payload``.

Why:

- archived final/correction snapshots are the legal/reporting record
- current tests already show that ``job_record.json`` and archived final lineage
  can disagree
- final/correction payloads contain the consolidated form/transcript/report data

That means:

- reporting exports should read from ``job_finals``
- customer/billing/admin lookup should read from normalized operational tables
- round tables support provenance, troubleshooting, and edit history
- they are not the long-term reporting source

Read-only query tool
--------------------

Use:

- ``tools/query_imported_jobs.py``

Current query presets:

- ``summary``
- ``archived-finals``
- ``round-mismatches``
- ``media-by-job``
- ``pruning-candidates``
- ``report-projection``
- ``normalized-entities``

These queries exist to test the schema against real imported jobs before live
runtime code is moved to PostgreSQL.
