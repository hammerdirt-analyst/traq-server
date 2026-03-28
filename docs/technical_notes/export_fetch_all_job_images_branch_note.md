# Branch Technical Note: Export Fetch All Job Images

## Why this branch exists

This branch exists to support downstream reporting workflows that run on a separate machine and need all job images as local files.

Current CLI behavior supports fetching one image at a time (`export image-fetch`). Final payloads may include URLs, but downstream reporters need a deterministic local export command that materializes all images for a job.

## Intended feature

Add a CLI command to fetch all images for one job in a single operation.

Proposed command:

- `uv run traq-admin <local|cloud> export images-fetch-all --job <job_ref> [--variant auto|original|report] [--output <dir>]`

## Contract expectations

- Accept `--job` as `job_id` or `job_number` (CLI resolves to canonical `job_id`).
- Resolve image refs from export sync payload (completed + in-process rows when relevant).
- Download each image via existing export image endpoint.
- Write outputs under deterministic paths (default under `./exports/<job_number>/images/`).
- Return JSON summary: total refs, downloaded, skipped duplicates, failed refs with reasons.

## Out of scope

- Changing final payload schema.
- Replacing existing single-image command.
- New server endpoint unless reuse proves insufficient.

## Acceptance criteria

1. One command downloads all available image refs for a job.
2. Works in both local and cloud modes.
3. Handles partial failures without losing successful downloads.
4. Produces machine-readable summary output suitable for automation.
