# Branch Technical Note: Completed Export Image Resolution Bugfix

## Why this branch exists

Export image download for archived jobs can fail with `404 Report image not found` even when the image exists in artifact storage.

Root cause: archived image resolution relied on transient/local `report_images[].path` values in finalized payloads instead of stable artifact keys.

## Intentions

1. Resolve archived `report_*` images via stable `stored_path` artifact keys when available.
2. Keep backward compatibility by falling back to legacy `path` values.
3. Persist `stored_path` in report image payload assembly to prevent future drift.
4. Add regression tests that reproduce and lock this behavior.
