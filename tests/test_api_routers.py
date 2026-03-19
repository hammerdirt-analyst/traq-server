"""Focused router regression checks for extracted low-risk endpoints."""

from __future__ import annotations

import importlib
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.routing import APIRoute

from app import db as db_module
from app.api.admin_routes import build_admin_router
from app.api.core_routes import build_core_router
from app.api.extraction_routes import build_extraction_router
from app.api.job_read_routes import build_job_read_router
from app.api.job_write_routes import build_job_write_router
from app.api.round_manifest_routes import build_round_manifest_router
from app.api.round_reprocess_routes import build_round_reprocess_router
from app.api.round_submit_routes import build_round_submit_router


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

        record = DummyJob()
        saved: list[DummyJob] = []

        router = build_admin_router(
            require_api_key=lambda key, required_role=None: {"api_key": key, "role": required_role},
            ensure_job_record=lambda job_id: record,
            assign_job_record=lambda **kwargs: {"job_id": kwargs["job_id"], "device_id": kwargs["device_id"]},
            unassign_job_record=lambda job_id: {"job_id": job_id},
            list_job_assignments=lambda: [{"job_id": "job_1", "device_id": "device-1"}],
            save_job_record=lambda job: saved.append(job),
            db_store=type("DbStore", (), {"get_job_round": lambda self, job_id, round_id: None})(),
            round_record_factory=lambda **kwargs: DummyRound(status=kwargs["status"]),
            logger=type("Logger", (), {"info": lambda *args, **kwargs: None})(),
        )

        assignments = self._router_endpoint(router, "/v1/admin/jobs/assignments", "GET")
        self.assertEqual(assignments(x_api_key="test-key")["assignments"][0]["job_id"], "job_1")

        reopen = self._router_endpoint(router, "/v1/admin/jobs/{job_id}/rounds/{round_id}/reopen", "POST")
        response = reopen("job_1", "round_1", x_api_key="test-key")
        self.assertTrue(response["ok"])
        self.assertEqual(record.status, "DRAFT")
        self.assertEqual(record.latest_round_status, "DRAFT")
        self.assertEqual(len(saved), 1)

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

    @staticmethod
    def _router_endpoint(router, path: str, method: str):
        for route in router.routes:
            if isinstance(route, APIRoute) and route.path == path and method in route.methods:
                return route.endpoint
        raise AssertionError(f"Endpoint not found: {method} {path}")


if __name__ == "__main__":
    unittest.main()
