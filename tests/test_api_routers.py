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

    @staticmethod
    def _router_endpoint(router, path: str, method: str):
        for route in router.routes:
            if isinstance(route, APIRoute) and route.path == path and method in route.methods:
                return route.endpoint
        raise AssertionError(f"Endpoint not found: {method} {path}")


if __name__ == "__main__":
    unittest.main()
