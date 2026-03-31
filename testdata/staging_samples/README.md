# Staging Root

This directory is the canonical local staging root for completed-job bundles.

Intended downstream use:

- the admin/server side owns this directory shape
- reporter-client reads `manifest.json` files and the local files they reference
- all manifest paths are relative to the manifest file

Suggested reporter-client configuration variable:

```env
REPORTER_STAGE_ROOT=/home/roger/projects/codex_trial/agent_client/server/staging
```

Layout:

```text
staging/
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

Notes:

- this root currently contains sample data matching the staged bundle contract
- `J0003` is populated from real-style exported artifacts
- the remaining sample jobs are synthetic but contract-correct fixtures
