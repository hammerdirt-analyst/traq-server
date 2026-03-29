"""Customer, billing, artifact, and tree identification CLI coverage."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import patch

from tests.admin_cli_support import AdminCliTestCase, admin_cli


class AdminCliCustomersArtifactsTests(AdminCliTestCase):
    @patch("admin_cli._http")
    def test_remote_customer_billing_and_job_mutation_commands(self, http_mock) -> None:
        http_mock.side_effect = [
            (200, {"ok": True, "customers": [{"customer_id": "cust_1", "customer_code": "C0001"}]}),
            (200, {"ok": True, "billing_profile": {"billing_profile_id": "bill_1", "billing_code": "B0001"}}),
            (200, {"ok": True, "job": {"job_id": "job_1", "job_number": "J0001", "status": "DRAFT"}}),
            (200, {"ok": True, "job": {"job_id": "job_1", "job_number": "J0001", "job_name": "Updated"}}),
        ]

        rc, output = self._stdout_for(admin_cli.cmd_customer_list, argparse.Namespace(search=None, json=True, host="https://example.test", api_key="demo-key"))
        self.assertEqual(rc, 0)
        self.assertIn('"customer_code": "C0001"', output)

        rc, output = self._stdout_for(admin_cli.cmd_billing_create, argparse.Namespace(billing_name="Billing A", billing_contact_name=None, billing_address=None, contact_preference=None, json=True, host="https://example.test", api_key="demo-key"))
        self.assertEqual(rc, 0)
        self.assertIn('"billing_code": "B0001"', output)

        rc, output = self._stdout_for(admin_cli.cmd_job_create, argparse.Namespace(job_id="job_1", job_number="J0001", status="DRAFT", customer_id=None, billing_profile_id=None, tree_number=None, job_name=None, job_address=None, reason=None, location_notes=None, tree_species=None, json=True, host="https://example.test", api_key="demo-key"))
        self.assertEqual(rc, 0)
        self.assertIn('"job_number": "J0001"', output)

        rc, output = self._stdout_for(admin_cli.cmd_job_update, argparse.Namespace(job="J0001", customer_id=None, billing_profile_id=None, tree_number=None, job_name="Updated", job_address=None, reason=None, location_notes=None, tree_species=None, status=None, json=True, host="https://example.test", api_key="demo-key"))
        self.assertEqual(rc, 0)
        self.assertIn('"job_name": "Updated"', output)

    @patch("admin_cli._http")
    def test_tree_identify_command(self, http_mock) -> None:
        leaf = self.storage_root / "leaf.jpg"
        leaf.write_bytes(b"jpeg")
        bark = self.storage_root / "bark.jpg"
        bark.write_bytes(b"jpeg")
        http_mock.return_value = (200, {"query": {}, "predictedOrgans": [{"organ": "leaf"}], "bestMatch": "Ajuga genevensis L.", "results": [{"score": 0.9}], "otherResults": [], "version": "2025-01-17 (7.3)", "remainingIdentificationRequests": 498})

        rc, output = self._stdout_for(admin_cli.cmd_tree_identify, argparse.Namespace(image=[str(leaf), str(bark)], organ=["leaf", "bark"], project="all", include_related_images=False, no_reject=False, host="https://example.test", api_key="demo-key"))
        self.assertEqual(rc, 0)
        self.assertIn('"bestMatch": "Ajuga genevensis L."', output)
        http_mock.assert_called_once()

    def test_customer_and_billing_commands(self) -> None:
        rc, output = self._stdout_for(admin_cli.cmd_customer_create, argparse.Namespace(name="Sacramento State Arboretum", phone="555-1212", address="6000 J St"))
        self.assertEqual(rc, 0)
        created_customer = json.loads(output)
        self.assertEqual(created_customer["customer_code"], "C0001")
        self.assertEqual(created_customer["name"], "Sacramento State Arboretum")

        rc, output = self._stdout_for(admin_cli.cmd_customer_list, argparse.Namespace(search="Arboretum"))
        self.assertEqual(rc, 0)
        listed_customers = json.loads(output)
        self.assertEqual(len(listed_customers), 1)

        rc, output = self._stdout_for(admin_cli.cmd_customer_update, argparse.Namespace(customer_id=created_customer["customer_id"], name=None, phone="555-3434", address=None))
        self.assertEqual(rc, 0)
        updated_customer = json.loads(output)
        self.assertEqual(updated_customer["phone"], "555-3434")

    def test_artifact_fetch_command_exports_report_pdf(self) -> None:
        service = admin_cli._job_mutation_service()
        final_service = admin_cli._final_mutation_service()
        service.create_job(job_id="job_artifact", job_number="J0010", status="ARCHIVED", customer_id=None, billing_profile_id=None, tree_number=None, job_name="Artifact Fetch", job_address="123 Export St", reason=None, location_notes=None, tree_species=None)
        final_service.set_final("J0010", payload={"round_id": "round_1", "transcript": "Final transcript"})
        job_dir = self.storage_root / "jobs" / "job_artifact"
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "final_report_letter.pdf").write_bytes(b"report-bytes")

        rc, output = self._stdout_for(admin_cli.cmd_artifact_fetch, argparse.Namespace(job="J0010", kind="report-pdf"))
        self.assertEqual(rc, 0)
        payload = json.loads(output)
        exported = Path(payload["saved_path"])
        self.assertTrue(exported.exists())
        self.assertEqual(exported.name, "J0010_report_letter.pdf")
        self.assertEqual(exported.read_bytes(), b"report-bytes")

    def test_artifact_fetch_command_exports_final_json(self) -> None:
        service = admin_cli._job_mutation_service()
        final_service = admin_cli._final_mutation_service()
        service.create_job(job_id="job_artifact_json", job_number="J0011", status="ARCHIVED", customer_id=None, billing_profile_id=None, tree_number=None, job_name="Artifact Json", job_address="124 Export St", reason=None, location_notes=None, tree_species=None)
        final_service.set_final("J0011", payload={"round_id": "round_1", "transcript": "Json transcript"})

        rc, output = self._stdout_for(admin_cli.cmd_artifact_fetch, argparse.Namespace(job="J0011", kind="final-json"))
        self.assertEqual(rc, 0)
        payload = json.loads(output)
        exported = Path(payload["saved_path"])
        self.assertTrue(exported.exists())
        self.assertEqual(exported.name, "J0011_final.json")
        exported_payload = json.loads(exported.read_text(encoding="utf-8"))
        self.assertEqual(exported_payload["transcript"], "Json transcript")

        rc, output = self._stdout_for(admin_cli.cmd_billing_create, argparse.Namespace(billing_name="City of Trees", billing_contact_name="A. Manager", billing_address="123 Elm", contact_preference="email"))
        self.assertEqual(rc, 0)
        created_billing = json.loads(output)
        self.assertEqual(created_billing["billing_code"], "B0001")
        self.assertEqual(created_billing["billing_name"], "City of Trees")

        rc, output = self._stdout_for(admin_cli.cmd_billing_list, argparse.Namespace(search="Trees"))
        self.assertEqual(rc, 0)
        listed_billing = json.loads(output)
        self.assertEqual(len(listed_billing), 1)

        rc, output = self._stdout_for(admin_cli.cmd_billing_update, argparse.Namespace(billing_profile_id=created_billing["billing_profile_id"], billing_name=None, billing_contact_name="B. Manager", billing_address=None, contact_preference="phone"))
        self.assertEqual(rc, 0)
        updated_billing = json.loads(output)
        self.assertEqual(updated_billing["billing_contact_name"], "B. Manager")
        self.assertEqual(updated_billing["contact_preference"], "phone")

    def test_artifact_fetch_command_exports_geo_json(self) -> None:
        service = admin_cli._job_mutation_service()
        final_service = admin_cli._final_mutation_service()
        service.create_job(job_id="job_artifact_geo", job_number="J0012", status="ARCHIVED", customer_id=None, billing_profile_id=None, tree_number=None, job_name="Artifact GeoJSON", job_address="125 Export St", reason=None, location_notes=None, tree_species=None)
        final_service.set_final("J0012", payload={"round_id": "round_1", "transcript": "Geo transcript"})
        job_dir = self.storage_root / "jobs" / "job_artifact_geo"
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "final.geojson").write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")

        rc, output = self._stdout_for(admin_cli.cmd_artifact_fetch, argparse.Namespace(job="J0012", kind="geo-json"))
        self.assertEqual(rc, 0)
        payload = json.loads(output)
        exported = Path(payload["saved_path"])
        self.assertTrue(exported.exists())
        self.assertEqual(exported.name, "J0012_final.geojson")
        exported_payload = json.loads(exported.read_text(encoding="utf-8"))
        self.assertEqual(exported_payload["type"], "FeatureCollection")

    def test_customer_and_billing_duplicates_commands(self) -> None:
        self._stdout_for(admin_cli.cmd_customer_create, argparse.Namespace(name="Test", phone="111", address=None))
        self._stdout_for(admin_cli.cmd_customer_create, argparse.Namespace(name=" Test ", phone="222", address=None))
        self._stdout_for(admin_cli.cmd_billing_create, argparse.Namespace(billing_name="Test Billing", billing_contact_name=None, billing_address=None, contact_preference=None))
        self._stdout_for(admin_cli.cmd_billing_create, argparse.Namespace(billing_name=" Test Billing ", billing_contact_name=None, billing_address=None, contact_preference=None))

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
        customer = json.loads(self._stdout_for(admin_cli.cmd_customer_create, argparse.Namespace(name="Delete Customer", phone=None, address=None))[1])
        billing = json.loads(self._stdout_for(admin_cli.cmd_billing_create, argparse.Namespace(billing_name="Delete Billing", billing_contact_name=None, billing_address=None, contact_preference=None))[1])

        rc, output = self._stdout_for(admin_cli.cmd_customer_delete, argparse.Namespace(customer_id=customer["customer_code"]))
        self.assertEqual(rc, 0)
        self.assertIn('"deleted": true', output.lower())

        rc, output = self._stdout_for(admin_cli.cmd_billing_delete, argparse.Namespace(billing_profile_id=billing["billing_code"]))
        self.assertEqual(rc, 0)
        self.assertIn('"deleted": true', output.lower())

    def test_customer_usage_merge_and_billing_merge_commands(self) -> None:
        source_customer = json.loads(self._stdout_for(admin_cli.cmd_customer_create, argparse.Namespace(name="Source Customer", phone=None, address=None))[1])
        target_customer = json.loads(self._stdout_for(admin_cli.cmd_customer_create, argparse.Namespace(name="Target Customer", phone=None, address=None))[1])
        source_billing = json.loads(self._stdout_for(admin_cli.cmd_billing_create, argparse.Namespace(billing_name="Source Billing", billing_contact_name=None, billing_address=None, contact_preference=None))[1])
        target_billing = json.loads(self._stdout_for(admin_cli.cmd_billing_create, argparse.Namespace(billing_name="Target Billing", billing_contact_name=None, billing_address=None, contact_preference=None))[1])
        self._stdout_for(admin_cli.cmd_job_create, argparse.Namespace(job_id="job_4", job_number="J0004", customer_id=source_customer["customer_id"], billing_profile_id=source_billing["billing_profile_id"], tree_number="1", job_name="Merge Test", job_address=None, reason=None, location_notes=None, tree_species=None, status="DRAFT"))

        rc, output = self._stdout_for(admin_cli.cmd_customer_usage, argparse.Namespace(customer_id=source_customer["customer_code"]))
        self.assertEqual(rc, 0)
        usage = json.loads(output)
        self.assertEqual(usage["job_numbers"], ["J0004"])
        self.assertEqual(usage["jobs"][0]["billing_code"], source_billing["billing_code"])

        rc, output = self._stdout_for(admin_cli.cmd_customer_merge, argparse.Namespace(customer_id=source_customer["customer_code"], into=target_customer["customer_code"]))
        self.assertEqual(rc, 0)
        merge_result = json.loads(output)
        self.assertEqual(merge_result["moved_job_count"], 1)

        rc, output = self._stdout_for(admin_cli.cmd_billing_merge, argparse.Namespace(billing_profile_id=source_billing["billing_code"], into=target_billing["billing_code"]))
        self.assertEqual(rc, 0)
        billing_result = json.loads(output)
        self.assertEqual(billing_result["moved_job_count"], 1)

        updated_job = admin_cli._job_mutation_service().update_job("J0004")
        self.assertIsNotNone(updated_job)
        self.assertEqual(updated_job["customer_id"], target_customer["customer_id"])
        self.assertEqual(updated_job["billing_profile_id"], target_billing["billing_profile_id"])

        rc, output = self._stdout_for(admin_cli.cmd_billing_usage, argparse.Namespace(billing_profile_id=target_billing["billing_code"]))
        self.assertEqual(rc, 0)
        billing_usage = json.loads(output)
        self.assertEqual(billing_usage["jobs"][0]["customer_code"], target_customer["customer_code"])
