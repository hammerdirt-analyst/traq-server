# AGENT

## Process rule

We lost substantial time because of unverified assumptions.
That should be remembered as a process failure.

## Required operating standard

Do not assume. Verify.

Before acting on infrastructure, deployment, data, or operator workflow changes, verify the current state explicitly.

## Minimum verification checklist

Verify each layer directly:
- object existence
- configuration actually applied
- runtime contract
- operator path
- deployed state

## Examples

Do not assume:
- a Cloud SQL instance implies the application database exists
- a local admin workflow implies a remote admin workflow exists
- a secret value is live in the current revision
- a UI field shown once means the deployed revision actually has that setting
- a service and a job share networking just because they share an image

## Repo rule

For this repo, progress should follow this order:
1. verify what exists
2. verify what is wired
3. verify what is live
4. then change it

## Python environment rule

For all Python work in `server/`, use `uv`.

- run tests from the `server/` directory
- prefer `uv run ...` over direct `python ...`
- do not assume the global Python environment matches the project environment

Examples:

- `env UV_CACHE_DIR=/tmp/uv-cache uv run python -m unittest tests.test_export_sync_service`
- `env UV_CACHE_DIR=/tmp/uv-cache uv run python -m unittest tests.test_api_routers`

## Failure framing

When something goes wrong, first ask:
- what are we assuming?
- which of those assumptions have been verified?
- which layer is proven, and which layer is only inferred?

If the answer is unclear, stop and verify before continuing.
