"""Unit tests for runtime state helper extraction."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi import HTTPException

from app.artifact_storage import LocalArtifactStore
from app.services.runtime_state_service import RuntimeStateService


@dataclass
class _RoundRecord:
    round_id: str
    status: str
    manifest: list[dict] = field(default_factory=list)
    server_revision_id: str | None = None


@dataclass
class _JobRecord:
    job_id: str
    job_number: str
    status: str
    customer_name: str | None = None
    tree_number: int | None = None
    address: str | None = None
    tree_species: str | None = None
    reason: str | None = None
    job_name: str | None = None
    job_address: str | None = None
    job_phone: str | None = None
    contact_preference: str | None = None
    billing_name: str | None = None
    billing_address: str | None = None
    billing_contact_name: str | None = None
    location_notes: str | None = None
    latest_round_id: str | None = None
    latest_round_status: str | None = None
    rounds: dict[str, _RoundRecord] = field(default_factory=dict)


class _DummyDbStore:
    def __init__(self) -> None:
        self.job_payload: dict | None = None
        self.round_rows: list[dict] = []
        self.round_payload: dict | None = None
        self.saved_job: dict | None = None
        self.saved_round: dict | None = None
        self.allocated_job_number = "J0009"

    def upsert_job(self, **kwargs):
        self.saved_job = kwargs
        return kwargs

    def get_job(self, job_id: str):
        del job_id
        return self.job_payload

    def list_job_rounds(self, job_id: str):
        del job_id
        return list(self.round_rows)

    def get_job_round(self, job_id: str, round_id: str):
        del job_id, round_id
        return self.round_payload

    def upsert_job_round(self, **kwargs):
        self.saved_round = kwargs
        return kwargs

    def allocate_job_number(self):
        return self.allocated_job_number


class RuntimeStateServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        self.db = _DummyDbStore()
        self.writes: list[tuple[Path, dict]] = []
        self.service = RuntimeStateService(
            storage_root=self.root,
            db_store=self.db,
            artifact_store=LocalArtifactStore(self.root),
            logger=__import__("logging").getLogger("runtime-state-test"),
            parse_tree_number=lambda value: int(value) if value not in (None, "") else None,
            job_record_factory=_JobRecord,
            round_record_factory=_RoundRecord,
            write_json=lambda path, payload: self._capture_write(path, payload),
        )

    def _capture_write(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(payload), encoding="utf-8")
        self.writes.append((path, payload))

    def test_save_job_record_persists_db_and_disk_payload(self) -> None:
        record = _JobRecord(job_id="job_1", job_number="J0001", status="DRAFT", job_name="Job")

        self.service.save_job_record(record)

        self.assertEqual(self.db.saved_job["job_id"], "job_1")
        self.assertTrue((self.root / "jobs/job_1/job_record.json").exists())

    def test_load_job_record_prefers_db_and_parses_tree_number(self) -> None:
        self.db.job_payload = {
            "job_id": "job_1",
            "job_number": "J0001",
            "status": "DRAFT",
            "tree_number": "7",
        }

        record = self.service.load_job_record("job_1")

        self.assertEqual(record.tree_number, 7)
        self.assertEqual(record.job_number, "J0001")

    def test_refresh_job_record_from_store_merges_cached_rounds(self) -> None:
        self.db.job_payload = {"job_id": "job_1", "job_number": "J0001", "status": "DRAFT"}
        self.db.round_rows = [{"round_id": "round_1", "status": "DRAFT", "manifest": []}]
        cached = _JobRecord(job_id="job_1", job_number="J0001", status="DRAFT")
        cached.rounds["round_2"] = _RoundRecord(round_id="round_2", status="REVIEW_RETURNED")
        jobs_cache = {"job_1": cached}

        refreshed = self.service.refresh_job_record_from_store("job_1", jobs_cache=jobs_cache)

        self.assertIn("round_1", refreshed.rounds)
        self.assertIn("round_2", refreshed.rounds)
        self.assertIs(jobs_cache["job_1"], refreshed)

    def test_save_round_record_persists_manifest_and_review_payload(self) -> None:
        round_record = _RoundRecord(round_id="round_1", status="DRAFT", manifest=[{"kind": "recording"}])

        self.service.save_round_record("job_1", round_record, review_payload={"round_id": "round_1"})

        self.assertEqual(self.db.saved_round["round_id"], "round_1")
        self.assertTrue((self.root / "jobs/job_1/rounds/round_1/manifest.json").exists())
        self.assertTrue((self.root / "jobs/job_1/rounds/round_1/review.json").exists())

    def test_ensure_round_record_raises_when_missing(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            self.service.ensure_round_record("job_missing", "round_1", jobs_cache={})
        self.assertEqual(ctx.exception.status_code, 404)

    def test_next_job_number_wraps_db_allocation(self) -> None:
        self.assertEqual(self.service.next_job_number(), "J0009")


if __name__ == "__main__":
    unittest.main()
