# Staged Jobs Demo

This directory is a stable local staging root that mirrors the phase-1 admin-side
staging contract for completed jobs.

Intended downstream use:

- the admin/server side owns this directory shape
- reporter-client reads `manifest.json` files and the local files they reference
- all manifest paths are relative to the manifest file

Suggested reporter-client configuration variable:

```env
REPORTER_STAGE_ROOT=/home/roger/projects/codex_trial/agent_client/server/testdata/staged_jobs
```

Layout:

```text
staged_jobs/
  state/
    export_cursor.json
  jobs/
    J0001/
      manifest.json
      final.json
      final.geojson
      traq_page1.pdf
      images/
        report_1.svg
        report_2.svg
```
