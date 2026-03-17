"""Tests for archived final/correction retention behavior."""

from __future__ import annotations

import unittest

from app.services.archive_policy import build_archive_retention_decision, path_should_be_deleted
from app.db_models import Artifact, ArtifactKind, Job, JobFinal, JobRound, JobStatus


class ArchivePolicyTests(unittest.TestCase):
    def test_archive_policy_keeps_final_and_correction_rounds_but_prunes_audio(self) -> None:
        job = Job(job_id="job_test", job_number="J9998", status=JobStatus.archived)
        round_1 = JobRound(job=job, round_id="round_1")
        round_2 = JobRound(job=job, round_id="round_2")
        round_3 = JobRound(job=job, round_id="round_3")
        job.rounds.extend([round_1, round_2, round_3])

        final = JobFinal(job=job, kind="final", round_id="round_1", payload={"round_id": "round_1"})
        correction = JobFinal(job=job, kind="correction", round_id="round_3", payload={"round_id": "round_3"})
        job.finals.extend([final, correction])

        final.artifacts.extend(
            [
                Artifact(job=job, final=final, kind=ArtifactKind.final_json, path="/tmp/final.json"),
                Artifact(job=job, final=final, kind=ArtifactKind.final_pdf, path="/tmp/final_traq_page1.pdf"),
            ]
        )
        correction.artifacts.extend(
            [
                Artifact(job=job, final=correction, kind=ArtifactKind.final_json, path="/tmp/final_correction.json"),
                Artifact(job=job, final=correction, kind=ArtifactKind.report_pdf, path="/tmp/final_report_letter_correction.pdf"),
            ]
        )
        job.artifacts.extend(
            [
                Artifact(job=job, round=round_1, kind=ArtifactKind.transcript_txt, path="/tmp/round_1.transcript.txt"),
                Artifact(job=job, round=round_1, kind=ArtifactKind.audio, path="/tmp/round_1.wav"),
                Artifact(job=job, round=round_2, kind=ArtifactKind.transcript_txt, path="/tmp/round_2.transcript.txt"),
                Artifact(job=job, round=round_2, kind=ArtifactKind.audio, path="/tmp/round_2.wav"),
                Artifact(job=job, round=round_2, kind=ArtifactKind.review_json, path="/tmp/review.json"),
                Artifact(job=job, round=round_3, kind=ArtifactKind.transcript_txt, path="/tmp/round_3.transcript.txt"),
                Artifact(job=job, round=round_3, kind=ArtifactKind.audio, path="/tmp/round_3.wav"),
            ]
        )

        decision = build_archive_retention_decision(job)

        self.assertEqual(decision.final_round_id, "round_1")
        self.assertEqual(decision.correction_round_id, "round_3")
        self.assertEqual(decision.retained_round_ids, ("round_1", "round_3"))
        self.assertEqual(decision.prunable_round_ids, ("round_2",))
        self.assertIn("/tmp/round_1.transcript.txt", decision.retained_artifact_paths)
        self.assertIn("/tmp/round_3.transcript.txt", decision.retained_artifact_paths)
        self.assertNotIn("/tmp/round_2.transcript.txt", decision.retained_artifact_paths)
        self.assertIn("/tmp/round_1.wav", decision.prunable_artifact_paths)
        self.assertIn("/tmp/round_2.wav", decision.prunable_artifact_paths)
        self.assertIn("/tmp/round_3.wav", decision.prunable_artifact_paths)
        self.assertIn("/tmp/review.json", decision.prunable_artifact_paths)

    def test_path_deletion_helper(self) -> None:
        self.assertTrue(path_should_be_deleted("/tmp/example.wav"))
        self.assertTrue(path_should_be_deleted("/tmp/review.json"))
        self.assertFalse(path_should_be_deleted("/tmp/final.json"))
        self.assertFalse(path_should_be_deleted("/tmp/example.transcript.txt"))

    def test_same_round_for_final_and_correction_is_retained_once(self) -> None:
        job = Job(job_id="job_same", job_number="J9997", status=JobStatus.archived)
        round_1 = JobRound(job=job, round_id="round_1")
        job.rounds.append(round_1)
        final = JobFinal(job=job, kind="final", round_id="round_1", payload={})
        correction = JobFinal(job=job, kind="correction", round_id="round_1", payload={})
        job.finals.extend([final, correction])

        decision = build_archive_retention_decision(job)

        self.assertEqual(decision.retained_round_ids, ("round_1",))


if __name__ == "__main__":
    unittest.main()
