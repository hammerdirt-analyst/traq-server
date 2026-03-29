"""Current local backend for CLI mode."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from app.artifact_storage import create_artifact_store
from app.config import load_settings
from app.db import create_schema, init_database
from app.db_store import DatabaseStore
from app.services.artifact_fetch_service import ArtifactFetchService
from app.services.customer_service import CustomerService
from app.services.final_mutation_service import FinalMutationService
from app.services.inspection_service import InspectionService
from app.services.job_mutation_service import JobMutationService
from app.services.project_service import ProjectService
from app.services.tree_identification_service import TreeIdentificationImage, TreeIdentificationService

from .backends import CliBackendBundle, UnsupportedInModeError
from .file_exports import save_bytes_output, save_json_output
from .net_commands import _collect_ipv4_candidates, _collect_ipv6_candidates


HttpCaller = Callable[..., tuple[int, Any]]


def _settings():
    return load_settings()


def _init_db() -> None:
    settings = _settings()
    init_database(settings)
    create_schema()


def _store() -> DatabaseStore:
    _init_db()
    return DatabaseStore()


def _inspection_service() -> InspectionService:
    settings = _settings()
    _init_db()
    return InspectionService(settings=settings, db_store=DatabaseStore())


def _customer_service() -> CustomerService:
    _init_db()
    return CustomerService()


def _job_mutation_service() -> JobMutationService:
    _init_db()
    return JobMutationService()


def _project_service() -> ProjectService:
    _init_db()
    return ProjectService()


def _final_mutation_service() -> FinalMutationService:
    _init_db()
    return FinalMutationService()


def _artifact_fetch_service() -> ArtifactFetchService:
    settings = _settings()
    _init_db()
    return ArtifactFetchService(
        settings=settings,
        db_store=DatabaseStore(),
        artifact_store=create_artifact_store(settings),
    )


class LocalDeviceBackend:
    def _resolve_device_id(self, device_ref: str) -> str:
        normalized = (device_ref or "").strip()
        if not normalized:
            raise RuntimeError("Device id is required")
        rows = _store().list_devices()
        exact = [row for row in rows if str(row.get("device_id") or "") == normalized]
        if exact:
            return normalized
        matches = [
            str(row.get("device_id") or "")
            for row in rows
            if str(row.get("device_id") or "").startswith(normalized)
        ]
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise RuntimeError(f"Device not found: {device_ref}")
        raise RuntimeError(f"Device id prefix is ambiguous: {device_ref}")

    def list(self, *, status: str | None = None) -> Any:
        return _store().list_devices(status=status)

    def pending(self) -> Any:
        rows = _store().list_devices(status="pending")
        rows.sort(key=lambda r: str(r.get("updated_at") or r.get("created_at") or ""))
        return rows

    def validate(self, *, index: int, role: str) -> Any:
        rows = self.pending()
        if not rows:
            raise RuntimeError("No pending devices.")
        normalized_index = max(1, int(index))
        if normalized_index > len(rows):
            raise RuntimeError(f"Invalid index {normalized_index}; pending count={len(rows)}")
        device_id = str(rows[normalized_index - 1].get("device_id") or "")
        return _store().approve_device(device_id, role=role)

    def approve(self, *, device_id: str, role: str) -> Any:
        return _store().approve_device(self._resolve_device_id(device_id), role=role)

    def revoke(self, *, device_id: str) -> Any:
        return _store().revoke_device(self._resolve_device_id(device_id))

    def issue_token(self, *, device_id: str, ttl: int) -> Any:
        return _store().issue_token(self._resolve_device_id(device_id), ttl_seconds=ttl)


class LocalCustomerBackend:
    def list(self, *, search: str | None = None) -> Any:
        return _customer_service().list_customers(search=search)
    def duplicates(self) -> Any:
        return _customer_service().customer_duplicates()
    def create(self, **kwargs: Any) -> Any:
        return _customer_service().create_customer(**kwargs)
    def update(self, customer_id: str, **kwargs: Any) -> Any:
        return _customer_service().update_customer(customer_id, **kwargs)
    def usage(self, customer_id: str) -> Any:
        return _customer_service().customer_usage(customer_id)
    def merge(self, customer_id: str, *, into: str) -> Any:
        return _customer_service().merge_customer(customer_id, target_customer_id=into)
    def delete(self, customer_id: str) -> Any:
        return _customer_service().delete_customer(customer_id)


class LocalBillingBackend:
    def list(self, *, search: str | None = None) -> Any:
        return _customer_service().list_billing_profiles(search=search)
    def duplicates(self) -> Any:
        return _customer_service().billing_duplicates()
    def create(self, **kwargs: Any) -> Any:
        return _customer_service().create_billing_profile(**kwargs)
    def update(self, billing_profile_id: str, **kwargs: Any) -> Any:
        return _customer_service().update_billing_profile(billing_profile_id, **kwargs)
    def usage(self, billing_profile_id: str) -> Any:
        return _customer_service().billing_usage(billing_profile_id)
    def merge(self, billing_profile_id: str, *, into: str) -> Any:
        return _customer_service().merge_billing_profile(billing_profile_id, target_billing_profile_id=into)
    def delete(self, billing_profile_id: str) -> Any:
        return _customer_service().delete_billing_profile(billing_profile_id)


class LocalProjectBackend:
    def list(self) -> Any:
        return _project_service().list_projects()

    def create(self, **kwargs: Any) -> Any:
        return _project_service().create_project(**kwargs)

    def update(self, project_ref: str, **kwargs: Any) -> Any:
        return _project_service().update_project(project_ref, **kwargs)


class LocalJobBackend:
    def __init__(self, *, http: HttpCaller, host: str, api_key: str) -> None:
        self._http = http
        self._host = host.rstrip("/")
        self._api_key = api_key

    def _resolve_job_id(self, job_ref: str) -> str:
        if job_ref.startswith("job_"):
            return job_ref
        return _inspection_service().resolve_job_id(job_ref)

    def create(self, **kwargs: Any) -> Any:
        return _job_mutation_service().create_job(**kwargs)

    def update(self, job_ref: str, **kwargs: Any) -> Any:
        return _job_mutation_service().update_job(job_ref, **kwargs)

    def inspect(self, *, job_ref: str) -> Any:
        return _inspection_service().inspect_job(job_ref)

    def list_assignments(self, *, raw: bool = False) -> Any:
        code, body = self._http("GET", f"{self._host}/v1/admin/jobs/assignments", api_key=self._api_key)
        if code != 200:
            raise RuntimeError(f"HTTP {code}: {body}")
        if raw and isinstance(body, dict):
            return body.get("assignments", [])
        return body

    def assign(self, *, job_ref: str, device_id: str) -> Any:
        job_id = self._resolve_job_id(job_ref)
        code, body = self._http(
            "POST",
            f"{self._host}/v1/admin/jobs/{job_id}/assign",
            api_key=self._api_key,
            payload={"device_id": device_id},
        )
        if code != 200:
            raise RuntimeError(f"HTTP {code}: {body}")
        return body

    def unassign(self, *, job_ref: str) -> Any:
        job_id = self._resolve_job_id(job_ref)
        code, body = self._http(
            "POST",
            f"{self._host}/v1/admin/jobs/{job_id}/unassign",
            api_key=self._api_key,
            payload={},
        )
        if code != 200:
            raise RuntimeError(f"HTTP {code}: {body}")
        return body

    def set_status(
        self,
        *,
        job_ref: str,
        status: str,
        round_id: str | None = None,
        round_status: str | None = None,
    ) -> Any:
        job_id = self._resolve_job_id(job_ref)
        payload: dict[str, Any] = {"status": status}
        if round_id:
            payload["round_id"] = round_id
        if round_status:
            payload["round_status"] = round_status
        code, body = self._http(
            "POST",
            f"{self._host}/v1/admin/jobs/{job_id}/status",
            api_key=self._api_key,
            payload=payload,
        )
        if code != 200:
            raise RuntimeError(f"HTTP {code}: {body}")
        return body

    def unlock(
        self,
        *,
        job_ref: str,
        round_id: str | None = None,
        device_id: str | None = None,
    ) -> Any:
        job_id = self._resolve_job_id(job_ref)
        payload: dict[str, Any] = {}
        if round_id:
            payload["round_id"] = round_id
        if device_id:
            payload["device_id"] = device_id
        code, body = self._http(
            "POST",
            f"{self._host}/v1/admin/jobs/{job_id}/unlock",
            api_key=self._api_key,
            payload=payload,
        )
        if code != 200:
            raise RuntimeError(f"HTTP {code}: {body}")
        return body


class LocalRoundBackend:
    def __init__(self, *, http: HttpCaller, host: str, api_key: str) -> None:
        self._http = http
        self._host = host.rstrip("/")
        self._api_key = api_key

    def create(self, *, job_ref: str) -> Any:
        job_id = _inspection_service().resolve_job_id(job_ref) if not job_ref.startswith("job_") else job_ref
        job = _store().get_job(job_id)
        if not isinstance(job, dict):
            raise RuntimeError(f"Job not found: {job_ref}")
        latest = str(job.get("latest_round_status") or "").strip().upper()
        if latest == "SUBMITTED_FOR_PROCESSING":
            raise RuntimeError("Job is locked while processing. Wait for review.")
        if latest == "ARCHIVED":
            raise RuntimeError("Job is archived. Admin must reopen to DRAFT.")
        rounds = _store().list_job_rounds(job_id)
        round_id = f"round_{len(rounds) + 1}"
        _store().upsert_job_round(job_id=job_id, round_id=round_id, status="DRAFT")
        details = dict(job)
        details["latest_round_id"] = round_id
        details["latest_round_status"] = "DRAFT"
        _store().upsert_job(
            job_id=job_id,
            job_number=str(job.get("job_number") or job_id),
            status="DRAFT",
            latest_round_id=round_id,
            latest_round_status="DRAFT",
            details=details,
        )
        return {"round_id": round_id, "status": "DRAFT"}

    def manifest_get(self, *, job_ref: str, round_id: str) -> Any:
        job_id = _inspection_service().resolve_job_id(job_ref) if not job_ref.startswith("job_") else job_ref
        payload = _store().get_job_round(job_id, round_id)
        if not isinstance(payload, dict):
            raise RuntimeError(f"Round not found: {job_ref}/{round_id}")
        manifest = list(payload.get("manifest") or [])
        return {"ok": True, "round_id": round_id, "manifest": manifest, "manifest_count": len(manifest)}

    def manifest_set(self, *, job_ref: str, round_id: str, items: list[dict[str, Any]]) -> Any:
        job_id = _inspection_service().resolve_job_id(job_ref) if not job_ref.startswith("job_") else job_ref
        payload = _store().get_job_round(job_id, round_id)
        if not isinstance(payload, dict):
            raise RuntimeError(f"Round not found: {job_ref}/{round_id}")
        _store().upsert_job_round(
            job_id=job_id,
            round_id=round_id,
            status=str(payload.get("status") or "DRAFT"),
            server_revision_id=payload.get("server_revision_id"),
            manifest=items,
            review_payload=payload.get("review_payload"),
        )
        return {"ok": True, "round_id": round_id, "manifest_count": len(items)}

    def submit(self, *, job_ref: str, round_id: str, payload: dict[str, Any] | None) -> Any:
        raise UnsupportedInModeError(
            "round submit is not available in local mode yet. "
            "The local round submit service seam has not been extracted."
        )

    def reprocess(self, *, job_ref: str, round_id: str) -> Any:
        raise UnsupportedInModeError(
            "round reprocess is not available in local mode yet. "
            "The local round reprocess service seam has not been extracted."
        )

    def reopen(self, *, job_id: str, round_id: str) -> Any:
        code, body = self._http(
            "POST",
            f"{self._host}/v1/admin/jobs/{job_id}/rounds/{round_id}/reopen",
            api_key=self._api_key,
            payload={},
        )
        if code != 200:
            raise RuntimeError(f"HTTP {code}: {body}")
        return body

    def inspect(self, *, job_ref: str, round_id: str) -> Any:
        return _inspection_service().inspect_round(job_ref, round_id)


class LocalReviewBackend:
    def inspect(self, *, job_ref: str, round_id: str) -> Any:
        return _inspection_service().inspect_review(job_ref, round_id)


class LocalFinalBackend:
    def inspect(self, *, job_ref: str) -> Any:
        return _inspection_service().inspect_final(job_ref)

    def set_final(self, *, job_ref: str, payload: dict[str, Any], geojson_payload: dict[str, Any] | None) -> Any:
        return _final_mutation_service().set_final(job_ref, payload=payload, geojson_payload=geojson_payload)

    def set_correction(self, *, job_ref: str, payload: dict[str, Any], geojson_payload: dict[str, Any] | None) -> Any:
        return _final_mutation_service().set_correction(job_ref, payload=payload, geojson_payload=geojson_payload)


class LocalArtifactBackend:
    def fetch(self, *, job_ref: str, kind: str) -> Any:
        return _artifact_fetch_service().fetch(job_ref, kind=kind)


class LocalExportBackend:
    def __init__(self, *, http: HttpCaller, host: str, api_key: str) -> None:
        self._http = http
        self._host = host.rstrip("/")
        self._api_key = api_key

    def changes(self, *, cursor: str | None = None) -> Any:
        query = f"?cursor={cursor}" if cursor else ""
        code, body = self._http(
            "GET",
            f"{self._host}/v1/export/changes{query}",
            api_key=self._api_key,
        )
        if code != 200:
            raise RuntimeError(f"HTTP {code}: {body}")
        return body

    def image_fetch(
        self,
        *,
        job_id: str,
        image_ref: str,
        variant: str = "auto",
        output_path: str | None = None,
    ) -> Any:
        from urllib import parse, request

        req = request.Request(
            f"{self._host}/v1/export/jobs/{parse.quote(job_id)}/images/{parse.quote(image_ref)}?variant={parse.quote(variant)}",
            method="GET",
            headers={"x-api-key": self._api_key},
        )
        with request.urlopen(req, timeout=30) as resp:
            payload = resp.read()
            saved_path = save_bytes_output(
                payload=payload,
                output_path=output_path,
                default_path=Path.cwd() / "exports" / job_id / resp.headers.get_filename(),
            )
            return {
                "job_id": job_id,
                "image_ref": image_ref,
                "variant": variant,
                "saved_path": str(saved_path),
            }

    def geojson_fetch(self, *, job_id: str, output_path: str | None = None) -> Any:
        code, body = self._http(
            "GET",
            f"{self._host}/v1/export/jobs/{job_id}/geojson",
            api_key=self._api_key,
        )
        if code != 200:
            raise RuntimeError(f"HTTP {code}: {body}")
        saved_path = save_json_output(
            payload=body,
            output_path=output_path,
            default_path=Path.cwd() / "exports" / job_id / "export.geojson",
        )
        return {
            "job_id": job_id,
            "saved_path": str(saved_path),
        }


class LocalTreeBackend:
    def identify(
        self,
        *,
        image_paths: list[str],
        organs: list[str] | None = None,
        project: str | None = None,
        include_related_images: bool = False,
        no_reject: bool = False,
    ) -> Any:
        settings = _settings()
        service = TreeIdentificationService(
            api_key=settings.plantnet_api_key,
            base_url=settings.plantnet_base_url,
            default_project=settings.plantnet_project,
        )
        paths = [Path(item) for item in image_paths]
        images: list[TreeIdentificationImage] = []
        for path in paths:
            if not path.exists():
                raise RuntimeError(f"Missing image file: {path}")
            images.append(
                TreeIdentificationImage(
                    filename=path.name,
                    content_type="image/png" if path.suffix.lower() == ".png" else "image/jpeg",
                    data=path.read_bytes(),
                )
            )
        return service.identify(
            images=images,
            organs=organs,
            project=project,
            include_related_images=include_related_images,
            no_reject=no_reject,
        )


class LocalNetBackend:
    def ipv4(self) -> Any:
        return {
            "ok": True,
            "note": "Use the top non-loopback IPv4 as Device Host IP in the mobile app.",
            "ipv4_candidates": _collect_ipv4_candidates(),
        }

    def ipv6(self) -> Any:
        return {
            "ok": True,
            "note": "Use the top global IPv6 as Device Host IP. In URLs use brackets: http://[IPv6]:8000",
            "ipv6_candidates": _collect_ipv6_candidates(),
        }


def build_local_backend(*, http: HttpCaller) -> CliBackendBundle:
    settings = _settings()
    host = settings.admin_base_url
    api_key = settings.api_key
    return CliBackendBundle(
        mode_name="local",
        device=LocalDeviceBackend(),
        customer=LocalCustomerBackend(),
        billing=LocalBillingBackend(),
        project=LocalProjectBackend(),
        job=LocalJobBackend(http=http, host=host, api_key=api_key),
        round=LocalRoundBackend(http=http, host=host, api_key=api_key),
        review=LocalReviewBackend(),
        final=LocalFinalBackend(),
        artifact=LocalArtifactBackend(),
        export=LocalExportBackend(http=http, host=host, api_key=api_key),
        tree=LocalTreeBackend(),
        net=LocalNetBackend(),
    )
