"""Tests for the server-managed project registry and job assignment flow."""

from __future__ import annotations

import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

from app import db as db_module
from app.config import load_settings
from app.db import create_schema, init_database
from app.db_store import DatabaseStore
from app.services.job_mutation_service import JobMutationService
from app.services.project_service import ProjectService


class ProjectServiceTests(unittest.TestCase):
    """Cover project creation, update, and job-level assignment propagation."""

    def setUp(self) -> None:
        self.tempdir = TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.storage_root = Path(self.tempdir.name) / "storage"
        self.storage_root.mkdir(parents=True, exist_ok=True)
        self.old_env = {key: os.environ.get(key) for key in ("TRAQ_STORAGE_ROOT", "TRAQ_DATABASE_URL")}
        os.environ["TRAQ_STORAGE_ROOT"] = str(self.storage_root)
        os.environ["TRAQ_DATABASE_URL"] = f"sqlite:///{self.storage_root / 'test.db'}"
        self.addCleanup(self._restore_env)

        db_module._engine = None
        db_module._SessionLocal = None
        init_database(load_settings())
        create_schema()
        self.store = DatabaseStore()
        self.projects = ProjectService()
        self.jobs = JobMutationService()

    def _restore_env(self) -> None:
        for key, value in self.old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        db_module._engine = None
        db_module._SessionLocal = None

    def test_create_update_and_list_projects(self) -> None:
        created = self.projects.create_project(project="Briarwood")
        self.assertTrue(created["project_id"].startswith("project_"))
        self.assertEqual(created["project"], "Briarwood")
        self.assertEqual(created["project_slug"], "briarwood")

        updated = self.projects.update_project(created["project_id"], project="Briarwood West")
        self.assertEqual(updated["project"], "Briarwood West")
        self.assertEqual(updated["project_slug"], "briarwood-west")

        listed = self.projects.list_projects()
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["project_id"], created["project_id"])

    def test_job_create_and_update_propagate_project_fields(self) -> None:
        project = self.projects.create_project(project="Arboretum")

        created = self.jobs.create_job(
            job_id="job_1",
            job_number="J0001",
            status="DRAFT",
            project_id=project["project_id"],
            job_name="Test Job",
        )
        self.assertEqual(created["project_id"], project["project_id"])
        self.assertEqual(created["project"], "Arboretum")
        self.assertEqual(created["project_slug"], "arboretum")

        loaded = self.store.get_job("job_1")
        self.assertEqual(loaded["project_id"], project["project_id"])
        self.assertEqual(loaded["project"], "Arboretum")

        cleared = self.jobs.update_job("J0001", project_id=None)
        self.assertIsNone(cleared["project_id"])
        self.assertIsNone(cleared["project"])
        self.assertIsNone(cleared["project_slug"])

    def test_invalid_project_id_is_rejected(self) -> None:
        with self.assertRaises(KeyError):
            self.jobs.create_job(
                job_id="job_2",
                job_number="J0002",
                status="DRAFT",
                project_id="project_missing",
                job_name="Broken Job",
            )


if __name__ == "__main__":
    unittest.main()
