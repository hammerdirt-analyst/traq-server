# Server Repo Hardening Checklist

## Objective

Harden `server/` so it operates cleanly as its own repo.

This checklist starts after runtime storage migration is validated:

- DB is authoritative for runtime operational state
- filesystem is limited to artifact bytes and debug/export outputs
- live device flow has been tested successfully

When this checklist is complete, the document can move to `server/issues/resolved/`.

## Scope

This phase is about repo quality and standalone operation, not storage migration.

Goals:

- standalone repo usability
- internal documentation only
- uv-first developer workflow
- repo-local storage defaults
- removal of monorepo assumptions

## Checklist

### 1. Packaging Boundary

- add `pyproject.toml`
- define package metadata for the standalone server repo
- define entrypoints for:
  - API server
  - admin CLI

Acceptance:

- the repo can be installed/run without depending on parent-repo layout

Status:

- complete
- added `pyproject.toml`
- added console scripts:
  - `traq-server`
  - `traq-admin`

### 2. Import Cleanup

- remove monorepo assumptions such as `server.app...`
- make imports work from inside the standalone repo
- update tests and scripts to match the standalone import model

Acceptance:

- tests run from inside `server/`
- CLI and API imports resolve without parent-repo help

Status:

- complete
- tests and repo-local docs now import from `app...` and `tools...`
- standalone test execution verified from inside `server/`

### 3. UV-First Bootstrap

- document `uv` environment bootstrap
- document `uv sync` / `uv run` workflow
- document PostgreSQL requirement
- document required env vars
- keep conda optional only where local system tooling requires it

Acceptance:

- a developer can stand up the repo with `uv` as the primary workflow

Status:

- complete
- `uv sync` works in the standalone repo
- `uv run traq-server --help` and `uv run traq-admin --help` both work

### 4. Storage Defaults

- change default storage root to a repo-local path
  - e.g. `./local_data` or `./var`
- keep local storage ignored in git
- remove dependency on `../server_data` as the default path

Acceptance:

- a fresh standalone repo uses a local storage root by default

Status:

- complete
- default storage root now points to repo-local `./local_data`

### 5. Internal Docs Only

- keep documentation self-contained within `server/`
- replace references to external docs paths
- make README command examples repo-local

Acceptance:

- a reader inside the standalone repo does not need sibling-repo docs

Status:

- complete
- top-level, app, and `docs/` references now use repo-local commands and repo-local paths

### 6. Generated File Hygiene

- remove absolute machine-specific paths from committed generated artifacts
- especially inspect:
  - `app/traq_2_schema/traq_full_map.json`

Acceptance:

- no committed generated file contains local machine path leakage

Status:

- complete
- `app/traq_2_schema/traq_full_map.json` now stores repo-relative source paths
- machine-specific path leakage removed from committed docs and generated files

### 7. Runtime vs Export Boundary

- document clearly:
  - DB-backed runtime authority
  - local artifact storage
  - export/debug files are non-authoritative

Acceptance:

- the storage boundary is explicit and easy to verify

Status:

- complete
- runtime/export boundary documented in `docs/runtime_export_boundary.rst`
- top-level and app docs now state that exported JSON files are non-authoritative

### 8. Git Hygiene

- review `.gitignore`
- ensure local artifacts, caches, logs, and env files stay out of git
- keep repo-local runtime data untracked

Acceptance:

- local runtime usage does not pollute the repo

Status:

- complete
- `.venv/` and `*.egg-info/` ignored
- generated `traq_server.egg-info/` removed from version control
- `uv.lock` retained as the repo-managed dependency lockfile

### 9. Validation

- run tests from the standalone repo context
- start the API from inside `server/`
- run the admin CLI from inside `server/`
- verify one end-to-end device flow still works

Acceptance:

- the standalone repo behaves correctly without relying on parent-repo behavior

Status:

- complete
- `uv run traq-server --help` works
- `uv run traq-admin --help` works
- standalone test run from inside `server/` passes:
  - `uv run python -m unittest tests.test_admin_cli tests.test_tree_identity_api tests.test_db_store`

## Recommended Order

Work this checklist in the following order:

1. storage defaults
2. internal docs
3. packaging boundary
4. import cleanup
5. generated file hygiene
6. runtime/export documentation
7. git hygiene
8. validation

## Exit Condition

Move this document to `server/issues/resolved/` when:

- the checklist items are complete
- the standalone repo works cleanly from inside `server/`
- the result has been validated against the live workflow
