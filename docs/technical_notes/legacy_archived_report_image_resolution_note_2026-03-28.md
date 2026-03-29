# Legacy Archived Report Image Resolution

This branch exists to fix one narrow backward-compatibility gap in export image
fetch for archived jobs.

Problem:

- older archived finals stored `report_images[*].path` as a local materialized
  cache path under `artifact_cache`
- those paths are not stable across runtime environments
- `export image-fetch` and `export images-fetch-all` therefore fail for legacy
  archived jobs even when the underlying report-image bytes still exist in
  artifact storage

Intended fix:

- keep `stored_path` as the preferred canonical lookup
- when `stored_path` is missing, reconstruct the artifact key only for the exact
  legacy cached job-photo report-image path shape
- materialize that reconstructed key through the artifact store
- do not add fuzzy matching or basename-only guessing

Acceptance criteria:

- archived jobs with only legacy cached `path` values can fetch report images
- malformed or non-matching legacy paths still fail cleanly
- current `stored_path`-based behavior remains unchanged
