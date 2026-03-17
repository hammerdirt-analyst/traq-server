# Archived Job Restore Behavior

## Context

During device testing, imported archived jobs were staged back to devices as `REVIEW_RETURNED`.

This was intentional for migration testing:

- the device needed editable working state
- the user needed to resume, edit, and resubmit
- archived jobs were therefore surfaced as active working jobs

## What Changed

An archived imported job can now appear on device as:

- `status = REVIEW_RETURNED`
- `latest_round_status = REVIEW_RETURNED`

That means the device sees a restorable working job, not a read-only archived record.

## Artifact Implications

This only works if the required artifact files still exist locally.

Required artifact classes:

- uploaded audio files
- uploaded image files
- generated report-image files where needed
- final output targets can be regenerated from current runtime state plus artifact files

Operational rule:

- runtime JSON state now comes from the DB
- artifact bytes still come from local filesystem storage

## Risk

If a staged archived job is restored to device and the underlying artifact files are missing, then:

- review/edit may be incomplete
- final regeneration may fail
- report letter / TRAQ form regeneration may be incomplete

## Follow-up

We need an explicit test/spec for this case:

1. assign a previously archived imported job restored as `REVIEW_RETURNED`
2. edit it on device
3. submit it
4. submit final again
5. verify:
   - transcript availability
   - form output
   - report letter output
   - artifact expectations are satisfied

This is not a blocker for the repo split, but it is a runtime behavior that needs to be tracked explicitly.
