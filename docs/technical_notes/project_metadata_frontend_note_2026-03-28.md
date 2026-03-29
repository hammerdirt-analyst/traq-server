# Project Metadata Feature Note For Frontend

Purpose
-------

This note records the current feature request for first-class project metadata
and the intended server-side implementation direction before coding begins.

Feature request
---------------

We want each job to carry a project identifier as first-class metadata.

Operational goal:

- group jobs by project consistently across server, CLI, staging, and reporter
- stop treating project as manual or reporter-only metadata
- make project assignment part of the authoritative job record

Current implementation status
-----------------------------

Project metadata is not yet first-class in the server.

Current state:

- staged/reporter bundles can carry manual ``project`` and ``project_slug``
- that metadata is currently provisional and not server-authoritative
- there is no canonical server-managed project list yet
- there is no job-level project assignment flow yet
- there is no frontend project selection contract yet

Intended server-side implementation
----------------------------------

The intended implementation direction is:

1. server-managed project list

   - projects come from the server, not free text from clients
   - each project should have a stable identifier and slug

2. job-level project assignment

   - jobs store project metadata as part of authoritative server state
   - admin CLI can assign or update the project on a job

3. downstream propagation

   - inspect/export/staging responses include project metadata
   - staged reporter manifests carry the server-owned project fields

4. frontend selection from server-provided values only

   - the UI should not invent arbitrary project strings
   - selection should be constrained to values returned by the server

Proposed backend contract shape
-------------------------------

Likely server-facing project fields:

- ``project_id``
- ``project``
- ``project_slug``

Likely job-facing shape once implemented:

.. code-block:: json

   {
     "job_id": "job_...",
     "job_number": "J0003",
     "project_id": "project_briarwood",
     "project": "Briarwood",
     "project_slug": "briarwood"
   }

Frontend comments requested
---------------------------

Before implementation, frontend feedback should confirm:

1. selection UX

   - does the UI need a required project selection or optional selection?
   - at what stage should project be assigned: job creation, edit, or both?

2. display needs

   - does the UI need only display name and slug?
   - does it need a separate stable ``project_id`` exposed to the client?

3. filtering/grouping behavior

   - does the UI expect project-based filtering in job lists immediately?
   - or is assignment/display enough for the first iteration?

4. empty-state behavior

   - how should the UI behave when no projects exist yet?
   - is a null/unassigned project valid in the first version?

Current recommendation to frontend
----------------------------------

Treat this as a server-owned metadata feature, not a presentation feature.

That means:

- project values should come from the backend
- the UI should select from server-provided choices
- the UI should not rely on reporter/staging conventions as the source of truth

Non-goals for the first implementation
--------------------------------------

The first implementation does not need to include:

- complex project permissions
- nested project hierarchies
- reporter-side project authoring
- free-text project entry from the device/UI

Summary
-------

This feature is intended to make project grouping authoritative and consistent
across the stack. Frontend feedback should focus on selection timing, null
handling, and whether display/filtering requirements extend beyond simple
assignment in the first version.
