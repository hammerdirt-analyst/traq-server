"""Unit tests for archived final/correction mutation behavior."""

from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app import db as db_module
from app.config import load_settings
from app.services.customer_service import CustomerService
from app.db import create_schema, init_database
from app.services.final_mutation_service import FinalMutationService
from app.services.job_mutation_service import JobMutationService


class FinalMutationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.storage_root = Path(self.tempdir.name) / "storage"
        self.storage_root.mkdir(parents=True, exist_ok=True)
        self.old_env = {key: os.environ.get(key) for key in self._env_keys()}
        os.environ["TRAQ_STORAGE_ROOT"] = str(self.storage_root)
        os.environ["TRAQ_DATABASE_URL"] = f"sqlite:///{self.storage_root / 'test.db'}"
        self.addCleanup(self._restore_env)

        db_module._engine = None
        db_module._SessionLocal = None
        init_database(load_settings())
        create_schema()
        customer = CustomerService().create_customer(name="Test Customer")
        JobMutationService().create_job(
            job_id="job_1",
            job_number="J0001",
            customer_id=customer["customer_id"],
            tree_number=1,
            job_name="Valley Oak",
        )
        self.service = FinalMutationService()

    @staticmethod
    def _env_keys() -> tuple[str, ...]:
        return ("TRAQ_STORAGE_ROOT", "TRAQ_DATABASE_URL")

    def _restore_env(self) -> None:
        for key, value in self.old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        db_module._engine = None
        db_module._SessionLocal = None

    def test_set_final_once_and_reject_overwrite(self) -> None:
        result = self.service.set_final(
            "J0001",
            payload={"round_id": "round_1", "transcript": "Final transcript"},
            geojson_payload={"type": "FeatureCollection", "features": []},
        )
        self.assertEqual(result["kind"], "final")
        self.assertEqual(result["job"]["status"], "ARCHIVED")
        with self.assertRaises(ValueError):
            self.service.set_final(
                "J0001",
                payload={"round_id": "round_2", "transcript": "Overwrite"},
            )

    def test_set_correction_overwrites(self) -> None:
        first = self.service.set_correction(
            "J0001",
            payload={"round_id": "round_2", "transcript": "Correction v1"},
        )
        second = self.service.set_correction(
            "J0001",
            payload={"round_id": "round_3", "transcript": "Correction v2"},
            geojson_payload={"type": "FeatureCollection", "features": []},
        )
        self.assertEqual(first["kind"], "correction")
        self.assertEqual(second["round_id"], "round_3")
        self.assertTrue(second["has_geojson"])

    def test_missing_job_raises(self) -> None:
        with self.assertRaises(KeyError):
            self.service.set_correction("J9999", payload={"round_id": "round_1"})


if __name__ == "__main__":
    unittest.main()
