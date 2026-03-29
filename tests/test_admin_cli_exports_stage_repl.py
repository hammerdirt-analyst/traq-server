"""Export, staging, and REPL-oriented CLI coverage."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tests.admin_cli_support import AdminCliTestCase, admin_cli


class AdminCliExportsStageReplTests(AdminCliTestCase):
    @patch("app.cli.remote_backend.request.urlopen")
    @patch("admin_cli._http")
    def test_remote_export_commands(self, http_mock, urlopen_mock) -> None:
        class _Response:
            def __init__(self, payload: bytes, *, filename: str) -> None:
                self._payload = payload
                self.headers = self
                self._filename = filename

            def read(self) -> bytes:
                return self._payload

            def get_filename(self) -> str:
                return self._filename

            def items(self):
                return [("Content-Disposition", f'attachment; filename="{self._filename}"')]

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        http_mock.side_effect = [
            (200, {"cursor": "2026-03-24T18:45:00Z", "server_time": "2026-03-24T18:45:00Z", "in_process": [], "completed": [], "transitioned_to_completed": []}),
            (200, {"type": "FeatureCollection", "features": []}),
        ]
        urlopen_mock.return_value = _Response(b"image-bytes", filename="img_1.jpg")

        rc, output = self._stdout_for(admin_cli.cmd_export_changes, argparse.Namespace(cursor=None, host="https://example.test", api_key="demo-key"))
        self.assertEqual(rc, 0)
        self.assertIn('"cursor": "2026-03-24T18:45:00Z"', output)

        image_output = self.storage_root / "downloaded.jpg"
        rc, output = self._stdout_for(
            admin_cli.cmd_export_image_fetch,
            argparse.Namespace(job_id="job_1", image_ref="img_1", variant="report", output=str(image_output), host="https://example.test", api_key="demo-key"),
        )
        self.assertEqual(rc, 0)
        self.assertTrue(image_output.exists())
        self.assertEqual(image_output.read_bytes(), b"image-bytes")
        self.assertIn('"saved_path"', output)

        geojson_output = self.storage_root / "export.geojson"
        rc, output = self._stdout_for(
            admin_cli.cmd_export_geojson_fetch,
            argparse.Namespace(job_id="job_1", output=str(geojson_output), host="https://example.test", api_key="demo-key"),
        )
        self.assertEqual(rc, 0)
        self.assertTrue(geojson_output.exists())
        self.assertIn('"saved_path"', output)

    @patch("admin_cli._legacy_backend_for_args")
    def test_export_images_fetch_all_downloads_job_images_with_partial_failures(self, backend_for_args_mock) -> None:
        workspace = self.storage_root / "scratch"
        workspace.mkdir(parents=True, exist_ok=True)
        image1 = workspace / "img_1.jpg"
        image1.write_bytes(b"img-1")
        report1 = workspace / "report_1.jpg"
        report1.write_bytes(b"report-1")

        class _Job:
            @staticmethod
            def inspect(*, job_ref: str):
                self.assertEqual(job_ref, "J0001")
                return {"job_id": "job_1", "job_number": "J0001"}

        class _Export:
            @staticmethod
            def changes(*, cursor=None):
                self.assertIsNone(cursor)
                return {
                    "in_process": [{"job_id": "job_1", "review": {"images": [{"image_ref": "img_1"}, {"image_ref": "img_2"}]}}],
                    "completed": [{"job_id": "job_1", "final": {"report_images": [{"image_ref": "report_1"}, {"image_ref": "img_2"}]}}],
                    "transitioned_to_completed": [],
                }

            @staticmethod
            def image_fetch(*, job_id: str, image_ref: str, variant: str, output_path=None):
                self.assertEqual(job_id, "job_1")
                self.assertEqual(variant, "report")
                self.assertIsNone(output_path)
                if image_ref == "img_1":
                    return {"saved_path": str(image1)}
                if image_ref == "report_1":
                    return {"saved_path": str(report1)}
                raise RuntimeError("missing image")

        backend_for_args_mock.return_value = SimpleNamespace(job=_Job(), export=_Export())
        output_dir = self.storage_root / "exports" / "J0001" / "images"
        rc, output = self._stdout_for(
            admin_cli.cmd_export_images_fetch_all,
            argparse.Namespace(job="J0001", variant="report", output=str(output_dir), host="https://example.test", api_key="demo-key"),
        )
        self.assertEqual(rc, 0)
        payload = json.loads(output)
        self.assertEqual(payload["job_id"], "job_1")
        self.assertEqual(payload["job_number"], "J0001")
        self.assertEqual(payload["total_refs"], 3)
        self.assertEqual(payload["skipped_duplicates"], 1)
        self.assertEqual(payload["downloaded_count"], 2)
        self.assertEqual(payload["failed_count"], 1)
        self.assertTrue((output_dir / "img_1.jpg").exists())
        self.assertTrue((output_dir / "report_1.jpg").exists())
        self.assertEqual(payload["failed"][0]["image_ref"], "img_2")

    @patch("admin_cli._legacy_backend_for_args")
    def test_stage_sync_command_stages_completed_jobs(self, backend_for_args_mock) -> None:
        workspace = self.storage_root / "stage_scratch"
        workspace.mkdir(parents=True, exist_ok=True)
        final_json = workspace / "J0003_final.json"
        final_json.write_text(json.dumps({"client_revision_id": "client-rev-1", "archived_at": "2026-03-28T12:00:00Z"}), encoding="utf-8")
        final_geojson = workspace / "J0003_final.geojson"
        final_geojson.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
        traq_pdf = workspace / "J0003_traq_page1.pdf"
        traq_pdf.write_bytes(b"pdf")

        class _Artifact:
            @staticmethod
            def fetch(*, job_ref: str, kind: str):
                self.assertEqual(job_ref, "J0003")
                return {"final-json": {"saved_path": str(final_json)}, "geo-json": {"saved_path": str(final_geojson)}, "traq-pdf": {"saved_path": str(traq_pdf)}}[kind]

        class _Export:
            @staticmethod
            def changes(*, cursor=None):
                return {"cursor": "2026-03-28T12:30:00Z", "completed": [{"job_id": "job_1", "job_number": "J0003", "project": "Briarwood", "project_slug": "briarwood", "final": {"report_images": [{"image_ref": "report_1", "caption": "The tree: east-facing view"}]}}]}

            @staticmethod
            def image_fetch(*, job_id: str, image_ref: str, variant: str, output_path=None):
                self.assertEqual(job_id, "job_1")
                self.assertEqual(image_ref, "report_1")
                self.assertEqual(variant, "report")
                output = Path(str(output_path))
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(b"image")
                return {"saved_path": str(output)}

        backend_for_args_mock.return_value = SimpleNamespace(artifact=_Artifact(), export=_Export())
        stage_root = self.storage_root / "staging"
        rc, output = self._stdout_for(
            admin_cli.cmd_stage_sync,
            argparse.Namespace(root=str(stage_root), cursor=None, host="https://example.test", api_key="demo-key"),
        )
        self.assertEqual(rc, 0)
        payload = json.loads(output)
        self.assertTrue(payload["cursor_updated"])
        self.assertEqual(payload["jobs_staged"], 1)
        self.assertTrue((stage_root / "jobs" / "J0003" / "manifest.json").exists())

    def test_normalize_repl_tokens_strips_optional_leading_slash(self) -> None:
        self.assertEqual(admin_cli._normalize_repl_tokens("/round reopen --job-id job_1 --round-id round_1"), ["round", "reopen", "--job-id", "job_1", "--round-id", "round_1"])
        self.assertEqual(admin_cli._normalize_repl_tokens("job inspect --job J0001"), ["job", "inspect", "--job", "J0001"])

    def test_repl_http_defaults_cover_remote_admin_commands(self) -> None:
        self.assertEqual(admin_cli._inject_http_defaults(["job", "inspect", "--job", "J0001"], host="http://127.0.0.1:8000", api_key="demo-key"), ["job", "inspect", "--job", "J0001", "--host", "http://127.0.0.1:8000", "--api-key", "demo-key"])
        self.assertEqual(admin_cli._inject_http_defaults(["job", "assign", "--job", "J0001", "--device-id", "device-1"], host="http://127.0.0.1:8000", api_key="demo-key"), ["job", "assign", "--job", "J0001", "--device-id", "device-1", "--host", "http://127.0.0.1:8000", "--api-key", "demo-key"])
        self.assertEqual(admin_cli._inject_http_defaults(["job", "unlock", "--job", "J0001"], host="http://127.0.0.1:8000", api_key="demo-key"), ["job", "unlock", "--job", "J0001", "--host", "http://127.0.0.1:8000", "--api-key", "demo-key"])
        self.assertEqual(admin_cli._inject_http_defaults(["tree", "identify", "--image", "./leaf.jpg"], host="http://127.0.0.1:8000", api_key="demo-key"), ["tree", "identify", "--image", "./leaf.jpg", "--host", "http://127.0.0.1:8000", "--api-key", "demo-key"])

    def test_repl_supports_slash_prefixed_commands(self) -> None:
        self._register_pending_device("device-1")
        parser = admin_cli.build_parser()
        stdout = io.StringIO()
        with patch("builtins.input", side_effect=["/device pending", "exit"]):
            with contextlib.redirect_stdout(stdout):
                rc = admin_cli._run_repl(parser)
        self.assertEqual(rc, 0)
        output = stdout.getvalue()
        self.assertIn("TRAQ admin CLI interactive mode", output)
        self.assertIn("device-1", output)
        self.assertIn("status=pending", output)

    def test_repl_can_switch_to_cloud_context(self) -> None:
        import os
        os.environ["TRAQ_CLOUD_ADMIN_BASE_URL"] = "https://cloud.example.run.app"
        os.environ["TRAQ_CLOUD_API_KEY"] = "cloud-key"
        parser = admin_cli.build_parser()
        stdout = io.StringIO()
        with patch("builtins.input", side_effect=["use cloud", "show", "exit"]):
            with contextlib.redirect_stdout(stdout):
                rc = admin_cli._run_repl(parser)
        self.assertEqual(rc, 0)
        output = stdout.getvalue()
        self.assertIn("context=cloud", output)
        self.assertIn("host=https://cloud.example.run.app", output)

    def test_build_parser_uses_remote_backend_defaults_for_customer_commands(self) -> None:
        backend = admin_cli._build_backend(context_name="cloud", host="https://cloud.example.run.app", api_key="cloud-key")
        parser = admin_cli.build_parser(backend=backend)
        args = parser.parse_args(["customer", "list"])
        self.assertEqual(args.host, "https://cloud.example.run.app")
        self.assertEqual(args.api_key, "cloud-key")
