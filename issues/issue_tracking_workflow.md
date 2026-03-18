# Issue Tracking Workflow

## Purpose

This file is the temporary coordination point for unresolved and resolved issues
while the server repo is still stabilizing and before a stricter remote issue
workflow is chosen.

Use this file to:
- register new issues when they are discovered
- link supporting notes already present under `issues/`
- record frontend replies or follow-up references
- mark when an issue is resolved and by which commit

This avoids fragmented issue handling while keeping detailed notes available.

## Working Rules

1. Add a short issue entry here when a problem is found.
2. If a deeper note is needed, create a dedicated markdown file in `issues/` and
   link it from the entry.
3. If frontend review/comment is needed, add the client-facing note path and any
   reply path to the same entry.
4. When resolved, do not delete the entry.
   - move its status to `resolved`
   - add the fixing commit
   - add any follow-up or remaining caveat
5. If an issue becomes obsolete, mark it `closed-no-action` with a reason.

## Status Values

- `open`
- `in_progress`
- `blocked`
- `resolved`
- `closed-no-action`

## Issue Register

| ID | Status | Area | Summary | Notes | Frontend/Reply | Fixed By | Follow-up |
| --- | --- | --- | --- | --- | --- | --- | --- |
| S-001 | open | assignment/lifecycle | Archived jobs can still auto-claim after local restore if unassigned | `issues/archived_job_auto_claim_too_permissive.md` | — | — | Tighten `_assert_job_assignment()` for archived jobs |
| S-002 | open | deployment | GCP deployment readiness baseline and remaining blockers | `issues/gcp_deployment_readiness_spec.md`, `issues/gcp_deployment_audit.md`, `issues/gcp_services_pricing_list.md` | — | — | Use this row until remote issue tracker is chosen |
| S-003 | open | admin-cli/artifacts | `artifact fetch --kind final-json` requires archived final payloads in DB and does not support file-only historical finals | — | — | — | Keep current DB-first behavior; document that older file-only finals may still support PDF fetch but not `final-json` |

## Coordination Notes

- Use one row per logical issue.
- Prefer updating the existing row instead of creating duplicates.
- If a UI/client reply exists, link both the original issue note and the reply.
- If a server issue depends on a client change, note that in `Follow-up`.

## Remote Migration Later

When the remote issue workflow is chosen, this document can be used as the
source list to create remote issues in a controlled pass.
