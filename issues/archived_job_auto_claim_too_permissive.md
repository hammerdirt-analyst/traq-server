# Archived job auto-claim is too permissive

## Problem

The current server assignment check allows implicit auto-claim of any existing unassigned job.

That includes jobs whose server status is `ARCHIVED`.

In practice, this means a client can:
- restore a previously finalized local job backup
- submit again without explicit reassignment
- have the server auto-claim the archived job
- process the request as correction-mode finalization

This is technically working today, but the assignment rule is too permissive.

## Current behavior

Relevant path:
- `app/main.py`
- `_assert_job_assignment(job_id, auth)`

Current logic:
- if no assignment exists
- and the job exists in memory or DB
- the server auto-assigns it to the caller device with `assigned_by="auto"`

This applies even when the job is already archived.

## Why this is a problem

Archived jobs are supposed to be completed work.

Allowing implicit auto-claim means:
- completed jobs can be reopened by local restore alone
- archived/unassigned is not a strong lifecycle boundary
- correction-mode can be entered without explicit admin intent

That is too loose for the long-term cloud/server contract.

## Desired behavior

Auto-claim should be limited to active work only.

Proposed rule:
- if a job is unassigned and not archived, auto-claim may still be allowed
- if a job status is `ARCHIVED`, auto-claim must be rejected
- reopening an archived job should require explicit server-side/admin action

## Accepted current state

For now, restored finalized local jobs can still submit again and the server will:
- auto-claim the job
- treat finalization as correction-mode
- regenerate correction artifacts
- unassign the job again

This is acceptable temporarily, but should not remain the long-term rule.

## Follow-up

When this is addressed:
- tighten `_assert_job_assignment()`
- reject implicit auto-claim for archived jobs
- add tests covering archived/unassigned restore attempts
