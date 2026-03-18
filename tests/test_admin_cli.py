"""CLI coverage for the current server operator command set."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from app import db as db_module
from app.config import load_settings
from app.db import create_schema, init_database
from app.db_store import DatabaseStore
from app.services.inspection_service import InspectionService

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import admin_cli  # type: ignore  # noqa: E402

try:
    import app.db as cli_db_module  # type: ignore
except Exception:  # pragma: no cover - only relevant in CLI import mode
    cli_db_module = None


class AdminCliTests(unittest.TestCase):
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
        if cli_db_module is not None:
            cli_db_module._engine = None
            cli_db_module._SessionLocal = None
        init_database(load_settings())
        create_schema()
        self.store = DatabaseStore()
        self.inspection_service = InspectionService(settings=load_settings(), db_store=self.store)

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
        if cli_db_module is not None:
            cli_db_module._engine = None
            cli_db_module._SessionLocal = None

    def _register_pending_device(self, device_id: str = "device-1") -> None:
        self.store.register_device(
            device_id=device_id,
            device_name="Pixel",
            app_version="0.1.0",
            profile_summary=None,
        )

    def _stdout_for(self, func, *args, **kwargs) -> tuple[int, str]:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            rc = func(*args, **kwargs)
        return int(rc), stdout.getvalue()

    def test_device_list_pending_validate_approve_revoke_and_issue_token(self) -> None:
        self._register_pending_device("device-1")
        self._register_pending_device("device-2")

        rc, output = self._stdout_for(
            admin_cli.cmd_device_list,
            argparse.Namespace(status="pending", json=False),
        )
        self.assertEqual(rc, 0)
        self.assertIn("device-1"[:8], output)
        self.assertIn("pending", output)

        rc, output = self._stdout_for(
            admin_cli.cmd_device_pending,
            argparse.Namespace(json=True),
        )
        self.assertEqual(rc, 0)
        self.assertIn('"device_id": "device-1"', output)
        self.assertIn('"device_id": "device-2"', output)

        rc, output = self._stdout_for(
            admin_cli.cmd_device_validate,
            argparse.Namespace(index=2, role="admin"),
        )
        self.assertEqual(rc, 0)
        self.assertIn("Validated device", output)
        approved = self.store.get_device("device-2")
        self.assertIsNotNone(approved)
        self.assertEqual(approved["status"], "approved")
        self.assertEqual(approved["role"], "admin")

        rc, output = self._stdout_for(
            admin_cli.cmd_device_approve,
            argparse.Namespace(device_id="device-1", role="arborist"),
        )
        self.assertEqual(rc, 0)
        self.assertIn('"status": "approved"', output)

        rc, output = self._stdout_for(
            admin_cli.cmd_device_issue_token,
            argparse.Namespace(device_id="device-1", ttl=3600),
        )
        self.assertEqual(rc, 0)
        self.assertIn("access_token", output)

        rc, output = self._stdout_for(
            admin_cli.cmd_device_revoke,
            argparse.Namespace(device_id="device-1"),
        )
        self.assertEqual(rc, 0)
        self.assertIn('"status": "revoked"', output)

    @patch("admin_cli._pending_devices")
    def test_device_validate_handles_invalid_index(self, pending_mock) -> None:
        pending_mock.return_value = [{"device_id": "device-1"}]
        rc, output = self._stdout_for(
            admin_cli.cmd_device_validate,
            argparse.Namespace(index=5, role="arborist"),
        )
        self.assertEqual(rc, 1)
        self.assertIn("Invalid index", output)

    @patch("admin_cli._http")
    def test_job_list_assignments(self, http_mock) -> None:
        http_mock.return_value = (
            200,
            {"assignments": [{"job_id": "job_1", "device_id": "device-1"}]},
        )
        rc, output = self._stdout_for(
            admin_cli.cmd_job_list_assignments,
            argparse.Namespace(host="http://127.0.0.1:8000", api_key="demo-key", raw=False),
        )
        self.assertEqual(rc, 0)
        self.assertIn('"job_id": "job_1"', output)
        http_mock.assert_called_once()

    @patch("admin_cli._http")
    def test_job_assign_unassign_and_set_status(self, http_mock) -> None:
        http_mock.return_value = (200, {"ok": True})
        self._register_pending_device("device-1")

        rc, output = self._stdout_for(
            admin_cli.cmd_job_assign,
            argparse.Namespace(
                job="job_1",
                device_id="device-1",
                host="http://127.0.0.1:8000",
                api_key="demo-key",
            ),
        )
        self.assertEqual(rc, 0)
        self.assertIn('"ok": true', output.lower())

        rc, output = self._stdout_for(
            admin_cli.cmd_job_unassign,
            argparse.Namespace(
                job="job_1",
                host="http://127.0.0.1:8000",
                api_key="demo-key",
            ),
        )
        self.assertEqual(rc, 0)

        rc, output = self._stdout_for(
            admin_cli.cmd_job_set_status,
            argparse.Namespace(
                job="job_1",
                status="REVIEW_RETURNED",
                round_id="round_1",
                round_status="REVIEW_RETURNED",
                host="http://127.0.0.1:8000",
                api_key="demo-key",
            ),
        )
        self.assertEqual(rc, 0)
        self.assertEqual(http_mock.call_count, 3)

    def test_resolve_device_id_accepts_unique_prefix(self) -> None:
        self._register_pending_device("dc82323f-5424-49a2-9211-67b01f9f9ded")
        resolved = admin_cli._resolve_device_id("dc82323f")
        self.assertEqual(resolved, "dc82323f-5424-49a2-9211-67b01f9f9ded")

    @patch("admin_cli._inspection_service")
    def test_resolve_job_id_uses_db_store(self, inspection_mock) -> None:
        self.store.upsert_job(
            job_id="job_1",
            job_number="J0001",
            status="DRAFT",
            details={"job_name": "Customer Tree"},
        )
        inspection_mock.return_value = self.inspection_service
        resolved = admin_cli._resolve_job_id(
            "http://127.0.0.1:8000",
            "demo-key",
            "J0001",
        )
        self.assertEqual(resolved, "job_1")

    @patch("admin_cli._http")
    def test_round_reopen(self, http_mock) -> None:
        http_mock.return_value = (200, {"ok": True, "status": "DRAFT"})
        rc, output = self._stdout_for(
            admin_cli.cmd_round_reopen,
            argparse.Namespace(
                job_id="job_1",
                round_id="round_2",
                host="http://127.0.0.1:8000",
                api_key="demo-key",
            ),
        )
        self.assertEqual(rc, 0)
        self.assertIn('"status": "DRAFT"', output)

    @patch("app.cli.net_commands.subprocess.check_output")
    def test_net_ipv4_and_ipv6(self, check_output_mock) -> None:
        check_output_mock.side_effect = [
            "2: wlp0s20f3: <BROADCAST>\n    inet 192.168.12.231/24 scope global dynamic wlp0s20f3\n",
            "192.168.12.231 2601:204:f301:8de0::dcf0\n",
            "2: wlp0s20f3: <BROADCAST>\n    inet6 2601:204:f301:8de0::dcf0/128 scope global dynamic \n",
        ]

        rc, output = self._stdout_for(admin_cli.cmd_net_ipv4, argparse.Namespace(json=False))
        self.assertEqual(rc, 0)
        self.assertIn("192.168.12.231/24", output)

        rc, output = self._stdout_for(admin_cli.cmd_net_ipv6, argparse.Namespace(json=True))
        self.assertEqual(rc, 0)
        self.assertIn("2601:204:f301:8de0::dcf0", output)

    @patch("admin_cli._inspection_service")
    def test_job_round_review_and_final_inspect_commands(self, inspection_mock) -> None:
        customer = json.loads(
            self._stdout_for(
                admin_cli.cmd_customer_create,
                argparse.Namespace(name="Customer Tree Owner", phone=None, address=None),
            )[1]
        )
        self._stdout_for(
            admin_cli.cmd_job_create,
            argparse.Namespace(
                job_id="job_1",
                job_number="J0001",
                customer_id=customer["customer_id"],
                billing_profile_id=None,
                tree_number="4",
                job_name="Customer Tree",
                job_address="123 Oak St",
                reason=None,
                location_notes=None,
                tree_species=None,
                status="REVIEW_RETURNED",
            ),
        )
        job_dir = self.storage_root / "jobs" / "job_1"
        round_dir = job_dir / "rounds" / "round_1"
        round_dir.mkdir(parents=True, exist_ok=True)
        (round_dir / "manifest.json").write_text(
            json.dumps([{"artifact_id": "rec_1", "kind": "recording"}]),
            encoding="utf-8",
        )
        (round_dir / "review.json").write_text(
            json.dumps(
                {
                    "server_revision_id": "rev_round_1",
                    "tree_number": 4,
                    "transcript": "Transcript ready.",
                    "section_transcripts": {"client_tree_details": "hello"},
                    "images": [],
                    "draft_form": {
                        "schema_name": "demo",
                        "schema_version": "0.0",
                        "data": {"client_tree_details": {"tree_number": "4"}},
                    },
                }
            ),
            encoding="utf-8",
        )
        (job_dir / "final.json").write_text(
            json.dumps(
                {
                    "round_id": "round_1",
                    "user_name": "Roger",
                    "transcript": "Final transcript",
                    "report_images": [],
                }
            ),
            encoding="utf-8",
        )
        (job_dir / "final_traq_page1.pdf").write_text("pdf", encoding="utf-8")
        (job_dir / "final_report_letter.pdf").write_text("pdf", encoding="utf-8")
        (job_dir / "final.geojson").write_text("{}", encoding="utf-8")
        inspection_mock.return_value = self.inspection_service

        rc, output = self._stdout_for(
            admin_cli.cmd_job_inspect,
            argparse.Namespace(job="J0001"),
        )
        self.assertEqual(rc, 0)
        self.assertIn('"job_number": "J0001"', output)
        self.assertIn('"customer_code": "C0001"', output)

        rc, output = self._stdout_for(
            admin_cli.cmd_round_inspect,
            argparse.Namespace(job="J0001", round_id="round_1"),
        )
        self.assertEqual(rc, 0)
        self.assertIn('"manifest_count": 1', output)

        rc, output = self._stdout_for(
            admin_cli.cmd_review_inspect,
            argparse.Namespace(job="J0001", round_id="round_1"),
        )
        self.assertEqual(rc, 0)
        self.assertIn('"server_revision_id": "rev_round_1"', output)
        self.assertIn('"tree_number": 4', output)

        rc, output = self._stdout_for(
            admin_cli.cmd_final_inspect,
            argparse.Namespace(job="J0001"),
        )
        self.assertEqual(rc, 0)
        self.assertIn('"exists": true', output.lower())
        self.assertIn('"report_pdf_exists": true', output.lower())

    def test_customer_and_billing_commands(self) -> None:
        rc, output = self._stdout_for(
            admin_cli.cmd_customer_create,
            argparse.Namespace(
                name="Sacramento State Arboretum",
                phone="555-1212",
                address="6000 J St",
            ),
        )
        self.assertEqual(rc, 0)
        created_customer = json.loads(output)
        self.assertEqual(created_customer["customer_code"], "C0001")
        self.assertEqual(created_customer["name"], "Sacramento State Arboretum")

        rc, output = self._stdout_for(
            admin_cli.cmd_customer_list,
            argparse.Namespace(search="Arboretum"),
        )
        self.assertEqual(rc, 0)
        listed_customers = json.loads(output)
        self.assertEqual(len(listed_customers), 1)

        rc, output = self._stdout_for(
            admin_cli.cmd_customer_update,
            argparse.Namespace(
                customer_id=created_customer["customer_id"],
                name=None,
                phone="555-3434",
                address=None,
            ),
        )
        self.assertEqual(rc, 0)
        updated_customer = json.loads(output)
        self.assertEqual(updated_customer["phone"], "555-3434")

    def test_artifact_fetch_command_exports_report_pdf(self) -> None:
        service = admin_cli._job_mutation_service()
        final_service = admin_cli._final_mutation_service()
        service.create_job(
            job_id="job_artifact",
            job_number="J0010",
            status="ARCHIVED",
            customer_id=None,
            billing_profile_id=None,
            tree_number=None,
            job_name="Artifact Fetch",
            job_address="123 Export St",
            reason=None,
            location_notes=None,
            tree_species=None,
        )
        final_service.set_final(
            "J0010",
            payload={"round_id": "round_1", "transcript": "Final transcript"},
        )
        job_dir = self.storage_root / "jobs" / "job_artifact"
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "final_report_letter.pdf").write_bytes(b"report-bytes")

        rc, output = self._stdout_for(
            admin_cli.cmd_artifact_fetch,
            argparse.Namespace(job="J0010", kind="report-pdf"),
        )
        self.assertEqual(rc, 0)
        payload = json.loads(output)
        self.assertEqual(payload["variant"], "final")
        exported = Path(payload["saved_path"])
        self.assertTrue(exported.exists())
        self.assertEqual(exported.name, "J0010_report_letter.pdf")
        self.assertEqual(exported.read_bytes(), b"report-bytes")

    def test_artifact_fetch_command_exports_final_json(self) -> None:
        service = admin_cli._job_mutation_service()
        final_service = admin_cli._final_mutation_service()
        service.create_job(
            job_id="job_artifact_json",
            job_number="J0011",
            status="ARCHIVED",
            customer_id=None,
            billing_profile_id=None,
            tree_number=None,
            job_name="Artifact Json",
            job_address="124 Export St",
            reason=None,
            location_notes=None,
            tree_species=None,
        )
        final_service.set_final(
            "J0011",
            payload={"round_id": "round_1", "transcript": "Json transcript"},
        )

        rc, output = self._stdout_for(
            admin_cli.cmd_artifact_fetch,
            argparse.Namespace(job="J0011", kind="final-json"),
        )
        self.assertEqual(rc, 0)
        payload = json.loads(output)
        exported = Path(payload["saved_path"])
        self.assertTrue(exported.exists())
        self.assertEqual(exported.name, "J0011_final.json")
        exported_payload = json.loads(exported.read_text(encoding="utf-8"))
        self.assertEqual(exported_payload["transcript"], "Json transcript")

        rc, output = self._stdout_for(
            admin_cli.cmd_billing_create,
            argparse.Namespace(
                billing_name="City of Trees",
                billing_contact_name="A. Manager",
                billing_address="123 Elm",
                contact_preference="email",
            ),
        )
        self.assertEqual(rc, 0)
        created_billing = json.loads(output)
        self.assertEqual(created_billing["billing_code"], "B0001")
        self.assertEqual(created_billing["billing_name"], "City of Trees")

        rc, output = self._stdout_for(
            admin_cli.cmd_billing_list,
            argparse.Namespace(search="Trees"),
        )
        self.assertEqual(rc, 0)
        listed_billing = json.loads(output)
        self.assertEqual(len(listed_billing), 1)

        rc, output = self._stdout_for(
            admin_cli.cmd_billing_update,
            argparse.Namespace(
                billing_profile_id=created_billing["billing_profile_id"],
                billing_name=None,
                billing_contact_name="B. Manager",
                billing_address=None,
                contact_preference="phone",
            ),
        )
        self.assertEqual(rc, 0)
        updated_billing = json.loads(output)
        self.assertEqual(updated_billing["billing_contact_name"], "B. Manager")
        self.assertEqual(updated_billing["contact_preference"], "phone")

    def test_customer_and_billing_duplicates_commands(self) -> None:
        self._stdout_for(
            admin_cli.cmd_customer_create,
            argparse.Namespace(name="Test", phone="111", address=None),
        )
        self._stdout_for(
            admin_cli.cmd_customer_create,
            argparse.Namespace(name=" Test ", phone="222", address=None),
        )
        self._stdout_for(
            admin_cli.cmd_billing_create,
            argparse.Namespace(
                billing_name="Test Billing",
                billing_contact_name=None,
                billing_address=None,
                contact_preference=None,
            ),
        )
        self._stdout_for(
            admin_cli.cmd_billing_create,
            argparse.Namespace(
                billing_name=" Test Billing ",
                billing_contact_name=None,
                billing_address=None,
                contact_preference=None,
            ),
        )

        rc, output = self._stdout_for(admin_cli.cmd_customer_duplicates, argparse.Namespace())
        self.assertEqual(rc, 0)
        customer_dups = json.loads(output)
        self.assertEqual(customer_dups[0]["normalized_name"], "test")
        self.assertEqual(customer_dups[0]["count"], 2)

        rc, output = self._stdout_for(admin_cli.cmd_billing_duplicates, argparse.Namespace())
        self.assertEqual(rc, 0)
        billing_dups = json.loads(output)
        self.assertEqual(billing_dups[0]["normalized_billing_name"], "test billing")
        self.assertEqual(billing_dups[0]["count"], 2)

    def test_customer_and_billing_delete_commands(self) -> None:
        customer = json.loads(
            self._stdout_for(
                admin_cli.cmd_customer_create,
                argparse.Namespace(name="Delete Customer", phone=None, address=None),
            )[1]
        )
        billing = json.loads(
            self._stdout_for(
                admin_cli.cmd_billing_create,
                argparse.Namespace(
                    billing_name="Delete Billing",
                    billing_contact_name=None,
                    billing_address=None,
                    contact_preference=None,
                ),
            )[1]
        )

        rc, output = self._stdout_for(
            admin_cli.cmd_customer_delete,
            argparse.Namespace(customer_id=customer["customer_code"]),
        )
        self.assertEqual(rc, 0)
        self.assertIn('"deleted": true', output.lower())

        rc, output = self._stdout_for(
            admin_cli.cmd_billing_delete,
            argparse.Namespace(billing_profile_id=billing["billing_code"]),
        )
        self.assertEqual(rc, 0)
        self.assertIn('"deleted": true', output.lower())

    def test_customer_usage_merge_and_billing_merge_commands(self) -> None:
        source_customer = json.loads(
            self._stdout_for(
                admin_cli.cmd_customer_create,
                argparse.Namespace(name="Source Customer", phone=None, address=None),
            )[1]
        )
        target_customer = json.loads(
            self._stdout_for(
                admin_cli.cmd_customer_create,
                argparse.Namespace(name="Target Customer", phone=None, address=None),
            )[1]
        )
        source_billing = json.loads(
            self._stdout_for(
                admin_cli.cmd_billing_create,
                argparse.Namespace(
                    billing_name="Source Billing",
                    billing_contact_name=None,
                    billing_address=None,
                    contact_preference=None,
                ),
            )[1]
        )
        target_billing = json.loads(
            self._stdout_for(
                admin_cli.cmd_billing_create,
                argparse.Namespace(
                    billing_name="Target Billing",
                    billing_contact_name=None,
                    billing_address=None,
                    contact_preference=None,
                ),
            )[1]
        )
        self._stdout_for(
            admin_cli.cmd_job_create,
            argparse.Namespace(
                job_id="job_4",
                job_number="J0004",
                customer_id=source_customer["customer_id"],
                billing_profile_id=source_billing["billing_profile_id"],
                tree_number="1",
                job_name="Merge Test",
                job_address=None,
                reason=None,
                location_notes=None,
                tree_species=None,
                status="DRAFT",
            ),
        )

        rc, output = self._stdout_for(
            admin_cli.cmd_customer_usage,
            argparse.Namespace(customer_id=source_customer["customer_code"]),
        )
        self.assertEqual(rc, 0)
        usage = json.loads(output)
        self.assertEqual(usage["job_numbers"], ["J0004"])
        self.assertEqual(usage["jobs"][0]["billing_code"], source_billing["billing_code"])

        rc, output = self._stdout_for(
            admin_cli.cmd_customer_merge,
            argparse.Namespace(
                customer_id=source_customer["customer_code"],
                into=target_customer["customer_code"],
            ),
        )
        self.assertEqual(rc, 0)
        merge_result = json.loads(output)
        self.assertEqual(merge_result["moved_job_count"], 1)

        rc, output = self._stdout_for(
            admin_cli.cmd_billing_merge,
            argparse.Namespace(
                billing_profile_id=source_billing["billing_code"],
                into=target_billing["billing_code"],
            ),
        )
        self.assertEqual(rc, 0)
        billing_result = json.loads(output)
        self.assertEqual(billing_result["moved_job_count"], 1)

        updated_job = admin_cli._job_mutation_service().update_job("J0004")
        self.assertIsNotNone(updated_job)
        self.assertEqual(updated_job["customer_id"], target_customer["customer_id"])
        self.assertEqual(updated_job["billing_profile_id"], target_billing["billing_profile_id"])

        rc, output = self._stdout_for(
            admin_cli.cmd_billing_usage,
            argparse.Namespace(billing_profile_id=target_billing["billing_code"]),
        )
        self.assertEqual(rc, 0)
        billing_usage = json.loads(output)
        self.assertEqual(billing_usage["jobs"][0]["customer_code"], target_customer["customer_code"])

    def test_job_create_and_update_commands(self) -> None:
        customer = json.loads(
            self._stdout_for(
                admin_cli.cmd_customer_create,
                argparse.Namespace(
                    name="Test Customer",
                    phone=None,
                    address=None,
                ),
            )[1]
        )
        billing = json.loads(
            self._stdout_for(
                admin_cli.cmd_billing_create,
                argparse.Namespace(
                    billing_name="Test Billing",
                    billing_contact_name=None,
                    billing_address=None,
                    contact_preference=None,
                ),
            )[1]
        )

        rc, output = self._stdout_for(
            admin_cli.cmd_job_create,
            argparse.Namespace(
                job_id="job_1",
                job_number="J0001",
                customer_id=customer["customer_id"],
                billing_profile_id=billing["billing_profile_id"],
                tree_number="3",
                job_name="Valley Oak",
                job_address="123 Oak St",
                reason="Inspection",
                location_notes="Near sidewalk",
                tree_species="Quercus lobata",
                status="DRAFT",
            ),
        )
        self.assertEqual(rc, 0)
        created_job = json.loads(output)
        self.assertEqual(created_job["job_number"], "J0001")
        self.assertEqual(created_job["tree_number"], 3)

        rc, output = self._stdout_for(
            admin_cli.cmd_job_update,
            argparse.Namespace(
                job="J0001",
                customer_id=None,
                billing_profile_id=None,
                tree_number="4",
                job_name="Valley Oak Revisit",
                job_address=None,
                reason=None,
                location_notes="Back lot",
                tree_species=None,
                status="REVIEW_RETURNED",
            ),
        )
        self.assertEqual(rc, 0)
        updated_job = json.loads(output)
        self.assertEqual(updated_job["job_name"], "Valley Oak Revisit")
        self.assertEqual(updated_job["tree_number"], 4)
        self.assertEqual(updated_job["status"], "REVIEW_RETURNED")

    def test_normalize_repl_tokens_strips_optional_leading_slash(self) -> None:
        self.assertEqual(
            admin_cli._normalize_repl_tokens(
                "/round reopen --job-id job_1 --round-id round_1"
            ),
            ["round", "reopen", "--job-id", "job_1", "--round-id", "round_1"],
        )
        self.assertEqual(
            admin_cli._normalize_repl_tokens("job inspect --job J0001"),
            ["job", "inspect", "--job", "J0001"],
        )

    def test_repl_http_defaults_apply_only_to_http_commands(self) -> None:
        self.assertEqual(
            admin_cli._inject_repl_defaults(
                ["job", "inspect", "--job", "J0001"],
                host="http://127.0.0.1:8000",
                api_key="demo-key",
            ),
            ["job", "inspect", "--job", "J0001"],
        )
        self.assertEqual(
            admin_cli._inject_repl_defaults(
                ["job", "assign", "--job", "J0001", "--device-id", "device-1"],
                host="http://127.0.0.1:8000",
                api_key="demo-key",
            ),
            [
                "job",
                "assign",
                "--job",
                "J0001",
                "--device-id",
                "device-1",
                "--host",
                "http://127.0.0.1:8000",
                "--api-key",
                "demo-key",
            ],
        )

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

    def test_final_set_final_and_set_correction_commands(self) -> None:
        customer = json.loads(
            self._stdout_for(
                admin_cli.cmd_customer_create,
                argparse.Namespace(name="Test Customer", phone=None, address=None),
            )[1]
        )
        self._stdout_for(
            admin_cli.cmd_job_create,
            argparse.Namespace(
                job_id="job_9",
                job_number="J0009",
                customer_id=customer["customer_id"],
                billing_profile_id=None,
                tree_number="1",
                job_name="Archive Test",
                job_address=None,
                reason=None,
                location_notes=None,
                tree_species=None,
                status="DRAFT",
            ),
        )

        final_path = self.storage_root / "final_payload.json"
        final_path.write_text(
            json.dumps({"round_id": "round_1", "transcript": "Final transcript"}),
            encoding="utf-8",
        )
        correction_path = self.storage_root / "correction_payload.json"
        correction_path.write_text(
            json.dumps({"round_id": "round_2", "transcript": "Correction transcript"}),
            encoding="utf-8",
        )
        geojson_path = self.storage_root / "final_geojson.json"
        geojson_path.write_text(
            json.dumps({"type": "FeatureCollection", "features": []}),
            encoding="utf-8",
        )

        rc, output = self._stdout_for(
            admin_cli.cmd_final_set_final,
            argparse.Namespace(
                job="J0009",
                from_json=str(final_path),
                geojson_json=str(geojson_path),
            ),
        )
        self.assertEqual(rc, 0)
        final_result = json.loads(output)
        self.assertEqual(final_result["kind"], "final")
        self.assertTrue(final_result["has_geojson"])

        rc, output = self._stdout_for(
            admin_cli.cmd_final_set_correction,
            argparse.Namespace(
                job="J0009",
                from_json=str(correction_path),
                geojson_json=None,
            ),
        )
        self.assertEqual(rc, 0)
        correction_result = json.loads(output)
        self.assertEqual(correction_result["kind"], "correction")
        self.assertEqual(correction_result["round_id"], "round_2")


if __name__ == "__main__":
    unittest.main()
