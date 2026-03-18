"""Archive retention policy for final and correction data.

Authors: Roger Erismann (https://hammerdirt.solutions), OpenAI Codex

This module defines what must be retained after a job is archived and what can
be pruned from the working-state tables and artifact store.

Policy baseline:
- keep final and correction transcript outputs
- drop raw audio after archive
- preserve immutable original final
- preserve the current correction snapshot separately from the original final
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from ..db_models import Artifact, ArtifactKind, Job, JobFinal, JobRound


RETAINED_FINAL_KINDS = {
    ArtifactKind.final_json,
    ArtifactKind.final_pdf,
    ArtifactKind.report_pdf,
    ArtifactKind.report_docx,
    ArtifactKind.geojson,
    ArtifactKind.image,
    ArtifactKind.transcript_txt,
}

PRUNABLE_WORKING_KINDS = {
    ArtifactKind.audio,
    ArtifactKind.review_json,
}


@dataclass(frozen=True)
class ArchiveRetentionDecision:
    """Retention plan for one archived job.

    The decision is descriptive only. It does not delete anything. Runtime code
    can use it later to implement pruning once the database migration is live.
    """

    job_id: str
    final_round_id: str | None
    correction_round_id: str | None
    retained_round_ids: tuple[str, ...]
    prunable_round_ids: tuple[str, ...]
    retained_artifact_paths: tuple[str, ...] = field(default_factory=tuple)
    prunable_artifact_paths: tuple[str, ...] = field(default_factory=tuple)


def _round_ids_to_keep(finals: Iterable[JobFinal]) -> tuple[str, ...]:
    """Collect unique round ids referenced by retained final snapshots."""
    keep: list[str] = []
    for row in finals:
        if row.round_id and row.round_id not in keep:
            keep.append(row.round_id)
    return tuple(keep)


def _is_final_artifact_retained(artifact: Artifact) -> bool:
    """Return whether a final snapshot artifact must survive archiving."""
    if artifact.kind in RETAINED_FINAL_KINDS:
        return True
    if artifact.kind == ArtifactKind.audio:
        return False
    if artifact.kind == ArtifactKind.review_json:
        return False
    return False


def _is_round_artifact_prunable(artifact: Artifact, kept_round_ids: set[str]) -> bool:
    """Return whether a round-scoped artifact is safe to prune after archive."""
    round_row = artifact.round
    if round_row is None:
        return False
    if round_row.round_id in kept_round_ids:
        if artifact.kind == ArtifactKind.audio:
            return True
        return False
    return artifact.kind in PRUNABLE_WORKING_KINDS or artifact.kind == ArtifactKind.audio


def build_archive_retention_decision(job: Job) -> ArchiveRetentionDecision:
    """Return retained and prunable data for one archived job.

    Retention rules:
    - final and correction rounds are retained as transcript/report provenance
    - raw audio is prunable even for retained final/correction rounds
    - review JSON is prunable once archived
    - non-final working rounds are prune candidates
    """

    final_row = next((row for row in job.finals if row.kind == "final"), None)
    correction_row = next((row for row in job.finals if row.kind == "correction"), None)
    kept_round_ids = set(_round_ids_to_keep(job.finals))

    retained_round_ids = tuple(
        dict.fromkeys(
            round_id
            for round_id in [
                final_row.round_id if final_row else None,
                correction_row.round_id if correction_row else None,
            ]
            if round_id
        )
    )
    prunable_round_ids = tuple(
        dict.fromkeys(
            row.round_id
            for row in sorted(job.rounds, key=lambda item: item.round_id)
            if row.round_id not in kept_round_ids
        )
    )

    retained_artifacts: list[str] = []
    prunable_artifacts: list[str] = []

    for final in job.finals:
        for artifact in final.artifacts:
            if _is_final_artifact_retained(artifact):
                retained_artifacts.append(artifact.path)
            else:
                prunable_artifacts.append(artifact.path)

    for artifact in job.artifacts:
        if _is_round_artifact_prunable(artifact, kept_round_ids):
            prunable_artifacts.append(artifact.path)
        elif artifact.round and artifact.round.round_id in kept_round_ids and artifact.kind == ArtifactKind.transcript_txt:
            retained_artifacts.append(artifact.path)

    return ArchiveRetentionDecision(
        job_id=job.job_id,
        final_round_id=final_row.round_id if final_row else None,
        correction_round_id=correction_row.round_id if correction_row else None,
        retained_round_ids=retained_round_ids,
        prunable_round_ids=prunable_round_ids,
        retained_artifact_paths=tuple(sorted(dict.fromkeys(retained_artifacts))),
        prunable_artifact_paths=tuple(sorted(dict.fromkeys(prunable_artifacts))),
    )


def path_should_be_deleted(path: str) -> bool:
    """Return whether a retained archive should delete the given artifact path.

    This is a path-level helper for scripts that operate on filesystem artifacts.
    It intentionally biases toward safety: only raw audio and review payloads are
    marked as directly deletable by suffix.
    """

    candidate = Path(path)
    name = candidate.name
    return name.endswith(".wav") or name == "review.json"
