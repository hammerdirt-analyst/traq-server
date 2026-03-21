"""Focused router regression checks for extracted low-risk endpoints."""

from __future__ import annotations

import importlib
import asyncio
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi import HTTPException
from fastapi.routing import APIRoute

from app import db as db_module
from app.db import create_schema
from app.api.admin_routes import build_admin_router
from app.api.core_routes import build_core_router
from app.api.extraction_routes import build_extraction_router
from app.api.final_routes import build_final_router
from app.api.image_routes import build_image_router
from app.api.job_read_routes import build_job_read_router
from app.api.job_write_routes import build_job_write_router
from app.api.models import FinalSubmitRequest
from app.api.recording_routes import build_recording_router
from app.api.round_manifest_routes import build_round_manifest_router
from app.api.round_reprocess_routes import build_round_reprocess_router
from app.api.round_submit_routes import build_round_submit_router
from app.api.tree_identification_routes import build_tree_identification_router
from app.services.round_submit_service import RoundSubmitService


class ApiRouterTests(unittest.TestCase):
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
        create_schema()
        self.app = self.main_module.app

    @staticmethod
    def _env_keys() -> tuple[str, ...]:
        return ("TRAQ_API_KEY", "TRAQ_STORAGE_ROOT", "TRAQ_DATABASE_URL")

    def _restore_env(self) -> None:
        for key, value in self.old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        db_module._engine = None
        db_module._SessionLocal = None

    def _endpoint(self, path: str, method: str):
        for route in self.app.router.routes:
            if isinstance(route, APIRoute) and route.path == path and method in route.methods:
                return route.endpoint
        raise AssertionError(f"Endpoint not found: {method} {path}")

    def test_health_route_survives_router_extraction(self) -> None:
        health = self._endpoint("/health", "GET")
        payload = health()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["storage_root"], str(self.storage_root))

    def test_register_device_route_survives_router_extraction(self) -> None:
        register_device = self._endpoint("/v1/auth/register-device", "POST")
        payload = register_device(
            self.main_module.RegisterDeviceRequest(
                device_id="device-router",
                device_name="Pixel",
            )
        )
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["device_id"], "device-router")
        self.assertEqual(payload["status"], "pending")

    def test_extraction_and_summary_router_handlers_bind_supplied_dependencies(self) -> None:
        router = build_extraction_router(
            require_api_key=lambda key: {"api_key": key},
            run_extraction_logged=lambda section_id, transcript: type(
                "ExtractionResult",
                (),
                {"model_dump": lambda self: {"section_id": section_id, "transcript": transcript}},
            )(),
            generate_summary=lambda **kwargs: "Generated summary",
        )

        extract_site_factors = self._router_endpoint(router, "/v1/extract/site_factors", "POST")
        extract_payload = extract_site_factors(
            self.main_module.SiteFactorsRequest(transcript="wind exposure"),
            x_api_key="test-key",
        )
        self.assertEqual(extract_payload["section_id"], "site_factors")
        self.assertEqual(extract_payload["transcript"], "wind exposure")

        summary_endpoint = self._router_endpoint(router, "/v1/summary", "POST")
        summary_payload = summary_endpoint(
            self.main_module.SummaryRequest(form={"risk": "low"}, transcript="notes"),
            x_api_key="test-key",
        )
        self.assertEqual(summary_payload, {"summary": "Generated summary"})

    def test_core_router_builds_expected_endpoints(self) -> None:
        router = build_core_router(
            settings=type("Settings", (), {"storage_root": self.storage_root})(),
            logger=type("Logger", (), {"info": lambda *args, **kwargs: None})(),
            require_api_key=lambda key: {"api_key": key},
            register_device_record=lambda **kwargs: {"device_id": kwargs["device_id"], "status": "pending", "role": None},
            get_device_record=lambda device_id: None,
            issue_device_token_record=lambda **kwargs: {"access_token": "token"},
            load_runtime_profile=lambda identity: None,
            save_runtime_profile=lambda identity, payload: payload,
            identity_key=lambda auth, key: "identity",
            customer_service=type(
                "CustomerService",
                (),
                {
                    "list_customers": lambda self, search=None: [],
                    "list_billing_profiles": lambda self, search=None: [],
                },
            )(),
        )

        health = self._router_endpoint(router, "/health", "GET")
        payload = health()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["storage_root"], str(self.storage_root))

    def test_admin_router_builds_expected_endpoints(self) -> None:
        class DummyRound:
            def __init__(self, status: str = "REVIEW_RETURNED") -> None:
                self.status = status

        class DummyJob:
            def __init__(self) -> None:
                self.status = "REVIEW_RETURNED"
                self.rounds = {"round_1": DummyRound()}
                self.latest_round_id = "round_1"
                self.latest_round_status = "REVIEW_RETURNED"

        class DummyDbStore:
            def get_job_round(self, job_id, round_id):
                return None

            def list_devices(self, status=None):
                rows = [
                    {"device_id": "device-1", "status": "pending", "role": "arborist"},
                    {"device_id": "device-2", "status": "approved", "role": "admin"},
                ]
                if status:
                    rows = [row for row in rows if row["status"] == status]
                return rows

            def approve_device(self, device_id, role="arborist"):
                return {"device_id": device_id, "status": "approved", "role": role}

            def revoke_device(self, device_id):
                return {"device_id": device_id, "status": "revoked", "role": "arborist"}

            def issue_token(self, device_id, ttl_seconds=604800):
                return {"access_token": "token", "device_id": device_id, "ttl_seconds": ttl_seconds}

        record = DummyJob()
        saved: list[DummyJob] = []

        router = build_admin_router(
            require_api_key=lambda key, required_role=None: {"api_key": key, "role": required_role},
            ensure_job_record=lambda job_id: record,
            assign_job_record=lambda **kwargs: {"job_id": kwargs["job_id"], "device_id": kwargs["device_id"]},
            unassign_job_record=lambda job_id: {"job_id": job_id},
            list_job_assignments=lambda: [{"job_id": "job_1", "device_id": "device-1"}],
            save_job_record=lambda job: saved.append(job),
            db_store=DummyDbStore(),
            round_record_factory=lambda **kwargs: DummyRound(status=kwargs["status"]),
            logger=type("Logger", (), {"info": lambda *args, **kwargs: None})(),
        )

        list_devices = self._router_endpoint(router, "/v1/admin/devices", "GET")
        self.assertEqual(len(list_devices(x_api_key="test-key")["devices"]), 2)

        pending_devices = self._router_endpoint(router, "/v1/admin/devices/pending", "GET")
        self.assertEqual(len(pending_devices(x_api_key="test-key")["devices"]), 1)

        approve_device = self._router_endpoint(router, "/v1/admin/devices/{device_id}/approve", "POST")
        approved = approve_device("device-1", type("Payload", (), {"role": "admin"})(), x_api_key="test-key")
        self.assertEqual(approved["device"]["role"], "admin")

        revoke_device = self._router_endpoint(router, "/v1/admin/devices/{device_id}/revoke", "POST")
        revoked = revoke_device("device-1", x_api_key="test-key")
        self.assertEqual(revoked["device"]["status"], "revoked")

        issue_token = self._router_endpoint(router, "/v1/admin/devices/{device_id}/issue-token", "POST")
        token = issue_token("device-2", type("Payload", (), {"ttl_seconds": 900})(), x_api_key="test-key")
        self.assertEqual(token["access_token"], "token")

        assignments = self._router_endpoint(router, "/v1/admin/jobs/assignments", "GET")
        self.assertEqual(assignments(x_api_key="test-key")["assignments"][0]["job_id"], "job_1")

        reopen = self._router_endpoint(router, "/v1/admin/jobs/{job_id}/rounds/{round_id}/reopen", "POST")
        response = reopen("job_1", "round_1", x_api_key="test-key")
        self.assertTrue(response["ok"])
        self.assertEqual(record.status, "DRAFT")
        self.assertEqual(record.latest_round_status, "DRAFT")
        self.assertEqual(len(saved), 1)

        unlock = self._router_endpoint(router, "/v1/admin/jobs/{job_id}/unlock", "POST")
        response = unlock(
            "job_1",
            type("Payload", (), {"round_id": "round_1", "device_id": "device-1"})(),
            x_api_key="test-key",
        )
        self.assertTrue(response["ok"])
        self.assertEqual(response["assignment"]["device_id"], "device-1")

    def test_tree_identification_router_builds_expected_endpoint(self) -> None:
        router = build_tree_identification_router(
            require_api_key=lambda key: {"api_key": key},
            tree_identification_service=type(
                "TreeIdentificationService",
                (),
                {
                    "identify": lambda self, **kwargs: {
                        "query": {"project": kwargs.get("project") or "all"},
                        "predictedOrgans": [{"organ": "leaf"}],
                        "bestMatch": "Ajuga genevensis L.",
                        "results": [{"score": 0.9}],
                        "otherResults": [],
                        "version": "2025-01-17 (7.3)",
                        "remainingIdentificationRequests": 498,
                    }
                },
            )(),
            logger=type("Logger", (), {"info": lambda *args, **kwargs: None})(),
        )
        identify = self._router_endpoint(router, "/v1/trees/identify", "POST")

        class DummyUpload:
            filename = "leaf.jpg"
            content_type = "image/jpeg"

            async def read(self) -> bytes:
                return b"jpeg"

        async def invoke():
            return await identify(
                images=[
                    DummyUpload(),
                ],
                organs=["leaf"],
                project="all",
                include_related_images=False,
                no_reject=False,
                nb_results=3,
                lang="en",
                x_api_key="test-key",
            )

        result = asyncio.run(invoke())
        self.assertEqual(result["bestMatch"], "Ajuga genevensis L.")
        self.assertEqual(result["remainingIdentificationRequests"], 498)

    def test_job_read_router_builds_expected_endpoints(self) -> None:
        class DummyRound:
            def __init__(self) -> None:
                self.status = "REVIEW_RETURNED"
                self.server_revision_id = None

        class DummyJob:
            def __init__(self) -> None:
                self.status = "DRAFT"
                self.tree_number = 7
                self.rounds = {"round_1": DummyRound()}
                self.latest_round_id = "round_1"
                self.latest_round_status = "DRAFT"

        record = DummyJob()

        router = build_job_read_router(
            require_api_key=lambda key: type(
                "Auth",
                (),
                {"is_admin": False, "device_id": "device-1"},
            )(),
            assert_job_assignment=lambda job_id, auth: None,
            ensure_job_record=lambda job_id: record,
            list_job_assignments=lambda: [{"job_id": "job_1", "device_id": "device-1"}],
            resolve_assigned_job=lambda job_id: self.main_module.AssignedJob(
                job_id=job_id,
                job_number="J0001",
                status="DRAFT",
                customer_name="",
                address="",
                tree_species="",
                job_name="",
                job_address="",
                job_phone="",
                contact_preference="",
                billing_name="",
                billing_address="",
                latest_round_id="round_1",
                latest_round_status="DRAFT",
                tree_number=7,
                review_payload={},
            ),
            save_job_record=lambda job: None,
            save_round_record=lambda job_id, round_record, review_payload=None: None,
            review_payload_service=type(
                "ReviewService",
                (),
                {
                    "build_round_images": lambda self, rows: [{"image_id": "img_1"}],
                    "normalize_payload": lambda self, payload, **kwargs: {"ok": True, **payload, "images": kwargs["hydrated_images"]},
                    "build_default_payload": lambda self, **kwargs: {"round_id": kwargs["round_id"], "images": kwargs["images"]},
                },
            )(),
            normalize_form_schema=lambda form: form,
            db_store=type(
                "DbStore",
                (),
                {
                    "get_job_round": lambda self, job_id, round_id: {"review_payload": {"cached": True}},
                    "list_round_images": lambda self, job_id, round_id: [{"image_id": "img_1"}],
                },
            )(),
            logger=type("Logger", (), {"info": lambda *args, **kwargs: None})(),
        )

        list_assigned = self._router_endpoint(router, "/v1/jobs/assigned", "GET")
        assigned = list_assigned(x_api_key="test-key")
        self.assertEqual(len(assigned), 1)
        self.assertEqual(assigned[0].job_id, "job_1")

        get_job = self._router_endpoint(router, "/v1/jobs/{job_id}", "GET")
        status = get_job("job_1", x_api_key="test-key")
        self.assertEqual(status.tree_number, 7)

        get_review = self._router_endpoint(router, "/v1/jobs/{job_id}/rounds/{round_id}/review", "GET")
        review = get_review("job_1", "round_1", x_api_key="test-key")
        self.assertEqual(review["images"][0]["image_id"], "img_1")

    def test_job_write_router_builds_expected_endpoints(self) -> None:
        class DummyAuth:
            def __init__(self) -> None:
                self.device_id = "device-1"
                self.is_admin = False

        class DummyRound:
            def __init__(self, round_id: str, status: str) -> None:
                self.round_id = round_id
                self.status = status

        class DummyJob:
            def __init__(self) -> None:
                self.rounds = {}
                self.latest_round_id = None
                self.latest_round_status = None
                self.status = "DRAFT"

        jobs: dict[str, object] = {}
        loaded_record = DummyJob()

        class DummyCustomerService:
            def get_or_create_customer(self, **kwargs):
                return {"customer_id": "cust_1"}

            def get_or_create_billing_profile(self, **kwargs):
                return {"billing_profile_id": "bill_1"}

        class DummyJobMutationService:
            def create_job(self, **kwargs):
                return {
                    "customer_name": "Customer A",
                    "tree_number": 7,
                    "address": "123 Oak",
                    "job_name": "Job A",
                    "job_address": "123 Oak",
                    "job_phone": "555",
                    "contact_preference": "text",
                    "billing_name": "Billing",
                    "billing_address": "123 Oak",
                    "billing_contact_name": "Alex",
                    "location_notes": "Notes",
                }

        saved_rounds: list[tuple[str, object]] = []

        router = build_job_write_router(
            require_api_key=lambda key: DummyAuth(),
            jobs=jobs,
            next_job_number=lambda: "J0001",
            customer_service=DummyCustomerService(),
            job_mutation_service=DummyJobMutationService(),
            load_job_record=lambda job_id: loaded_record,
            assign_job_record=lambda **kwargs: {"job_id": kwargs["job_id"], "device_id": kwargs["device_id"]},
            save_job_record=lambda record: None,
            save_round_record=lambda job_id, round_record: saved_rounds.append((job_id, round_record)),
            round_record_factory=DummyRound,
            logger=type("Logger", (), {"info": lambda *args, **kwargs: None, "exception": lambda *args, **kwargs: None})(),
            uuid_hex_supplier=lambda: "abc123def456",
            assert_job_assignment=lambda job_id, auth: None,
            ensure_job_record=lambda job_id: loaded_record,
        )

        create_job = self._router_endpoint(router, "/v1/jobs", "POST")
        response = create_job(
            self.main_module.CreateJobRequest(
                customer_name="Customer A",
                tree_number=7,
                job_name="Job A",
                job_address="123 Oak",
                job_phone="555",
                contact_preference="text",
                billing_name="Billing",
                billing_address="123 Oak",
            ),
            x_api_key="test-key",
        )
        self.assertEqual(response.job_id, "job_abc123def456")
        self.assertIn(response.job_id, jobs)

        create_round = self._router_endpoint(router, "/v1/jobs/{job_id}/rounds", "POST")
        round_response = create_round("job_abc123def456", x_api_key="test-key")
        self.assertEqual(round_response.round_id, "round_1")
        self.assertEqual(loaded_record.latest_round_id, "round_1")
        self.assertEqual(saved_rounds[0][0], "job_abc123def456")

    def test_round_manifest_router_builds_expected_endpoint(self) -> None:
        class DummyRound:
            def __init__(self) -> None:
                self.manifest = []

        round_record = DummyRound()

        router = build_round_manifest_router(
            require_api_key=lambda key: object(),
            assert_job_assignment=lambda job_id, auth: None,
            ensure_round_record=lambda job_id, round_id: (object(), round_record),
            assert_round_editable=lambda record, round_id, auth, allow_correction=False: None,
            save_round_record=lambda job_id, round_record: None,
            logger=type("Logger", (), {"info": lambda *args, **kwargs: None})(),
        )

        set_manifest = self._router_endpoint(router, "/v1/jobs/{job_id}/rounds/{round_id}/manifest", "PUT")
        payload = set_manifest(
            "job_1",
            "round_1",
            [
                self.main_module.ManifestItem(
                    artifact_id="rec_1",
                    section_id="site_factors",
                    kind="recording",
                )
            ],
            x_api_key="test-key",
        )
        self.assertEqual(payload["manifest_count"], 1)
        self.assertEqual(round_record.manifest[0]["artifact_id"], "rec_1")

    def test_round_submit_router_builds_expected_endpoint(self) -> None:
        class DummyAuth:
            is_admin = False
            device_id = "device-1"

        class DummyRound:
            def __init__(self) -> None:
                self.status = "DRAFT"
                self.manifest = [{"artifact_id": "rec_1", "kind": "recording"}]
                self.server_revision_id = None

        class DummyJob:
            def __init__(self) -> None:
                self.job_name = "Job A"
                self.job_address = "123 Oak"
                self.job_phone = "555"
                self.contact_preference = "text"
                self.billing_name = "Billing"
                self.billing_address = "123 Oak"
                self.latest_round_status = "DRAFT"
                self.status = "DRAFT"
                self.tree_number = 7

        record = DummyJob()
        round_record = DummyRound()
        saved_reviews: list[dict[str, object] | None] = []

        router = build_round_submit_router(
            require_api_key=lambda key: DummyAuth(),
            assert_job_assignment=lambda job_id, auth: None,
            ensure_round_record=lambda job_id, round_id: (record, round_record),
            assert_round_editable=lambda record, round_id, auth, allow_correction=False: None,
            save_job_record=lambda record: None,
            save_round_record=lambda job_id, round_record, review_payload=None: saved_reviews.append(review_payload),
            requested_tree_number_from_form=lambda form: 7,
            resolve_server_tree_number=lambda record, requested_tree_number=None: requested_tree_number,
            apply_tree_number_to_form=lambda form, tree_number: {**form, "tree_number": tree_number},
            db_store=type(
                "DbStore",
                (),
                {"get_job_round": lambda self, job_id, round_id: {}, "list_round_images": lambda self, job_id, round_id: []},
            )(),
            build_reprocess_manifest=lambda job_id, round_record, review: [],
            load_latest_review=lambda job_id, exclude_round_id=None: {},
            apply_form_patch=lambda draft_form, form_patch: {**draft_form, **form_patch},
            normalize_form_schema=lambda form: form,
            process_round=lambda job_id, round_id, record, review: {"transcription_failures": [], "draft_form": {"data": {}}, "form": {}, "tree_number": 7},
            round_submit_service=RoundSubmitService(),
            logger=type("Logger", (), {"info": lambda *args, **kwargs: None, "exception": lambda *args, **kwargs: None})(),
        )

        submit_round = self._router_endpoint(router, "/v1/jobs/{job_id}/rounds/{round_id}/submit", "POST")
        payload = submit_round(
            "job_1",
            "round_1",
            self.main_module.SubmitRoundRequest(form={"risk": "low"}),
            x_api_key="test-key",
        )
        self.assertTrue(payload["accepted"])
        self.assertEqual(payload["processed_count"], 1)
        self.assertEqual(record.status, "REVIEW_RETURNED")

    def test_round_reprocess_router_builds_expected_endpoint(self) -> None:
        class DummyAuth:
            is_admin = False
            device_id = "device-1"

        class DummyRound:
            def __init__(self) -> None:
                self.status = "REVIEW_RETURNED"
                self.server_revision_id = None

        class DummyJob:
            def __init__(self) -> None:
                self.latest_round_status = "REVIEW_RETURNED"
                self.status = "REVIEW_RETURNED"
                self.tree_number = 7

        record = DummyJob()
        round_record = DummyRound()

        router = build_round_reprocess_router(
            require_api_key=lambda key: DummyAuth(),
            assert_job_assignment=lambda job_id, auth: None,
            ensure_round_record=lambda job_id, round_id: (record, round_record),
            db_store=type("DbStore", (), {"get_job_round": lambda self, job_id, round_id: {"review_payload": {"cached": True}}})(),
            build_reprocess_manifest=lambda job_id, round_record, review: [{"artifact_id": "rec_1"}],
            save_job_record=lambda record: None,
            load_latest_review=lambda job_id, exclude_round_id=None: {"draft_form": {}},
            process_round=lambda *args, **kwargs: {"transcription_failures": []},
            logger=type("Logger", (), {"info": lambda *args, **kwargs: None, "exception": lambda *args, **kwargs: None})(),
        )

        reprocess = self._router_endpoint(router, "/v1/jobs/{job_id}/rounds/{round_id}/reprocess", "POST")
        payload = reprocess("job_1", "round_1", x_api_key="test-key")
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["manifest_count"], 1)
        self.assertEqual(record.status, "REVIEW_RETURNED")

    def test_recording_router_builds_expected_endpoint(self) -> None:
        class DummyAuth:
            is_admin = False
            device_id = "device-1"

        class DummyJob:
            latest_round_id = "round_1"

        stored: dict[str, object] = {}
        written_file = self.storage_root / "fake.wav"

        class DummyArtifactStore:
            def write_bytes(self, key, payload):
                stored["artifact_key"] = key
                stored["payload"] = payload
                return written_file

        class DummyDbStore:
            def upsert_round_recording(self, **kwargs):
                stored["db_kwargs"] = kwargs

        class DummyMediaService:
            def guess_extension(self, content_type, default_ext):
                stored["content_type"] = content_type
                return ".wav"

            def probe_audio_metadata(self, file_path):
                stored["probed_path"] = file_path
                return {
                    "duration_ms": 1000,
                    "codec_name": "pcm_s16le",
                    "sample_rate": 16000,
                    "channels": 1,
                    "duration": 1.0,
                    "format_name": "wav",
                    "ffprobe_error": None,
                }

        class DummyRequest:
            async def body(self):
                return b"audio-bytes"

        router = build_recording_router(
            require_api_key=lambda key: DummyAuth(),
            assert_job_assignment=lambda job_id, auth: None,
            ensure_job_record=lambda job_id: DummyJob(),
            assert_job_editable=lambda record, auth, allow_correction=False: None,
            media_runtime_service=DummyMediaService(),
            job_artifact_key=lambda *parts: "/".join(parts),
            artifact_store=DummyArtifactStore(),
            db_store=DummyDbStore(),
            write_json=lambda path, payload: stored.setdefault("meta", payload),
            section_dir=lambda job_id, section_id: self.storage_root / job_id / section_id,
            log_event=lambda *args, **kwargs: stored.setdefault("logged", True),
        )

        upload_recording = self._router_endpoint(
            router,
            "/v1/jobs/{job_id}/sections/{section_id}/recordings/{recording_id}",
            "PUT",
        )
        payload = asyncio.run(
            upload_recording(
                "job_1",
                "site_factors",
                "rec_1",
                DummyRequest(),
                content_type="audio/wav",
                x_api_key="test-key",
            )
        )
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["recording_id"], "rec_1")
        self.assertEqual(
            stored["artifact_key"],
            "job_1/sections/site_factors/recordings/rec_1.wav",
        )
        self.assertEqual(stored["db_kwargs"]["round_id"], "round_1")
        self.assertEqual(stored["meta"]["recording_id"], "rec_1")
        self.assertTrue(stored["logged"])

    def test_image_router_builds_expected_endpoints(self) -> None:
        class DummyAuth:
            is_admin = False
            device_id = "device-1"

        class DummyJob:
            latest_round_id = "round_1"

        stored: dict[str, object] = {}
        written_file = self.storage_root / "img_1.jpg"

        class DummyArtifactStore:
            def write_bytes(self, key, payload):
                stored["artifact_key"] = key
                stored["payload"] = payload
                return written_file

        class DummyDbStore:
            def __init__(self) -> None:
                self.image_row = {
                    "upload_status": "uploaded",
                    "artifact_path": "job_1/sections/job_photos/images/img_1.jpg",
                    "metadata_json": {"stored_path": "job_1/sections/job_photos/images/img_1.jpg"},
                }

            def list_round_images(self, job_id, round_id):
                return []

            def upsert_round_image(self, **kwargs):
                stored.setdefault("upserts", []).append(kwargs)

            def get_round_image(self, **kwargs):
                return self.image_row

        class DummyMediaService:
            def guess_extension(self, content_type, default_ext):
                stored["content_type"] = content_type
                return ".jpg"

            def build_report_image_variant(self, source_path, output_path):
                stored["report_source"] = source_path
                stored["report_output"] = output_path
                return output_path, 42

        class DummyRequest:
            async def body(self):
                return b"image-bytes"

        db_store = DummyDbStore()
        router = build_image_router(
            require_api_key=lambda key: DummyAuth(),
            assert_job_assignment=lambda job_id, auth: None,
            ensure_job_record=lambda job_id: DummyJob(),
            assert_job_editable=lambda record, auth, allow_correction=False: None,
            media_runtime_service=DummyMediaService(),
            job_artifact_key=lambda *parts: "/".join(parts),
            materialize_artifact_path=lambda key: self.storage_root / key,
            artifact_store=DummyArtifactStore(),
            db_store=db_store,
            write_json=lambda path, payload: stored.setdefault("meta", payload),
            section_dir=lambda job_id, section_id: self.storage_root / job_id / section_id,
            log_event=lambda *args, **kwargs: stored.setdefault("logged", True),
            job_photos_section_id="job_photos",
        )

        upload_image = self._router_endpoint(
            router,
            "/v1/jobs/{job_id}/sections/{section_id}/images/{image_id}",
            "PUT",
        )
        upload_payload = asyncio.run(
            upload_image(
                "job_1",
                "job_photos",
                "img_1",
                DummyRequest(),
                content_type="image/jpeg",
                x_api_key="test-key",
            )
        )
        self.assertTrue(upload_payload["ok"])
        self.assertEqual(upload_payload["image_id"], "img_1")
        self.assertEqual(
            stored["artifact_key"],
            "job_1/sections/job_photos/images/img_1.jpg",
        )
        self.assertEqual(stored["upserts"][0]["round_id"], "round_1")
        self.assertEqual(stored["meta"]["report_bytes"], 42)

        patch_image = self._router_endpoint(
            router,
            "/v1/jobs/{job_id}/sections/{section_id}/images/{image_id}",
            "PATCH",
        )
        patch_payload = patch_image(
            "job_1",
            "job_photos",
            "img_1",
            {"caption": "Oak", "gps": {"latitude": "1", "longitude": "2"}},
            x_api_key="test-key",
        )
        self.assertTrue(patch_payload["ok"])
        self.assertEqual(patch_payload["payload"]["caption"], "Oak")
        self.assertEqual(stored["upserts"][1]["caption"], "Oak")
        self.assertEqual(stored["upserts"][1]["latitude"], "1")
        self.assertEqual(stored["upserts"][1]["longitude"], "2")

    def test_final_router_builds_expected_endpoints(self) -> None:
        class DummyAuth:
            is_admin = False
            device_id = "device-1"

        class DummyProfile:
            def model_dump(self):
                return {"name": "Arborist", "isa_number": "WE-1234A"}

        class DummyPayload:
            round_id = "round_1"
            server_revision_id = "srv-1"
            client_revision_id = "cli-1"
            form = {"data": {"tree_number": 7}}
            narrative = {"text": "Tree is stable."}
            profile = DummyProfile()

        class DummyJob:
            def __init__(self, job_id: str, job_number: str, status: str) -> None:
                self.job_id = job_id
                self.job_number = job_number
                self.status = status
                self.latest_round_id = "round_1"
                self.latest_round_status = "REVIEW_RETURNED"
                self.tree_number = None
                self.billing_name = "Billing"
                self.customer_name = "Customer"

        class DummyArtifactStore:
            def __init__(self, root: Path) -> None:
                self.root = root

            def stage_output(self, key):
                path = self.root / key
                path.parent.mkdir(parents=True, exist_ok=True)
                return path

            def commit_output(self, key, path):
                return path

        class DummyDbStore:
            def get_job_round(self, job_id, round_id):
                return {"review_payload": {"transcript": "Transcript text"}}

        class DummyFinalMutationService:
            def set_final(self, job_id, payload, geojson_payload=None):
                calls["final_payload"] = payload
                calls["geojson_payload"] = geojson_payload

        class DummyMediaService:
            def load_job_report_images(self, job_id, round_id):
                return [{"image_id": "img_1"}]

        calls: dict[str, object] = {}
        artifact_store = DummyArtifactStore(self.storage_root)
        jobs: dict[str, object] = {}
        report_pdf = self.storage_root / "job_1" / "final_report_letter.pdf"
        report_pdf.parent.mkdir(parents=True, exist_ok=True)
        report_pdf.write_bytes(b"%PDF-1.4")

        router = build_final_router(
            require_api_key=lambda key: DummyAuth(),
            assert_job_assignment=lambda job_id, auth: None,
            ensure_job_record=lambda job_id: DummyJob(job_id, "J0001", "REVIEW_RETURNED"),
            job_record_factory=DummyJob,
            jobs=jobs,
            db_store=DummyDbStore(),
            is_correction_mode=lambda job_id, record: False,
            logger=type("Logger", (), {"info": lambda *args, **kwargs: None, "exception": lambda *args, **kwargs: None})(),
            finalization_service=type(
                "FinalizationService",
                (),
                {
                    "transcript_from_review_payload": lambda self, payload: "Transcript text",
                    "artifact_names": lambda self, correction_mode: type(
                        "ArtifactNames",
                        (),
                        {
                            "pdf_name": "final_traq_page1.pdf",
                            "report_name": "final_report_letter.pdf",
                            "report_docx_name": "final_report_letter.docx",
                            "final_json_name": "final.json",
                            "geojson_name": "final.geojson",
                        },
                    )(),
                    "ensure_risk_defaults": lambda self, form, normalize_form_schema: form,
                    "build_job_info": lambda self, record: {"job_number": record.job_number},
                    "resolve_profile_payload": lambda self, profile_payload, fallback_loader: profile_payload,
                    "build_final_payload": lambda self, **kwargs: {
                        "form": kwargs["form"],
                        "transcript": kwargs["transcript"],
                    },
                },
            )(),
            artifact_store=artifact_store,
            job_artifact_key=lambda *parts: "/".join(parts),
            requested_tree_number_from_form=lambda form: 7,
            resolve_server_tree_number=lambda record, requested_tree_number=None: requested_tree_number,
            normalize_form_schema=lambda form: form,
            apply_tree_number_to_form=lambda form, tree_number: {**form, "tree_number": tree_number},
            save_job_record=lambda record: calls.setdefault("saved", []).append(record.status),
            identity_key=lambda auth, key: "identity",
            load_runtime_profile=lambda key: {"name": "Fallback"},
            media_runtime_service=DummyMediaService(),
            generate_traq_pdf=lambda form_data, output_path: Path(output_path).write_bytes(b"%PDF-1.4"),
            write_json=lambda path, payload: Path(path).write_text('{"ok": true}'),
            read_json=lambda path: {"type": "FeatureCollection"},
            final_mutation_service=DummyFinalMutationService(),
            unassign_job_record=lambda job_id: calls.setdefault("unassigned", job_id),
            materialize_artifact_path=lambda key: self.storage_root / key,
        )

        from app import geojson_export, report_letter

        old_polish_summary = report_letter.polish_summary
        old_build_report_letter = report_letter.build_report_letter
        old_generate_pdf = report_letter.generate_report_letter_pdf
        old_generate_docx = report_letter.generate_report_letter_docx
        old_geojson = geojson_export.write_final_geojson
        self.addCleanup(setattr, report_letter, "polish_summary", old_polish_summary)
        self.addCleanup(setattr, report_letter, "build_report_letter", old_build_report_letter)
        self.addCleanup(setattr, report_letter, "generate_report_letter_pdf", old_generate_pdf)
        self.addCleanup(setattr, report_letter, "generate_report_letter_docx", old_generate_docx)
        self.addCleanup(setattr, geojson_export, "write_final_geojson", old_geojson)

        report_letter.polish_summary = lambda narrative_text, form_data, transcript: "Summary"
        report_letter.build_report_letter = lambda **kwargs: "Letter"
        report_letter.generate_report_letter_pdf = lambda *args, **kwargs: Path(args[1]).write_bytes(b"%PDF-1.4")
        report_letter.generate_report_letter_docx = lambda *args, **kwargs: Path(args[1]).write_text("docx")
        geojson_export.write_final_geojson = lambda output_path, **kwargs: Path(output_path).write_text('{"type":"FeatureCollection"}')

        submit_final = self._router_endpoint(router, "/v1/jobs/{job_id}/final", "POST")
        response = submit_final("job_1", DummyPayload(), x_api_key="test-key")
        self.assertEqual(response.filename, "traq_page1.pdf")
        self.assertEqual(calls["unassigned"], "job_1")
        self.assertEqual(calls["final_payload"]["transcript"], "Transcript text")

        get_report = self._router_endpoint(router, "/v1/jobs/{job_id}/final/report", "GET")
        report_response = get_report("job_1", x_api_key="test-key")
        self.assertEqual(report_response.filename, "report_letter.pdf")

    def test_final_router_returns_conflict_for_duplicate_final(self) -> None:
        class DummyAuth:
            is_admin = False
            device_id = "device-1"

        class DummyJob:
            def __init__(self, job_id: str, job_number: str, status: str) -> None:
                self.job_id = job_id
                self.job_number = job_number
                self.status = status
                self.latest_round_id = "round_1"
                self.latest_round_status = "REVIEW_RETURNED"
                self.tree_number = None
                self.billing_name = "Billing"
                self.customer_name = "Customer"

        class DummyProfile:
            def model_dump(self):
                return {"name": "Arborist"}

        class DummyPayload:
            round_id = "round_1"
            server_revision_id = "srv-1"
            client_revision_id = "cli-1"
            form = {"data": {"tree_number": 7}}
            narrative = {"text": "Tree is stable."}
            profile = DummyProfile()

        class DummyArtifactStore:
            def __init__(self, root: Path) -> None:
                self.root = root

            def stage_output(self, key):
                path = self.root / key
                path.parent.mkdir(parents=True, exist_ok=True)
                return path

            def commit_output(self, key, path):
                return path

        class DummyDbStore:
            def get_job_round(self, job_id, round_id):
                return {"review_payload": {"transcript": "Transcript text"}}

        router = build_final_router(
            require_api_key=lambda key: DummyAuth(),
            assert_job_assignment=lambda job_id, auth: None,
            ensure_job_record=lambda job_id: DummyJob(job_id, "J0001", "REVIEW_RETURNED"),
            job_record_factory=DummyJob,
            jobs={},
            db_store=DummyDbStore(),
            is_correction_mode=lambda job_id, record: False,
            logger=type("Logger", (), {"info": lambda *args, **kwargs: None, "exception": lambda *args, **kwargs: None})(),
            finalization_service=type(
                "FinalizationService",
                (),
                {
                    "transcript_from_review_payload": lambda self, payload: "Transcript text",
                    "artifact_names": lambda self, correction_mode: type(
                        "ArtifactNames",
                        (),
                        {
                            "pdf_name": "final_traq_page1.pdf",
                            "report_name": "final_report_letter.pdf",
                            "report_docx_name": "final_report_letter.docx",
                            "final_json_name": "final.json",
                            "geojson_name": "final.geojson",
                        },
                    )(),
                    "ensure_risk_defaults": lambda self, form, normalize_form_schema: form,
                    "build_job_info": lambda self, record: {"job_number": record.job_number},
                    "resolve_profile_payload": lambda self, profile_payload, fallback_loader: profile_payload,
                    "build_final_payload": lambda self, **kwargs: {"form": kwargs["form"], "transcript": kwargs["transcript"]},
                },
            )(),
            artifact_store=DummyArtifactStore(self.storage_root),
            job_artifact_key=lambda *parts: "/".join(parts),
            requested_tree_number_from_form=lambda form: 7,
            resolve_server_tree_number=lambda record, requested_tree_number=None: requested_tree_number,
            normalize_form_schema=lambda form: form,
            apply_tree_number_to_form=lambda form, tree_number: form,
            save_job_record=lambda record: None,
            identity_key=lambda auth, key: "identity",
            load_runtime_profile=lambda key: {"name": "Fallback"},
            media_runtime_service=type("MediaService", (), {"load_job_report_images": lambda self, job_id, round_id: []})(),
            generate_traq_pdf=lambda form_data, output_path: Path(output_path).write_bytes(b"%PDF-1.4"),
            write_json=lambda path, payload: Path(path).write_text('{"ok": true}'),
            read_json=lambda path: {"type": "FeatureCollection"},
            final_mutation_service=type(
                "FinalMutationService",
                (),
                {
                    "set_final": lambda self, job_id, payload, geojson_payload=None: (_ for _ in ()).throw(
                        ValueError("Final snapshot already exists for job_1")
                    ),
                },
            )(),
            unassign_job_record=lambda job_id: None,
            materialize_artifact_path=lambda key: self.storage_root / key,
        )

        from app import geojson_export, report_letter

        old_polish_summary = report_letter.polish_summary
        old_build_report_letter = report_letter.build_report_letter
        old_generate_pdf = report_letter.generate_report_letter_pdf
        old_generate_docx = report_letter.generate_report_letter_docx
        old_geojson = geojson_export.write_final_geojson
        self.addCleanup(setattr, report_letter, "polish_summary", old_polish_summary)
        self.addCleanup(setattr, report_letter, "build_report_letter", old_build_report_letter)
        self.addCleanup(setattr, report_letter, "generate_report_letter_pdf", old_generate_pdf)
        self.addCleanup(setattr, report_letter, "generate_report_letter_docx", old_generate_docx)
        self.addCleanup(setattr, geojson_export, "write_final_geojson", old_geojson)

        report_letter.polish_summary = lambda narrative_text, form_data, transcript: "Summary"
        report_letter.build_report_letter = lambda **kwargs: "Letter"
        report_letter.generate_report_letter_pdf = lambda *args, **kwargs: Path(args[1]).write_bytes(b"%PDF-1.4")
        report_letter.generate_report_letter_docx = lambda *args, **kwargs: Path(args[1]).write_text("docx")
        geojson_export.write_final_geojson = lambda output_path, **kwargs: Path(output_path).write_text('{"type":"FeatureCollection"}')

        submit_final = self._router_endpoint(router, "/v1/jobs/{job_id}/final", "POST")
        with self.assertRaises(HTTPException) as exc:
            submit_final("job_1", DummyPayload(), x_api_key="test-key")
        self.assertEqual(exc.exception.status_code, 409)

    def test_final_router_uses_final_submit_request_body(self) -> None:
        router = build_final_router(
            require_api_key=lambda key: None,
            assert_job_assignment=lambda *args, **kwargs: None,
            ensure_job_record=lambda *args, **kwargs: None,
            job_record_factory=lambda **kwargs: None,
            jobs={},
            db_store=None,
            is_correction_mode=lambda *args, **kwargs: False,
            logger=type("Logger", (), {"info": lambda *args, **kwargs: None, "exception": lambda *args, **kwargs: None})(),
            finalization_service=None,
            artifact_store=None,
            job_artifact_key=lambda *parts: "/".join(parts),
            requested_tree_number_from_form=lambda form: None,
            resolve_server_tree_number=lambda *args, **kwargs: None,
            normalize_form_schema=lambda form: form,
            apply_tree_number_to_form=lambda form, tree_number: form,
            save_job_record=lambda record: None,
            identity_key=lambda auth, key: "identity",
            load_runtime_profile=lambda key: None,
            media_runtime_service=None,
            generate_traq_pdf=lambda form_data, output_path: None,
            write_json=lambda path, payload: None,
            read_json=lambda path: None,
            final_mutation_service=None,
            unassign_job_record=lambda job_id: None,
            materialize_artifact_path=lambda key: self.storage_root / key,
        )

        route = next(
            route
            for route in router.routes
            if isinstance(route, APIRoute) and route.path == "/v1/jobs/{job_id}/final"
        )
        self.assertEqual(len(route.dependant.body_params), 1)
        self.assertIs(route.dependant.body_params[0].type_, FinalSubmitRequest)

    @staticmethod
    def _router_endpoint(router, path: str, method: str):
        for route in router.routes:
            if isinstance(route, APIRoute) and route.path == path and method in route.methods:
                return route.endpoint
        raise AssertionError(f"Endpoint not found: {method} {path}")


if __name__ == "__main__":
    unittest.main()
