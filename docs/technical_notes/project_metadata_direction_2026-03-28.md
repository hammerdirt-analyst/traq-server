# Technical Note: Project Metadata Direction

## Purpose

This note records the current architectural direction for project grouping so it
is not lost while media staging and reporter integration continue.

## Recommendation

Project grouping should be implemented as first-class server job metadata, not
as a reporter-only convention and not as a free-text field that drifts across
tools.

If project grouping matters operationally, the server must own it.

## Why This Matters

Project grouping affects more than reporter output. It is relevant to:

- admin CLI workflows
- job organization
- export/staging manifests
- downstream reporting
- future filtering, dashboards, and sync behavior

Because of that, project should be modeled at the server level and flow
downstream through existing contracts.

## Recommended Model

The preferred shape is:

- server-managed project list
- canonical project identity on the server
- jobs reference project by stable id
- server returns resolved project metadata with the job

Recommended fields:

- `project_id`
- `project`
- `project_slug`

Jobs should store the canonical project reference, not only a display string.

## Input And Mutation Rules

The project value should not be arbitrary free text from clients.

Recommended rules:

1. The server owns the list of valid projects.
2. UI selection should come only from the server-provided list.
3. Admin CLI should be able to assign or update a project's value on a job.
4. Device/client submission may carry a project selection only if that value
   came from the server list.

This avoids spelling drift, duplicate project names, and unstable slug
generation.

## Why Not A Plain String Field

A plain string field on the job is the wrong long-term model.

It would create:

- duplicate or near-duplicate project names
- unstable slugs
- merge/cleanup overhead later
- ambiguity in staging and reporting

If project is important enough to exist, it should exist as structured metadata.

## Relationship To Staging And Reporter Work

This project-metadata feature should not block the staging/media contract work.

The staging manifest can carry `project` and `project_slug` as optional fields
for now. Once project metadata is implemented on the server, those fields can
become authoritative.

That lets upstream staging proceed now without inventing temporary grouping
rules in the reporter client.

## Proposed Future Scope

This should become a separate feature with its own branch and note.

Expected future work:

- project model on the server
- admin CLI project management commands
- job update/assignment support for project metadata
- server-provided project list for UI selection
- export/staging manifest inclusion of project metadata

## Bottom Line

Project grouping should be treated as foundational metadata owned by the server.

It should not be solved as a loose reporter-side convention, and it should not
be reduced to a free-text string on jobs.
