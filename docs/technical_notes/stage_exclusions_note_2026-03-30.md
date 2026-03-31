# Technical Note: Stage Exclusions

## Purpose

This branch adds a local staging exclusion mechanism so operator workflows can
remove jobs from the reporter handoff flow without deleting or mutating server
state.

## Why This Exists

Completed jobs may be valid on the server but still undesirable in the local
staged reporter flow.

Examples:

- sparse or invalid sample jobs
- archived jobs that should be retained upstream but hidden downstream
- temporary local curation of the reporter bundle set

Deleting bundle directories by hand is not sufficient because a later `stage
sync` can re-stage the same jobs from the export feed.

## Design

Exclusions are local-only and root-specific.

Each staging root keeps a plain JSON file at:

```text
staging/state/excluded_jobs.json
```

Proposed shape:

```json
{
  "jobs": ["J0001", "J0007"],
  "updated_at": "2026-03-30T22:15:00Z"
}
```

The file is intentionally simple so operators can inspect and edit it manually.

## CLI Surface

The local stage command group should support:

- `stage exclusions --root <dir>`
- `stage exclude --job <job_number> --root <dir>`
- `stage include --job <job_number> --root <dir>`

Behavior:

- `stage exclude` adds the job number to the exclusion file and removes the
  local staged bundle if present
- `stage include` removes the job number from the exclusion file
- `stage exclusions` prints the current file state

## Sync Behavior

`stage sync` should skip any completed job whose `job_number` is present in the
local exclusion file.

This skip is local-only. It must not affect server export state, job status, or
archived artifacts.

## Bottom Line

The exclusion mechanism is an operator-side curation layer for the reporter
handoff root. It belongs in staging state, not in server archival state.
