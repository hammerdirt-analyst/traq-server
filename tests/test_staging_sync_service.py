"""Tests for admin-side completed-job staging sync."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from app.services.staging_sync_service import StagingSyncService


class StagingSyncServiceTests(unittest.TestCase):
    def test_sync_stages_completed_job_bundle_and_manifest(self) -> None:
        with TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            scratch = root / "scratch"
            scratch.mkdir(parents=True, exist_ok=True)

            final_json_source = scratch / "J0003_final.json"
            final_json_source.write_text(
                json.dumps(
                    {
                        "client_revision_id": "client-rev-1",
                        "archived_at": "2026-03-28T12:00:00Z",
                        "transcript": "Transcript",
                    }
                ),
                encoding="utf-8",
            )
            geojson_source = scratch / "J0003_final.geojson"
            geojson_source.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
            traq_source = scratch / "J0003_traq_page1.pdf"
            traq_source.write_bytes(b"pdf-bytes")

            class _Artifact:
                @staticmethod
                def fetch(*, job_ref: str, kind: str):
                    self.assertEqual(job_ref, "J0003")
                    return {
                        "final-json": {"saved_path": str(final_json_source)},
                        "geo-json": {"saved_path": str(geojson_source)},
                        "traq-pdf": {"saved_path": str(traq_source)},
                    }[kind]

            class _Export:
                @staticmethod
                def changes(*, cursor=None):
                    self.assertIsNone(cursor)
                    return {
                        "cursor": "2026-03-28T12:30:00Z",
                        "completed": [
                            {
                                "job_id": "job_1",
                                "job_number": "J0003",
                                "project_id": "project_1",
                                "project": "Briarwood",
                                "project_slug": "briarwood",
                                "final": {
                                    "report_images": [
                                        {"image_ref": "report_1", "caption": "The tree: east-facing view"},
                                        {"image_ref": "report_2", "caption": "Root flare"},
                                    ]
                                },
                            }
                        ],
                    }

                @staticmethod
                def image_fetch(*, job_id: str, image_ref: str, variant: str, output_path=None):
                    self.assertEqual(job_id, "job_1")
                    self.assertEqual(variant, "report")
                    output = Path(str(output_path))
                    output.parent.mkdir(parents=True, exist_ok=True)
                    output.write_bytes(f"{image_ref}-bytes".encode("utf-8"))
                    return {"saved_path": str(output)}

            service = StagingSyncService(
                backend=SimpleNamespace(artifact=_Artifact(), export=_Export()),
                root=root / "staging",
            )
            result = service.sync()

            self.assertTrue(result.cursor_updated)
            bundle_dir = root / "staging" / "jobs" / "J0003"
            manifest_path = bundle_dir / "manifest.json"
            self.assertTrue(manifest_path.exists())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["job_id"], "job_1")
            self.assertEqual(manifest["job_number"], "J0003")
            self.assertEqual(manifest["project_id"], "project_1")
            self.assertEqual(manifest["project"], "Briarwood")
            self.assertEqual(manifest["project_slug"], "briarwood")
            self.assertEqual(manifest["client_revision_id"], "client-rev-1")
            self.assertEqual(manifest["artifacts"]["final_json"], "./final.json")
            self.assertEqual(manifest["artifacts"]["final_geojson"], "./final.geojson")
            self.assertEqual(manifest["artifacts"]["traq_pdf"], "./traq_page1.pdf")
            self.assertEqual(manifest["images"][0]["source_path"], "./images/report_1.jpg")
            self.assertEqual(manifest["images"][0]["caption"], "The tree: east-facing view")
            self.assertTrue((bundle_dir / "images" / "report_1.jpg").exists())
            self.assertTrue((root / "staging" / "state" / "export_cursor.json").exists())

    def test_sync_preserves_cursor_when_job_fails(self) -> None:
        with TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            class _Artifact:
                @staticmethod
                def fetch(*, job_ref: str, kind: str):
                    raise RuntimeError(f"missing {kind} for {job_ref}")

            class _Export:
                @staticmethod
                def changes(*, cursor=None):
                    return {
                        "cursor": "2026-03-28T12:30:00Z",
                        "completed": [{"job_id": "job_1", "job_number": "J0003", "final": {"report_images": []}}],
                    }

            service = StagingSyncService(
                backend=SimpleNamespace(artifact=_Artifact(), export=_Export()),
                root=root / "staging",
            )
            result = service.sync()

            self.assertFalse(result.cursor_updated)
            self.assertEqual(result.jobs_failed, 1)
            self.assertFalse((root / "staging" / "state" / "export_cursor.json").exists())

    def test_exclude_job_removes_bundle_and_future_sync_skips_it(self) -> None:
        with TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            scratch = root / "scratch"
            scratch.mkdir(parents=True, exist_ok=True)
            final_json_source = scratch / "J0003_final.json"
            final_json_source.write_text(json.dumps({"client_revision_id": "client-rev-1"}), encoding="utf-8")
            geojson_source = scratch / "J0003_final.geojson"
            geojson_source.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
            traq_source = scratch / "J0003_traq_page1.pdf"
            traq_source.write_bytes(b"pdf-bytes")

            class _Artifact:
                @staticmethod
                def fetch(*, job_ref: str, kind: str):
                    return {
                        "final-json": {"saved_path": str(final_json_source)},
                        "geo-json": {"saved_path": str(geojson_source)},
                        "traq-pdf": {"saved_path": str(traq_source)},
                    }[kind]

            class _Export:
                @staticmethod
                def changes(*, cursor=None):
                    return {
                        "cursor": "2026-03-28T12:30:00Z",
                        "completed": [
                            {
                                "job_id": "job_1",
                                "job_number": "J0003",
                                "project_id": None,
                                "project": None,
                                "project_slug": None,
                                "final": {"report_images": []},
                            }
                        ],
                    }

                @staticmethod
                def image_fetch(*, job_id: str, image_ref: str, variant: str, output_path=None):
                    raise AssertionError("image_fetch should not be called for excluded job")

            service = StagingSyncService(
                backend=SimpleNamespace(artifact=_Artifact(), export=_Export()),
                root=root / "staging",
            )
            initial = service.sync()
            self.assertEqual(initial.jobs_staged, 1)
            self.assertTrue((root / "staging" / "jobs" / "J0003").exists())

            excluded = service.exclude_job(job_ref="J0003")
            self.assertTrue(excluded["removed_bundle"])
            self.assertFalse((root / "staging" / "jobs" / "J0003").exists())

            listed = service.list_exclusions()
            self.assertEqual(listed.excluded_jobs, ["J0003"])

            second = service.sync()
            self.assertEqual(second.jobs_staged, 0)
            self.assertEqual(second.jobs_failed, 0)
            self.assertFalse((root / "staging" / "jobs" / "J0003").exists())

    def test_include_job_removes_job_from_exclusion_list(self) -> None:
        with TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            service = StagingSyncService(backend=SimpleNamespace(), root=root / "staging")

            exclude_payload = service.exclude_job(job_ref="J0001")
            self.assertTrue(exclude_payload["excluded"])
            include_payload = service.include_job(job_ref="J0001")
            self.assertFalse(include_payload["excluded"])
            self.assertTrue(include_payload["was_excluded"])
            listed = service.list_exclusions()
            self.assertEqual(listed.excluded_jobs, [])


if __name__ == "__main__":
    unittest.main()
