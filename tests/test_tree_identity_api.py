"""Integration checks for the live tree identity API contract."""

from __future__ import annotations

import importlib
import asyncio
import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.routing import APIRoute
from starlette.requests import Request

from app import db as db_module
from app.db import create_schema
from app.db_store import DatabaseStore


class TreeIdentityApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.storage_root = Path(self.tempdir.name) / "storage"
        self.storage_root.mkdir(parents=True, exist_ok=True)
        self.database_path = self.storage_root / "test.db"
        self.old_env = {key: os.environ.get(key) for key in self._env_keys()}
        os.environ["TRAQ_API_KEY"] = "test-key"
        os.environ["TRAQ_STORAGE_ROOT"] = str(self.storage_root)
        os.environ["TRAQ_DATABASE_URL"] = f"sqlite:///{self.database_path}"
        self.addCleanup(self._restore_env)

        db_module._engine = None
        db_module._SessionLocal = None
        from app import service_discovery as discovery_module
        from app import main as main_module

        discovery_module.ServiceDiscoveryAdvertiser.start_in_background = lambda self: None
        discovery_module.ServiceDiscoveryAdvertiser.stop = lambda self: None
        self.main_module = importlib.reload(main_module)
        self.app = self.main_module.app
        create_schema()

    @staticmethod
    def _env_keys() -> tuple[str, ...]:
        return ("TRAQ_API_KEY", "TRAQ_STORAGE_ROOT", "TRAQ_DATABASE_URL")

    def _endpoint(self, path: str, method: str):
        for route in self.app.router.routes:
            if isinstance(route, APIRoute) and route.path == path and method in route.methods:
                return route.endpoint
        raise AssertionError(f"Endpoint not found: {method} {path}")

    def _restore_env(self) -> None:
        for key, value in self.old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        db_module._engine = None
        db_module._SessionLocal = None

    def _register_and_approve_device(self, device_id: str = "device-1") -> str:
        register_device = self._endpoint("/v1/auth/register-device", "POST")
        register_response = register_device(
            self.main_module.RegisterDeviceRequest(
                device_id=device_id,
                device_name="Pixel",
            )
        )
        self.assertTrue(register_response["ok"])
        store = DatabaseStore()
        store.approve_device(device_id)
        issue_token = self._endpoint("/v1/auth/token", "POST")
        token_response = issue_token(
            self.main_module.IssueTokenRequest(device_id=device_id),
        )
        self.assertTrue(token_response["ok"])
        return token_response["access_token"]

    def test_create_job_and_status_return_authoritative_tree_number(self) -> None:
        create_job = self._endpoint("/v1/jobs", "POST")
        payload = create_job(
            self.main_module.CreateJobRequest(
                customer_name="Customer A",
                tree_number=7,
                job_name="Job A",
                job_address="123 Oak St",
                job_phone="555-0100",
                contact_preference="text",
                billing_name="Customer A",
                billing_address="123 Oak St",
            ),
            x_api_key="test-key",
        )
        self.assertEqual(payload.tree_number, 7)

        get_job = self._endpoint("/v1/jobs/{job_id}", "GET")
        status_response = get_job(
            payload.job_id,
            x_api_key="test-key",
        )
        self.assertEqual(status_response.tree_number, 7)

    def test_create_job_allocates_job_numbers_from_db_counter(self) -> None:
        create_job = self._endpoint("/v1/jobs", "POST")
        first = create_job(
            self.main_module.CreateJobRequest(
                customer_name="Customer Seq 1",
                job_name="Customer Seq 1",
                job_address="123 Oak St",
                job_phone="555-0100",
                contact_preference="text",
                billing_name="Billing Seq 1",
                billing_address="123 Oak St",
            ),
            x_api_key="test-key",
        )
        second = create_job(
            self.main_module.CreateJobRequest(
                customer_name="Customer Seq 2",
                job_name="Customer Seq 2",
                job_address="456 Oak St",
                job_phone="555-0101",
                contact_preference="text",
                billing_name="Billing Seq 2",
                billing_address="456 Oak St",
            ),
            x_api_key="test-key",
        )

        self.assertEqual(first.job_number, "J0001")
        self.assertEqual(second.job_number, "J0002")

    def test_create_job_reuses_exact_customer_and_billing_identities(self) -> None:
        create_job = self._endpoint("/v1/jobs", "POST")
        first = create_job(
            self.main_module.CreateJobRequest(
                customer_name="Customer Exact",
                job_name="Customer Exact",
                job_address="123 Oak St",
                job_phone="555-0100",
                contact_preference="text",
                billing_name="Customer Exact Billing",
                billing_address="123 Oak St",
                billing_contact_name="Alex",
            ),
            x_api_key="test-key",
        )
        second = create_job(
            self.main_module.CreateJobRequest(
                customer_name="Customer Exact",
                job_name="Customer Exact",
                job_address="123 Oak St",
                job_phone="555-0100",
                contact_preference="text",
                billing_name="Customer Exact Billing",
                billing_address="123 Oak St",
                billing_contact_name="Alex",
            ),
            x_api_key="test-key",
        )

        store = DatabaseStore()
        first_job = store.get_job(first.job_id)
        second_job = store.get_job(second.job_id)
        self.assertIsNotNone(first_job)
        self.assertIsNotNone(second_job)
        self.assertEqual(first_job["customer_id"], second_job["customer_id"])
        self.assertEqual(first_job["billing_profile_id"], second_job["billing_profile_id"])

    def test_lookup_endpoints_return_customer_and_billing_prefill_rows(self) -> None:
        create_job = self._endpoint("/v1/jobs", "POST")
        create_job(
            self.main_module.CreateJobRequest(
                customer_name="Sacramento State Arboretum",
                job_name="Sacramento State Arboretum",
                job_address="Sacramento State University",
                job_phone="916 278 6011",
                contact_preference="text",
                billing_name="Sacramento State Arboretum",
                billing_address="Sacramento State University",
                billing_contact_name="Dr. Marina Laforgia",
            ),
            x_api_key="test-key",
        )

        list_customers = self._endpoint("/v1/customers", "GET")
        customer_rows = list_customers(query="Arboretum", x_api_key="test-key")
        self.assertEqual(len(customer_rows), 1)
        self.assertEqual(customer_rows[0].customer_name, "Sacramento State Arboretum")
        self.assertEqual(customer_rows[0].job_name, "Sacramento State Arboretum")
        self.assertEqual(customer_rows[0].job_address, "Sacramento State University")

        list_billing_profiles = self._endpoint("/v1/billing-profiles", "GET")
        billing_rows = list_billing_profiles(query="Arboretum", x_api_key="test-key")
        self.assertEqual(len(billing_rows), 1)
        self.assertEqual(billing_rows[0].billing_name, "Sacramento State Arboretum")
        self.assertEqual(billing_rows[0].billing_contact_name, "Dr. Marina Laforgia")

    def test_profile_endpoints_are_db_backed(self) -> None:
        token = self._register_and_approve_device("device-profile")
        put_profile = self._endpoint("/v1/profile", "PUT")
        get_profile = self._endpoint("/v1/profile", "GET")

        stored = put_profile(
            self.main_module.ProfilePayload(
                name="Roger Erismann",
                phone="916 699 1113",
                isa_number="WE-380138A",
            ),
            x_api_key=token,
        )
        self.assertEqual(stored.name, "Roger Erismann")

        identity_key = "device:device-profile"
        digest = hashlib.sha256(identity_key.encode("utf-8")).hexdigest()
        profile_path = self.storage_root / "profiles"
        profile_path.mkdir(parents=True, exist_ok=True)
        legacy_path = profile_path / f"{digest}.json"
        legacy_path.write_text(
            json.dumps(
                {
                    "name": "Wrong File Name",
                    "phone": "000",
                    "isa_number": "BAD",
                }
            ),
            encoding="utf-8",
        )

        fetched = get_profile(x_api_key=token)
        self.assertEqual(fetched.name, "Roger Erismann")
        self.assertEqual(fetched.phone, "916 699 1113")
        self.assertEqual(fetched.isa_number, "WE-380138A")

        store = DatabaseStore()
        self.assertEqual(
            store.get_runtime_profile(identity_key),
            {
                "name": "Roger Erismann",
                "phone": "916 699 1113",
                "isa_number": "WE-380138A",
                "correspondence_street": None,
                "correspondence_city": None,
                "correspondence_state": None,
                "correspondence_zip": None,
                "correspondence_email": None,
            },
        )

    def test_assigned_jobs_include_tree_number_for_device_created_jobs(self) -> None:
        token = self._register_and_approve_device()
        create_job = self._endpoint("/v1/jobs", "POST")
        create_response = create_job(
            self.main_module.CreateJobRequest(
                customer_name="Customer B",
                job_name="Job B",
                job_address="456 Pine St",
                job_phone="555-0200",
                contact_preference="call",
                billing_name="Customer B",
                billing_address="456 Pine St",
            ),
            x_api_key=token,
        )
        self.assertEqual(create_response.tree_number, 1)

        list_assigned_jobs = self._endpoint("/v1/jobs/assigned", "GET")
        assigned_jobs = list_assigned_jobs(x_api_key=token)
        self.assertEqual(len(assigned_jobs), 1)
        self.assertEqual(assigned_jobs[0].tree_number, 1)
        self.assertIsNone(assigned_jobs[0].latest_round_id)
        self.assertIsNone(assigned_jobs[0].review_payload)

    def test_assigned_jobs_include_resume_review_payload_when_latest_round_exists(self) -> None:
        token = self._register_and_approve_device("device-2")
        create_job = self._endpoint("/v1/jobs", "POST")
        create_response = create_job(
            self.main_module.CreateJobRequest(
                customer_name="Customer Resume",
                tree_number=3,
                job_name="Job Resume",
                job_address="999 Walnut St",
                job_phone="555-0400",
                contact_preference="text",
                billing_name="Customer Resume",
                billing_address="999 Walnut St",
            ),
            x_api_key=token,
        )

        create_round = self._endpoint("/v1/jobs/{job_id}/rounds", "POST")
        round_response = create_round(create_response.job_id, x_api_key=token)

        submit_round = self._endpoint("/v1/jobs/{job_id}/rounds/{round_id}/submit", "POST")
        submit_round(
            create_response.job_id,
            round_response.round_id,
            self.main_module.SubmitRoundRequest(
                form={
                    "schema_name": "demo",
                    "schema_version": "0.0",
                    "data": {"client_tree_details": {"tree_number": "3"}},
                },
                narrative={"text": "Resume test"},
            ),
            x_api_key=token,
        )

        list_assigned_jobs = self._endpoint("/v1/jobs/assigned", "GET")
        assigned_jobs = list_assigned_jobs(x_api_key=token)
        self.assertEqual(len(assigned_jobs), 1)
        assigned = assigned_jobs[0]
        self.assertEqual(assigned.latest_round_id, round_response.round_id)
        self.assertEqual(assigned.latest_round_status, "REVIEW_RETURNED")
        self.assertIsNotNone(assigned.server_revision_id)
        self.assertIsInstance(assigned.review_payload, dict)
        self.assertIn("draft_form", assigned.review_payload)
        self.assertEqual(assigned.review_payload.get("tree_number"), 3)

    def test_runtime_reads_refresh_job_metadata_from_db_not_file(self) -> None:
        token = self._register_and_approve_device("device-3")
        create_job = self._endpoint("/v1/jobs", "POST")
        create_response = create_job(
            self.main_module.CreateJobRequest(
                customer_name="Customer Refresh",
                job_name="Job Refresh",
                job_address="101 Refresh Ln",
                job_phone="555-0500",
                contact_preference="text",
                billing_name="Billing Original",
                billing_address="101 Refresh Ln",
            ),
            x_api_key=token,
        )

        create_round = self._endpoint("/v1/jobs/{job_id}/rounds", "POST")
        round_response = create_round(create_response.job_id, x_api_key=token)

        store = DatabaseStore()
        store.upsert_job(
            job_id=create_response.job_id,
            job_number=create_response.job_number,
            status="REVIEW_RETURNED",
            latest_round_id=round_response.round_id,
            latest_round_status="REVIEW_RETURNED",
            details={
                "job_id": create_response.job_id,
                "job_number": create_response.job_number,
                "status": "REVIEW_RETURNED",
                "customer_name": "Customer Refresh",
                "job_name": "Job Refresh Updated",
                "job_address": "500 Updated Ave",
                "job_phone": "555-0500",
                "billing_name": "Billing Original",
                "billing_address": "101 Refresh Ln",
                "latest_round_id": round_response.round_id,
                "latest_round_status": "REVIEW_RETURNED",
            },
        )

        job_record_path = (
            self.storage_root / "jobs" / create_response.job_id / "job_record.json"
        )
        payload = json.loads(job_record_path.read_text(encoding="utf-8"))
        payload["status"] = "DRAFT"
        payload["latest_round_id"] = None
        payload["latest_round_status"] = None
        payload["job_name"] = "Job Refresh Stale File"
        payload["job_address"] = "999 Wrong Ave"
        job_record_path.write_text(json.dumps(payload), encoding="utf-8")

        get_job = self._endpoint("/v1/jobs/{job_id}", "GET")
        status_response = get_job(create_response.job_id, x_api_key=token)
        self.assertEqual(status_response.status, "REVIEW_RETURNED")
        self.assertEqual(status_response.latest_round_id, round_response.round_id)
        self.assertEqual(status_response.latest_round_status, "REVIEW_RETURNED")

        list_assigned_jobs = self._endpoint("/v1/jobs/assigned", "GET")
        assigned_jobs = list_assigned_jobs(x_api_key=token)
        self.assertEqual(len(assigned_jobs), 1)
        self.assertEqual(assigned_jobs[0].job_name, "Job Refresh Updated")
        self.assertEqual(assigned_jobs[0].job_address, "500 Updated Ave")

    def test_final_submit_unassigns_job_from_device(self) -> None:
        token = self._register_and_approve_device("device-final")
        create_job = self._endpoint("/v1/jobs", "POST")
        create_response = create_job(
            self.main_module.CreateJobRequest(
                customer_name="Customer Final",
                job_name="Job Final",
                job_address="1 Final Way",
                job_phone="555-0600",
                contact_preference="text",
                billing_name="Customer Final",
                billing_address="1 Final Way",
            ),
            x_api_key=token,
        )

        create_round = self._endpoint("/v1/jobs/{job_id}/rounds", "POST")
        round_response = create_round(create_response.job_id, x_api_key=token)

        submit_round = self._endpoint("/v1/jobs/{job_id}/rounds/{round_id}/submit", "POST")
        submit_round(
            create_response.job_id,
            round_response.round_id,
            self.main_module.SubmitRoundRequest(
                form={
                    "schema_name": "demo",
                    "schema_version": "0.0",
                    "data": {"client_tree_details": {"tree_number": "1"}},
                },
                narrative={"text": "Ready for final"},
            ),
            x_api_key=token,
        )

        submit_final = self._endpoint("/v1/jobs/{job_id}/final", "POST")
        from app import report_letter as report_letter_module
        from app import geojson_export as geojson_export_module

        def _write_placeholder(path: str) -> None:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_bytes(b"placeholder")

        with (
            patch.object(report_letter_module, "polish_summary", return_value="summary"),
            patch.object(report_letter_module, "build_report_letter", return_value="letter"),
            patch.object(
                report_letter_module,
                "generate_report_letter_pdf",
                side_effect=lambda _text, output_path, **_kwargs: _write_placeholder(output_path),
            ),
            patch.object(
                report_letter_module,
                "generate_report_letter_docx",
                side_effect=lambda _text, output_path, **_kwargs: _write_placeholder(output_path),
            ),
            patch.object(
                geojson_export_module,
                "write_final_geojson",
                side_effect=lambda output_path, **_kwargs: _write_placeholder(str(output_path)),
            ),
        ):
            response = submit_final(
                create_response.job_id,
                self.main_module.FinalSubmitRequest(
                    round_id=round_response.round_id,
                    server_revision_id="server-rev-1",
                    client_revision_id="client-rev-1",
                    form={
                        "schema_name": "demo",
                        "schema_version": "0.0",
                        "data": {"client_tree_details": {"tree_number": 1}},
                    },
                    narrative={"text": "Final narrative"},
                    profile=self.main_module.ProfilePayload(name="Tester"),
                ),
                x_api_key=token,
            )
        self.assertTrue(str(response.path).endswith("final_traq_page1.pdf"))

        store = DatabaseStore()
        self.assertIsNone(store.get_job_assignment(create_response.job_id))
        archived_final = store.get_job_final(create_response.job_id, "final")
        self.assertIsNotNone(archived_final)
        self.assertEqual(archived_final["payload"]["transcript"], "")

        list_assigned_jobs = self._endpoint("/v1/jobs/assigned", "GET")
        assigned_jobs = list_assigned_jobs(x_api_key=token)
        self.assertEqual(assigned_jobs, [])

    def test_submit_and_review_surface_server_tree_number(self) -> None:
        create_job = self._endpoint("/v1/jobs", "POST")
        create_response = create_job(
            self.main_module.CreateJobRequest(
                customer_name="Customer C",
                tree_number=9,
                job_name="Job C",
                job_address="789 Cedar St",
                job_phone="555-0300",
                contact_preference="text",
                billing_name="Customer C",
                billing_address="789 Cedar St",
            ),
            x_api_key="test-key",
        )
        job_id = create_response.job_id

        create_round = self._endpoint("/v1/jobs/{job_id}/rounds", "POST")
        round_response = create_round(job_id, x_api_key="test-key")
        round_id = round_response.round_id

        review_path = self.storage_root / "jobs" / job_id / "rounds" / round_id / "review.json"
        review_path.parent.mkdir(parents=True, exist_ok=True)
        review_path.write_text(
            json.dumps(
                {
                    "draft_form": {
                        "schema_name": "demo",
                        "schema_version": "0.0",
                        "data": {},
                    },
                    "draft_narrative": "Existing review",
                    "form": {},
                    "narrative": "Existing review",
                }
            ),
            encoding="utf-8",
        )

        submit_round = self._endpoint("/v1/jobs/{job_id}/rounds/{round_id}/submit", "POST")
        submit_response = submit_round(job_id, round_id, None, x_api_key="test-key")
        self.assertEqual(submit_response["tree_number"], 9)

        review_path.write_text(
            json.dumps(
                {
                    "draft_form": {
                        "schema_name": "demo",
                        "schema_version": "0.0",
                        "data": {"client_tree_details": {"tree_number": "999"}},
                    },
                    "draft_narrative": "Stale file review",
                    "form": {"client_tree_details": {"tree_number": "999"}},
                    "narrative": "Stale file review",
                    "tree_number": 999,
                }
            ),
            encoding="utf-8",
        )

        get_review = self._endpoint("/v1/jobs/{job_id}/rounds/{round_id}/review", "GET")
        payload = get_review(job_id, round_id, x_api_key="test-key")
        self.assertEqual(payload["tree_number"], 9)
        self.assertEqual(
            payload["draft_form"]["data"]["client_tree_details"]["tree_number"],
            "9",
        )
        self.assertEqual(
            payload["form"]["client_tree_details"]["tree_number"],
            "9",
        )

    def test_recording_upload_persists_db_metadata_even_if_meta_file_is_stale(self) -> None:
        token = self._register_and_approve_device("device-audio")
        create_job = self._endpoint("/v1/jobs", "POST")
        create_response = create_job(
            self.main_module.CreateJobRequest(
                customer_name="Customer Audio",
                job_name="Job Audio",
                job_address="123 Audio St",
                job_phone="555-0666",
                contact_preference="text",
                billing_name="Customer Audio",
                billing_address="123 Audio St",
            ),
            x_api_key=token,
        )
        create_round = self._endpoint("/v1/jobs/{job_id}/rounds", "POST")
        round_response = create_round(create_response.job_id, x_api_key=token)

        async def receive() -> dict[str, object]:
            return {
                "type": "http.request",
                "body": b"fake audio bytes",
                "more_body": False,
            }

        request = Request(
            {
                "type": "http",
                "method": "PUT",
                "path": f"/v1/jobs/{create_response.job_id}/sections/site_factors/recordings/rec_1",
                "headers": [],
            },
            receive,
        )
        upload_recording = self._endpoint(
            "/v1/jobs/{job_id}/sections/{section_id}/recordings/{recording_id}",
            "PUT",
        )
        response = asyncio.run(
            upload_recording(
                create_response.job_id,
                "site_factors",
                "rec_1",
                request,
                content_type="audio/wav",
                x_api_key=token,
            )
        )
        self.assertTrue(response["ok"])

        meta_path = (
            self.storage_root
            / "jobs"
            / create_response.job_id
            / "sections"
            / "site_factors"
            / "recordings"
            / "rec_1.meta.json"
        )
        stale = json.loads(meta_path.read_text(encoding="utf-8"))
        stale["stored_path"] = "/tmp/wrong.wav"
        meta_path.write_text(json.dumps(stale), encoding="utf-8")

        store = DatabaseStore()
        recording = store.get_round_recording(
            job_id=create_response.job_id,
            round_id=round_response.round_id,
            section_id="site_factors",
            recording_id="rec_1",
        )
        self.assertIsNotNone(recording)
        self.assertEqual(recording["content_type"], "audio/wav")
        self.assertNotEqual(recording["metadata_json"].get("stored_path"), "/tmp/wrong.wav")
        self.assertEqual(
            recording["artifact_path"],
            f"jobs/{create_response.job_id}/sections/site_factors/recordings/rec_1.wav",
        )

    def test_image_upload_and_patch_persist_db_metadata_even_if_meta_file_is_stale(self) -> None:
        token = self._register_and_approve_device("device-image")
        create_job = self._endpoint("/v1/jobs", "POST")
        create_response = create_job(
            self.main_module.CreateJobRequest(
                customer_name="Customer Image",
                job_name="Job Image",
                job_address="123 Image St",
                job_phone="555-0777",
                contact_preference="text",
                billing_name="Customer Image",
                billing_address="123 Image St",
            ),
            x_api_key=token,
        )
        create_round = self._endpoint("/v1/jobs/{job_id}/rounds", "POST")
        round_response = create_round(create_response.job_id, x_api_key=token)

        async def receive() -> dict[str, object]:
            return {
                "type": "http.request",
                "body": b"fake image bytes",
                "more_body": False,
            }

        request = Request(
            {
                "type": "http",
                "method": "PUT",
                "path": f"/v1/jobs/{create_response.job_id}/sections/job_photos/images/img_1",
                "headers": [],
            },
            receive,
        )
        upload_image = self._endpoint(
            "/v1/jobs/{job_id}/sections/{section_id}/images/{image_id}",
            "PUT",
        )
        response = asyncio.run(
            upload_image(
                create_response.job_id,
                "job_photos",
                "img_1",
                request,
                content_type="image/jpeg",
                x_api_key=token,
            )
        )
        self.assertTrue(response["ok"])

        meta_path = (
            self.storage_root
            / "jobs"
            / create_response.job_id
            / "sections"
            / "job_photos"
            / "images"
            / "img_1.meta.json"
        )
        stale = json.loads(meta_path.read_text(encoding="utf-8"))
        stale["caption"] = "Wrong File Caption"
        meta_path.write_text(json.dumps(stale), encoding="utf-8")

        patch_image = self._endpoint(
            "/v1/jobs/{job_id}/sections/{section_id}/images/{image_id}",
            "PATCH",
        )
        patch_image(
            create_response.job_id,
            "job_photos",
            "img_1",
            {"caption": "Correct Caption", "gps": {"latitude": "38.5", "longitude": "-121.0"}},
            x_api_key=token,
        )

        store = DatabaseStore()
        image = store.get_round_image(
            job_id=create_response.job_id,
            round_id=round_response.round_id,
            section_id="job_photos",
            image_id="img_1",
        )
        self.assertIsNotNone(image)
        self.assertEqual(image["caption"], "Correct Caption")
        self.assertEqual(image["latitude"], "38.5")
        self.assertEqual(image["longitude"], "-121.0")
        self.assertNotEqual(image["metadata_json"].get("caption"), "Wrong File Caption")
        self.assertEqual(
            image["artifact_path"],
            f"jobs/{create_response.job_id}/sections/job_photos/images/img_1.jpg",
        )
        self.assertEqual(
            image["metadata_json"].get("report_image_path"),
            f"jobs/{create_response.job_id}/sections/job_photos/images/img_1.report.jpg",
        )

    def test_submit_uses_db_transcript_state_not_transcript_cache_file(self) -> None:
        token = self._register_and_approve_device("device-transcript")
        create_job = self._endpoint("/v1/jobs", "POST")
        create_response = create_job(
            self.main_module.CreateJobRequest(
                customer_name="Customer Transcript",
                job_name="Job Transcript",
                job_address="123 Transcript St",
                job_phone="555-0888",
                contact_preference="text",
                billing_name="Customer Transcript",
                billing_address="123 Transcript St",
            ),
            x_api_key=token,
        )
        create_round = self._endpoint("/v1/jobs/{job_id}/rounds", "POST")
        round_response = create_round(create_response.job_id, x_api_key=token)

        async def receive() -> dict[str, object]:
            return {
                "type": "http.request",
                "body": b"fake audio bytes",
                "more_body": False,
            }

        request = Request(
            {
                "type": "http",
                "method": "PUT",
                "path": f"/v1/jobs/{create_response.job_id}/sections/site_factors/recordings/rec_1",
                "headers": [],
            },
            receive,
        )
        upload_recording = self._endpoint(
            "/v1/jobs/{job_id}/sections/{section_id}/recordings/{recording_id}",
            "PUT",
        )
        asyncio.run(
            upload_recording(
                create_response.job_id,
                "site_factors",
                "rec_1",
                request,
                content_type="audio/wav",
                x_api_key=token,
            )
        )

        set_manifest = self._endpoint("/v1/jobs/{job_id}/rounds/{round_id}/manifest", "PUT")
        set_manifest(
            create_response.job_id,
            round_response.round_id,
            [
                self.main_module.ManifestItem(
                    artifact_id="rec_1",
                    section_id="site_factors",
                    kind="recording",
                )
            ],
            x_api_key=token,
        )

        transcript_path = (
            self.storage_root
            / "jobs"
            / create_response.job_id
            / "sections"
            / "site_factors"
            / "recordings"
            / "rec_1.transcript.txt"
        )
        transcript_path.write_text("WRONG FILE TRANSCRIPT", encoding="utf-8")

        processed_path = self.storage_root / "jobs" / create_response.job_id / "processed_artifacts.json"
        processed_path.write_text(
            json.dumps({"recordings": {"site_factors": ["wrong_rec"]}}),
            encoding="utf-8",
        )

        store = DatabaseStore()
        existing = store.get_round_recording(
            job_id=create_response.job_id,
            round_id=round_response.round_id,
            section_id="site_factors",
            recording_id="rec_1",
        )
        updated_meta = dict(existing["metadata_json"])
        updated_meta["transcript_text"] = "DB TRANSCRIPT"
        updated_meta["processed"] = True
        store.upsert_round_recording(
            job_id=create_response.job_id,
            round_id=round_response.round_id,
            section_id="site_factors",
            recording_id="rec_1",
            upload_status=existing["upload_status"],
            content_type=existing["content_type"],
            duration_ms=existing["duration_ms"],
            artifact_path=existing["artifact_path"],
            metadata_json=updated_meta,
        )

        self.main_module._run_extraction_core = lambda section_id, transcript: type(
            "ExtractionResult",
            (),
            {"model_dump": lambda self: {}},
        )()
        self.main_module._generate_summary = lambda **kwargs: "Generated summary"

        submit_round = self._endpoint("/v1/jobs/{job_id}/rounds/{round_id}/submit", "POST")
        submit_round(
            create_response.job_id,
            round_response.round_id,
            None,
            x_api_key=token,
        )

        get_review = self._endpoint("/v1/jobs/{job_id}/rounds/{round_id}/review", "GET")
        payload = get_review(create_response.job_id, round_response.round_id, x_api_key=token)
        self.assertIn("DB TRANSCRIPT", payload["transcript"])
        self.assertNotIn("WRONG FILE TRANSCRIPT", payload["transcript"])


if __name__ == "__main__":
    unittest.main()
