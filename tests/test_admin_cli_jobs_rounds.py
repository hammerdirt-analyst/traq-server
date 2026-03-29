"""Job, round, review, and final CLI coverage."""

from __future__ import annotations

import argparse
import json
from unittest.mock import patch

from tests.admin_cli_support import AdminCliTestCase, admin_cli


class AdminCliJobsRoundsTests(AdminCliTestCase):
    @patch("admin_cli._http")
    def test_job_list_assignments(self, http_mock) -> None:
        http_mock.return_value = (200, {"assignments": [{"job_id": "job_1", "device_id": "device-1"}]})
        rc, output = self._stdout_for(admin_cli.cmd_job_list_assignments, argparse.Namespace(host="http://127.0.0.1:8000", api_key="demo-key", raw=False))
        self.assertEqual(rc, 0)
        self.assertIn('"job_id": "job_1"', output)
        http_mock.assert_called_once()

    @patch("admin_cli._http")
    def test_job_assign_unassign_and_set_status(self, http_mock) -> None:
        http_mock.return_value = (200, {"ok": True})
        self._register_pending_device("device-1")

        rc, output = self._stdout_for(admin_cli.cmd_job_assign, argparse.Namespace(job="job_1", device_id="device-1", host="http://127.0.0.1:8000", api_key="demo-key"))
        self.assertEqual(rc, 0)
        self.assertIn('"ok": true', output.lower())

        rc, _ = self._stdout_for(admin_cli.cmd_job_unassign, argparse.Namespace(job="job_1", host="http://127.0.0.1:8000", api_key="demo-key"))
        self.assertEqual(rc, 0)

        rc, _ = self._stdout_for(admin_cli.cmd_job_set_status, argparse.Namespace(job="job_1", status="REVIEW_RETURNED", round_id="round_1", round_status="REVIEW_RETURNED", host="http://127.0.0.1:8000", api_key="demo-key"))
        self.assertEqual(rc, 0)
        self.assertEqual(http_mock.call_count, 3)

    @patch("admin_cli._http")
    def test_job_unlock(self, http_mock) -> None:
        http_mock.return_value = (200, {"ok": True, "status": "DRAFT"})
        self._register_pending_device("device-1")
        rc, output = self._stdout_for(admin_cli.cmd_job_unlock, argparse.Namespace(job="job_1", round_id="round_2", device_id="device-1", host="http://127.0.0.1:8000", api_key="demo-key"))
        self.assertEqual(rc, 0)
        self.assertIn('"status": "DRAFT"', output)

    @patch("admin_cli._inspection_service")
    def test_resolve_job_id_uses_db_store(self, inspection_mock) -> None:
        self.store.upsert_job(job_id="job_1", job_number="J0001", status="DRAFT", details={"job_name": "Customer Tree"})
        inspection_mock.return_value = self.inspection_service
        resolved = admin_cli._resolve_job_id("http://127.0.0.1:8000", "demo-key", "J0001")
        self.assertEqual(resolved, "job_1")

    @patch("admin_cli._http")
    def test_round_reopen(self, http_mock) -> None:
        http_mock.return_value = (200, {"ok": True, "status": "DRAFT"})
        rc, output = self._stdout_for(admin_cli.cmd_round_reopen, argparse.Namespace(job_id="job_1", round_id="round_2", host="http://127.0.0.1:8000", api_key="demo-key"))
        self.assertEqual(rc, 0)
        self.assertIn('"status": "DRAFT"', output)

    def test_round_create_local(self) -> None:
        customer = json.loads(self._stdout_for(admin_cli.cmd_customer_create, argparse.Namespace(name="Customer Tree Owner", phone=None, address=None))[1])
        self._stdout_for(admin_cli.cmd_job_create, argparse.Namespace(job_id="job_1", job_number="J0001", customer_id=customer["customer_id"], billing_profile_id=None, tree_number="4", job_name="Customer Tree", job_address="123 Oak St", reason=None, location_notes=None, tree_species=None, status="DRAFT"))

        rc, output = self._stdout_for(admin_cli.cmd_round_create, argparse.Namespace(job="J0001"))
        self.assertEqual(rc, 0)
        payload = json.loads(output)
        self.assertEqual(payload["round_id"], "round_1")
        self.assertEqual(payload["status"], "DRAFT")
        job = self.store.get_job("job_1")
        self.assertEqual(job["latest_round_id"], "round_1")
        self.assertEqual(job["latest_round_status"], "DRAFT")

    @patch("admin_cli._http")
    def test_round_create_remote(self, http_mock) -> None:
        http_mock.side_effect = [(200, {"ok": True, "job_id": "job_1", "job_number": "J0001", "status": "DRAFT"}), (200, {"round_id": "round_1", "status": "DRAFT"})]
        rc, output = self._stdout_for(admin_cli.cmd_round_create, argparse.Namespace(job="J0001", host="https://example.test", api_key="demo-key"))
        self.assertEqual(rc, 0)
        self.assertIn('"round_id": "round_1"', output)

    def test_round_manifest_get_and_set_local(self) -> None:
        customer = json.loads(self._stdout_for(admin_cli.cmd_customer_create, argparse.Namespace(name="Customer Tree Owner", phone=None, address=None))[1])
        self._stdout_for(admin_cli.cmd_job_create, argparse.Namespace(job_id="job_1", job_number="J0001", customer_id=customer["customer_id"], billing_profile_id=None, tree_number="4", job_name="Customer Tree", job_address="123 Oak St", reason=None, location_notes=None, tree_species=None, status="DRAFT"))
        self._stdout_for(admin_cli.cmd_round_create, argparse.Namespace(job="J0001"))
        manifest_path = self.storage_root / "manifest.json"
        manifest_path.write_text(json.dumps([{"artifact_id": "rec_1", "section_id": "site_factors", "client_order": 0, "kind": "recording"}]), encoding="utf-8")

        rc, output = self._stdout_for(admin_cli.cmd_round_manifest_set, argparse.Namespace(job="J0001", round_id="round_1", file=str(manifest_path)))
        self.assertEqual(rc, 0)
        self.assertIn('"manifest_count": 1', output)

        rc, output = self._stdout_for(admin_cli.cmd_round_manifest_get, argparse.Namespace(job="J0001", round_id="round_1"))
        self.assertEqual(rc, 0)
        self.assertIn('"artifact_id": "rec_1"', output)

    @patch("admin_cli._http")
    def test_round_manifest_get_and_set_remote(self, http_mock) -> None:
        manifest_path = self.storage_root / "manifest_remote.json"
        manifest_path.write_text(json.dumps([{"artifact_id": "rec_1", "section_id": "site_factors", "client_order": 0, "kind": "recording"}]), encoding="utf-8")
        http_mock.side_effect = [
            (200, {"ok": True, "job_id": "job_1", "job_number": "J0001", "status": "DRAFT"}),
            (200, {"ok": True, "round_id": "round_1", "manifest_count": 1}),
            (200, {"ok": True, "job_id": "job_1", "job_number": "J0001", "status": "DRAFT"}),
            (200, {"ok": True, "round_id": "round_1", "manifest": [{"artifact_id": "rec_1"}], "manifest_count": 1}),
        ]

        rc, output = self._stdout_for(admin_cli.cmd_round_manifest_set, argparse.Namespace(job="J0001", round_id="round_1", file=str(manifest_path), host="https://example.test", api_key="demo-key"))
        self.assertEqual(rc, 0)
        self.assertIn('"manifest_count": 1', output)

        rc, output = self._stdout_for(admin_cli.cmd_round_manifest_get, argparse.Namespace(job="J0001", round_id="round_1", host="https://example.test", api_key="demo-key"))
        self.assertEqual(rc, 0)
        self.assertIn('"artifact_id": "rec_1"', output)

    def test_round_submit_local_is_explicitly_unsupported(self) -> None:
        submit_path = self.storage_root / "submit_local.json"
        submit_path.write_text(json.dumps({"client_revision_id": "cli-local", "form": {"data": {}}, "narrative": {"text": ""}}), encoding="utf-8")
        rc, output = self._stdout_for(admin_cli.cmd_round_submit, argparse.Namespace(job="J0001", round_id="round_1", file=str(submit_path)))
        self.assertEqual(rc, 1)
        self.assertIn("not available in local mode yet", output)

    @patch("admin_cli._http")
    def test_round_submit_remote(self, http_mock) -> None:
        submit_path = self.storage_root / "submit_remote.json"
        submit_path.write_text(json.dumps({"client_revision_id": "cli-remote", "form": {"data": {}}, "narrative": {"text": ""}}), encoding="utf-8")
        http_mock.side_effect = [
            (200, {"ok": True, "job_id": "job_1", "job_number": "J0001", "status": "DRAFT"}),
            (200, {"ok": True, "accepted": True, "round_id": "round_1", "status": "REVIEW_RETURNED", "processed_count": 1, "failed_count": 0}),
        ]
        rc, output = self._stdout_for(admin_cli.cmd_round_submit, argparse.Namespace(job="J0001", round_id="round_1", file=str(submit_path), host="https://example.test", api_key="demo-key"))
        self.assertEqual(rc, 0)
        self.assertIn('"accepted": true', output.lower())
        self.assertIn('"status": "REVIEW_RETURNED"', output)

    def test_round_reprocess_local_is_explicitly_unsupported(self) -> None:
        rc, output = self._stdout_for(admin_cli.cmd_round_reprocess, argparse.Namespace(job="J0001", round_id="round_1"))
        self.assertEqual(rc, 1)
        self.assertIn("not available in local mode yet", output)

    @patch("admin_cli._http")
    def test_round_reprocess_remote(self, http_mock) -> None:
        http_mock.side_effect = [
            (200, {"ok": True, "job_id": "job_1", "job_number": "J0001", "status": "REVIEW_RETURNED"}),
            (200, {"ok": True, "round_id": "round_1", "status": "REVIEW_RETURNED", "manifest_count": 1, "transcription_failures": []}),
        ]
        rc, output = self._stdout_for(admin_cli.cmd_round_reprocess, argparse.Namespace(job="J0001", round_id="round_1", host="https://example.test", api_key="demo-key"))
        self.assertEqual(rc, 0)
        self.assertIn('"manifest_count": 1', output)
        self.assertIn('"status": "REVIEW_RETURNED"', output)

    @patch("admin_cli._inspection_service")
    def test_job_round_review_and_final_inspect_commands(self, inspection_mock) -> None:
        customer = json.loads(self._stdout_for(admin_cli.cmd_customer_create, argparse.Namespace(name="Customer Tree Owner", phone=None, address=None))[1])
        self._stdout_for(admin_cli.cmd_job_create, argparse.Namespace(job_id="job_1", job_number="J0001", customer_id=customer["customer_id"], billing_profile_id=None, tree_number="4", job_name="Customer Tree", job_address="123 Oak St", reason=None, location_notes=None, tree_species=None, status="REVIEW_RETURNED"))
        job_dir = self.storage_root / "jobs" / "job_1"
        round_dir = job_dir / "rounds" / "round_1"
        round_dir.mkdir(parents=True, exist_ok=True)
        (round_dir / "manifest.json").write_text(json.dumps([{"artifact_id": "rec_1", "kind": "recording"}]), encoding="utf-8")
        (round_dir / "review.json").write_text(json.dumps({"server_revision_id": "rev_round_1", "tree_number": 4, "transcript": "Transcript ready.", "section_transcripts": {"client_tree_details": "hello"}, "images": [], "draft_form": {"schema_name": "demo", "schema_version": "0.0", "data": {"client_tree_details": {"tree_number": "4"}}}}), encoding="utf-8")
        (job_dir / "final.json").write_text(json.dumps({"round_id": "round_1", "user_name": "Roger", "transcript": "Final transcript", "report_images": []}), encoding="utf-8")
        (job_dir / "final_traq_page1.pdf").write_text("pdf", encoding="utf-8")
        (job_dir / "final_report_letter.pdf").write_text("pdf", encoding="utf-8")
        (job_dir / "final.geojson").write_text("{}", encoding="utf-8")
        inspection_mock.return_value = self.inspection_service

        rc, output = self._stdout_for(admin_cli.cmd_job_inspect, argparse.Namespace(job="J0001"))
        self.assertEqual(rc, 0)
        self.assertIn('"job_number": "J0001"', output)
        self.assertIn('"customer_code": "C0001"', output)

        rc, output = self._stdout_for(admin_cli.cmd_round_inspect, argparse.Namespace(job="J0001", round_id="round_1"))
        self.assertEqual(rc, 0)
        self.assertIn('"manifest_count": 1', output)

        rc, output = self._stdout_for(admin_cli.cmd_review_inspect, argparse.Namespace(job="J0001", round_id="round_1"))
        self.assertEqual(rc, 0)
        self.assertIn('"server_revision_id": "rev_round_1"', output)
        self.assertIn('"tree_number": 4', output)

        rc, output = self._stdout_for(admin_cli.cmd_final_inspect, argparse.Namespace(job="J0001"))
        self.assertEqual(rc, 0)
        self.assertIn('"exists": true', output.lower())
        self.assertIn('"report_pdf_exists": true', output.lower())

    def test_job_create_and_update_commands(self) -> None:
        customer = json.loads(self._stdout_for(admin_cli.cmd_customer_create, argparse.Namespace(name="Test Customer", phone=None, address=None))[1])
        billing = json.loads(self._stdout_for(admin_cli.cmd_billing_create, argparse.Namespace(billing_name="Test Billing", billing_contact_name=None, billing_address=None, contact_preference=None))[1])

        rc, output = self._stdout_for(admin_cli.cmd_job_create, argparse.Namespace(job_id="job_1", job_number="J0001", customer_id=customer["customer_id"], billing_profile_id=billing["billing_profile_id"], tree_number="3", job_name="Valley Oak", job_address="123 Oak St", reason="Inspection", location_notes="Near sidewalk", tree_species="Quercus lobata", status="DRAFT"))
        self.assertEqual(rc, 0)
        created_job = json.loads(output)
        self.assertEqual(created_job["job_number"], "J0001")
        self.assertEqual(created_job["tree_number"], 3)

        rc, output = self._stdout_for(admin_cli.cmd_job_update, argparse.Namespace(job="J0001", customer_id=None, billing_profile_id=None, tree_number="4", job_name="Valley Oak Revisit", job_address=None, reason=None, location_notes="Back lot", tree_species=None, status="REVIEW_RETURNED"))
        self.assertEqual(rc, 0)
        updated_job = json.loads(output)
        self.assertEqual(updated_job["job_name"], "Valley Oak Revisit")
        self.assertEqual(updated_job["tree_number"], 4)
        self.assertEqual(updated_job["status"], "REVIEW_RETURNED")

    def test_final_set_final_and_set_correction_commands(self) -> None:
        customer = json.loads(self._stdout_for(admin_cli.cmd_customer_create, argparse.Namespace(name="Test Customer", phone=None, address=None))[1])
        self._stdout_for(admin_cli.cmd_job_create, argparse.Namespace(job_id="job_9", job_number="J0009", customer_id=customer["customer_id"], billing_profile_id=None, tree_number="1", job_name="Archive Test", job_address=None, reason=None, location_notes=None, tree_species=None, status="DRAFT"))

        final_path = self.storage_root / "final_payload.json"
        final_path.write_text(json.dumps({"round_id": "round_1", "transcript": "Final transcript"}), encoding="utf-8")
        correction_path = self.storage_root / "correction_payload.json"
        correction_path.write_text(json.dumps({"round_id": "round_2", "transcript": "Correction transcript"}), encoding="utf-8")
        geojson_path = self.storage_root / "final_geojson.json"
        geojson_path.write_text(json.dumps({"type": "FeatureCollection", "features": []}), encoding="utf-8")

        rc, output = self._stdout_for(admin_cli.cmd_final_set_final, argparse.Namespace(job="J0009", from_json=str(final_path), geojson_json=str(geojson_path)))
        self.assertEqual(rc, 0)
        final_result = json.loads(output)
        self.assertEqual(final_result["kind"], "final")
        self.assertTrue(final_result["has_geojson"])

        rc, output = self._stdout_for(admin_cli.cmd_final_set_correction, argparse.Namespace(job="J0009", from_json=str(correction_path), geojson_json=None))
        self.assertEqual(rc, 0)
        correction_result = json.loads(output)
        self.assertEqual(correction_result["kind"], "correction")
        self.assertEqual(correction_result["round_id"], "round_2")
