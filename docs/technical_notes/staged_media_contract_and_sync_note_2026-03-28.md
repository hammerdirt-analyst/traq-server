# Technical Note: Staged Media Contract And Manual Sync

## Purpose

This note defines the server/admin-side contract for staging completed job
artifacts into a stable local directory tree for downstream reporter use.

The immediate goal is a manual CLI command, not a scheduler-first workflow.

## Design Center

The handoff boundary is a staged per-job bundle, not loose downloaded files.

The reporter client should not speak to server export/admin endpoints directly.
It should consume only staged local bundles created by the admin-side sync
tooling.

## Phase 1 Scope

Phase 1 provides:

- a manual admin CLI sync command
- incremental sync using a local cursor file
- a stable local staging tree
- a canonical `manifest.json` per completed job
- fetch of the required completed-job artifact bundle

Phase 1 does not require:

- cron
- systemd timers
- background scheduling

## Required Completed-Job Bundle

For each completed job, the staging tool should materialize:

- `final.json`
- `final.geojson`
- `traq_page1.pdf`
- `images/` containing all completed report images
- `manifest.json`

Optional artifacts may be added later, but those are the phase 1 minimum.

## Recommended Local Layout

```text
staging/
  state/
    export_cursor.json
  jobs/
    J0003/
      manifest.json
      final.json
      final.geojson
      traq_page1.pdf
      images/
        report_1.jpg
        report_2.jpg
        report_3.jpg
```

This is the canonical staging layout for phase 1.

`job_number` is the top-level local bundle key because it is operator-facing and
easy to inspect. The manifest must still retain `job_id` and other canonical
server identities.

## Path Policy

All paths written into `manifest.json` must be relative to the manifest file.

Do not write absolute machine-specific paths into the staged manifest.

Examples:

- `./final.json`
- `./final.geojson`
- `./traq_page1.pdf`
- `./images/report_1.jpg`

This keeps the staged bundle portable and makes downstream tools simpler.

## Manifest Contract

Each staged completed-job bundle must include a `manifest.json`.

Recommended phase 1 shape:

```json
{
  "job_id": "job_b62ffe12501c",
  "job_number": "J0003",
  "project_id": null,
  "project": null,
  "project_slug": null,
  "client_revision_id": "ea4941e6-ca8c-464f-8370-ad47bd75c818",
  "archived_at": "2026-03-28T12:00:00Z",
  "staged_at": "2026-03-28T12:15:00Z",
  "artifacts": {
    "final_json": "./final.json",
    "final_geojson": "./final.geojson",
    "traq_pdf": "./traq_page1.pdf"
  },
  "images": [
    {
      "image_ref": "report_1",
      "variant": "report",
      "source_path": "./images/report_1.jpg",
      "caption": "The tree: east-facing view"
    }
  ]
}
```

## Manifest Field Rules

Required fields:

- `job_id`
- `job_number`
- `project_id`
- `project`
- `project_slug`
- `client_revision_id` when available
- `archived_at` when available
- `staged_at`
- `artifacts.final_json`
- `artifacts.final_geojson`
- `images`

Required field rule for project metadata:

- `project_id`, `project`, and `project_slug` must be present in the manifest
- unassigned jobs may set those values to `null`
- assigned jobs must carry the authoritative server values

Recommended fields:

- `artifacts.traq_pdf`

Image record minimum reporter-facing contract:

- `source_path`
- `caption`

But the staged manifest should also retain:

- `image_ref`
- `variant`

Those fields are needed for refresh/debug and should not be discarded upstream.

## Artifact Fetch Rules

For each completed or changed completed job, the sync command should fetch:

1. `artifact fetch --kind final-json`
2. `artifact fetch --kind geo-json`
3. `artifact fetch --kind traq-pdf`
4. `export images-fetch-all --variant report`

The sync command should normalize the fetched outputs into the canonical staged
layout and not expose the raw fetch directory structure as the final contract.

## Sync State

The sync tool must keep local state in:

```text
staging/state/export_cursor.json
```

Phase 1 behavior:

- read prior cursor if present
- call `export changes`
- process relevant completed jobs
- update cursor only after successful write of local staged outputs

## Idempotency Rules

The sync command must be safe to rerun.

Expected behavior:

- existing staged job bundles may be updated in place
- unchanged jobs should not be rewritten unnecessarily
- partial failures should not corrupt already-staged bundles
- manifest should reflect only successfully staged local outputs

## Failure Handling

Per-job failures should not abort the entire sync unless configured to do so.

Phase 1 summary output should report:

- jobs seen
- jobs staged
- jobs skipped
- jobs failed
- artifacts fetched
- artifacts failed
- resulting cursor

## Relationship To Reporter Client

Reporter client consumes only:

- `manifest.json`
- local files referenced by that manifest

Reporter client should not need to know:

- server endpoints
- artifact kinds
- export cursor logic
- download variants

## Relationship To Server Project Metadata

Project metadata is now first-class on the server.

Staged manifests should therefore carry the authoritative resolved project
fields from job metadata:

- `project_id`
- `project`
- `project_slug`

If a job is unassigned, those manifest fields may be `null`.

## Proposed CLI Direction

Recommended phase 1 command shape:

```text
uv run traq-admin <local|cloud> stage sync
```

Possible future flags:

- `--root <staging_dir>`
- `--job <job_ref>` for targeted sync
- `--cursor <override>`
- `--full-refresh`

This note does not lock the exact parser signature, but it does lock the output
contract.

## Bottom Line

The implementation target is:

- a manual admin-side sync command
- a stable local completed-job bundle
- a canonical relative-path manifest
- a clean offline handoff boundary for the reporter client
