"""Focused regression checks for assigned-job projection helpers."""

from __future__ import annotations

from types import SimpleNamespace
import unittest

from app.services.assigned_job_service import AssignedJobService


class _DummyReviewPayloadService:
    def build_round_images(self, rows):
        return [{"image_id": row["image_id"]} for row in rows]

    def normalize_payload(self, payload, *, tree_number, normalize_form_schema, hydrated_images):
        return {
            "payload": payload,
            "tree_number": tree_number,
            "normalized": normalize_form_schema(payload.get("draft_form", {}).get("data", {})),
            "images": hydrated_images,
        }


class _DummyDbStore:
    def __init__(self) -> None:
        self.job_round = {
            "review_payload": {
                "server_revision_id": "rev-1",
                "draft_form": {"data": {"client_tree_details": {"client": "Software Test"}}},
            }
        }
        self.round_images = [{"image_id": "img_1"}]

    def get_job_round(self, job_id: str, round_id: str):
        del job_id, round_id
        return dict(self.job_round)

    def list_round_images(self, job_id: str, round_id: str):
        del job_id, round_id
        return list(self.round_images)


class AssignedJobServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db_store = _DummyDbStore()
        self.service = AssignedJobService(
            db_store=self.db_store,
            review_payload_service=_DummyReviewPayloadService(),
            normalize_form_schema=lambda form: {"normalized": form},
            assigned_job_factory=lambda **kwargs: kwargs,
        )
        self.record = SimpleNamespace(
            job_id="job_1",
            job_number="J0001",
            status="REVIEW_RETURNED",
            latest_round_id="round_1",
            latest_round_status="review_returned",
            customer_name="Software Test",
            tree_number=1,
            address="123 Main",
            tree_species="apple",
            reason="Inspection",
            job_name="Test Job",
            job_address="123 Main",
            job_phone="555-1212",
            contact_preference="phone",
            billing_name="Billing",
            billing_address="Billing Address",
            billing_contact_name="Billing Contact",
            location_notes="Near the gate",
            rounds={"round_1": SimpleNamespace(server_revision_id=None)},
        )

    def test_to_assigned_job_hydrates_review_payload(self) -> None:
        assigned = self.service.to_assigned_job(self.record)

        self.assertEqual(assigned["job_id"], "job_1")
        self.assertEqual(assigned["server_revision_id"], "rev-1")
        self.assertEqual(assigned["review_payload"]["images"], [{"image_id": "img_1"}])
        self.assertEqual(
            assigned["review_payload"]["normalized"],
            {"normalized": {"client_tree_details": {"client": "Software Test"}}},
        )

    def test_resolve_assigned_job_prefers_persisted_record(self) -> None:
        persisted = SimpleNamespace(**self.record.__dict__)
        cached = SimpleNamespace(**{**self.record.__dict__, "job_number": "J9999"})

        assigned = self.service.resolve_assigned_job(
            "job_1",
            refresh_job_record_from_store=lambda job_id: persisted if job_id == "job_1" else None,
            jobs_cache={"job_1": cached},
        )

        self.assertEqual(assigned["job_number"], "J0001")

    def test_resolve_assigned_job_falls_back_to_cache(self) -> None:
        assigned = self.service.resolve_assigned_job(
            "job_1",
            refresh_job_record_from_store=lambda _job_id: None,
            jobs_cache={"job_1": self.record},
        )

        self.assertEqual(assigned["job_id"], "job_1")


if __name__ == "__main__":
    unittest.main()
