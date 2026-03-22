"""HTTP-only backend for remote CLI mode."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable
from urllib import error, parse, request

from .backends import CliBackendBundle, UnsupportedInModeError


HttpCaller = Callable[..., tuple[int, Any]]


def _unsupported(command_name: str) -> UnsupportedInModeError:
    return UnsupportedInModeError(
        f"Command not available in remote mode yet: {command_name}. "
        "The server endpoint is not implemented."
    )


class _RemoteBase:
    def __init__(self, *, host: str, api_key: str, http: HttpCaller) -> None:
        self._host = host.rstrip("/")
        self._api_key = api_key
        self._http = http

    def _expect_ok(self, code: int, body: Any) -> Any:
        if code != 200:
            raise RuntimeError(f"HTTP {code}: {body}")
        return body

    def _download(self, path: str) -> tuple[bytes, dict[str, str]]:
        req = request.Request(
            f"{self._host}{path}",
            method="GET",
            headers={"x-api-key": self._api_key},
        )
        try:
            with request.urlopen(req, timeout=30) as resp:
                headers = {key: value for key, value in resp.headers.items()}
                return resp.read(), headers
        except error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {int(exc.code)}: {raw}") from exc


class RemoteDeviceBackend(_RemoteBase):
    def _list_devices(self, *, status: str | None = None) -> list[dict[str, Any]]:
        suffix = "/v1/admin/devices/pending" if status == "pending" else "/v1/admin/devices"
        query = ""
        if status and status != "pending":
            query = f"?status={parse.quote(status)}"
        code, body = self._http(
            "GET",
            f"{self._host}{suffix}{query}",
            api_key=self._api_key,
        )
        payload = self._expect_ok(code, body)
        return list(payload.get("devices", []) if isinstance(payload, dict) else [])

    def _resolve_device_id(self, device_ref: str) -> str:
        normalized = (device_ref or "").strip()
        if not normalized:
            raise RuntimeError("Device id is required")
        rows = self._list_devices()
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
        if status == "pending":
            return self._list_devices(status="pending")
        return self._list_devices(status=status)

    def pending(self) -> Any:
        return self._list_devices(status="pending")

    def validate(self, *, index: int, role: str) -> Any:
        rows = self._list_devices(status="pending")
        if not rows:
            raise RuntimeError("No pending devices.")
        normalized_index = max(1, int(index))
        if normalized_index > len(rows):
            raise RuntimeError(f"Invalid index {normalized_index}; pending count={len(rows)}")
        device_id = str(rows[normalized_index - 1].get("device_id") or "")
        return self.approve(device_id=device_id, role=role)

    def approve(self, *, device_id: str, role: str) -> Any:
        resolved = self._resolve_device_id(device_id)
        code, body = self._http(
            "POST",
            f"{self._host}/v1/admin/devices/{parse.quote(resolved)}/approve",
            api_key=self._api_key,
            payload={"role": role},
        )
        return self._expect_ok(code, body)

    def revoke(self, *, device_id: str) -> Any:
        resolved = self._resolve_device_id(device_id)
        code, body = self._http(
            "POST",
            f"{self._host}/v1/admin/devices/{parse.quote(resolved)}/revoke",
            api_key=self._api_key,
            payload={},
        )
        return self._expect_ok(code, body)

    def issue_token(self, *, device_id: str, ttl: int) -> Any:
        resolved = self._resolve_device_id(device_id)
        code, body = self._http(
            "POST",
            f"{self._host}/v1/admin/devices/{parse.quote(resolved)}/issue-token",
            api_key=self._api_key,
            payload={"ttl_seconds": ttl},
        )
        return self._expect_ok(code, body)


class RemoteCustomerBackend(_RemoteBase):
    def list(self, *, search: str | None = None) -> Any:
        raise _unsupported("customer list")
    def duplicates(self) -> Any:
        raise _unsupported("customer duplicates")
    def create(self, **kwargs: Any) -> Any:
        raise _unsupported("customer create")
    def update(self, customer_id: str, **kwargs: Any) -> Any:
        raise _unsupported("customer update")
    def usage(self, customer_id: str) -> Any:
        raise _unsupported("customer usage")
    def merge(self, customer_id: str, *, into: str) -> Any:
        raise _unsupported("customer merge")
    def delete(self, customer_id: str) -> Any:
        raise _unsupported("customer delete")


class RemoteBillingBackend(_RemoteBase):
    def list(self, *, search: str | None = None) -> Any:
        raise _unsupported("customer billing list")
    def duplicates(self) -> Any:
        raise _unsupported("customer billing duplicates")
    def create(self, **kwargs: Any) -> Any:
        raise _unsupported("customer billing create")
    def update(self, billing_profile_id: str, **kwargs: Any) -> Any:
        raise _unsupported("customer billing update")
    def usage(self, billing_profile_id: str) -> Any:
        raise _unsupported("customer billing usage")
    def merge(self, billing_profile_id: str, *, into: str) -> Any:
        raise _unsupported("customer billing merge")
    def delete(self, billing_profile_id: str) -> Any:
        raise _unsupported("customer billing delete")


class RemoteJobBackend(_RemoteBase):
    def _resolve_job_id(self, job_ref: str) -> str:
        normalized = (job_ref or "").strip()
        if not normalized:
            raise RuntimeError("Job reference is required")
        if normalized.startswith("job_"):
            return normalized
        code, body = self._http(
            "GET",
            f"{self._host}/v1/admin/jobs/resolve?job_ref={parse.quote(normalized)}",
            api_key=self._api_key,
        )
        payload = self._expect_ok(code, body)
        job_id = str(payload.get("job_id") or "").strip() if isinstance(payload, dict) else ""
        if not job_id:
            raise RuntimeError(f"Job not found: {job_ref}")
        return job_id

    def create(self, **kwargs: Any) -> Any:
        raise _unsupported("job create")

    def update(self, job_ref: str, **kwargs: Any) -> Any:
        raise _unsupported("job update")

    def inspect(self, *, job_ref: str) -> Any:
        job_id = self._resolve_job_id(job_ref)
        code, body = self._http(
            "GET",
            f"{self._host}/v1/admin/jobs/{parse.quote(job_id)}/inspect",
            api_key=self._api_key,
        )
        return self._expect_ok(code, body)

    def list_assignments(self, *, raw: bool = False) -> Any:
        code, body = self._http(
            "GET",
            f"{self._host}/v1/admin/jobs/assignments",
            api_key=self._api_key,
        )
        payload = self._expect_ok(code, body)
        if raw and isinstance(payload, dict):
            return payload.get("assignments", [])
        return payload

    def assign(self, *, job_ref: str, device_id: str) -> Any:
        job_id = self._resolve_job_id(job_ref)
        code, body = self._http(
            "POST",
            f"{self._host}/v1/admin/jobs/{parse.quote(job_id)}/assign",
            api_key=self._api_key,
            payload={"device_id": device_id},
        )
        return self._expect_ok(code, body)

    def unassign(self, *, job_ref: str) -> Any:
        job_id = self._resolve_job_id(job_ref)
        code, body = self._http(
            "POST",
            f"{self._host}/v1/admin/jobs/{parse.quote(job_id)}/unassign",
            api_key=self._api_key,
            payload={},
        )
        return self._expect_ok(code, body)

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
            f"{self._host}/v1/admin/jobs/{parse.quote(job_id)}/status",
            api_key=self._api_key,
            payload=payload,
        )
        return self._expect_ok(code, body)

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
            f"{self._host}/v1/admin/jobs/{parse.quote(job_id)}/unlock",
            api_key=self._api_key,
            payload=payload,
        )
        return self._expect_ok(code, body)


class RemoteRoundBackend(_RemoteBase):
    def __init__(self, *, host: str, api_key: str, http: HttpCaller, job_backend: RemoteJobBackend) -> None:
        super().__init__(host=host, api_key=api_key, http=http)
        self._job_backend = job_backend

    def reopen(self, *, job_id: str, round_id: str) -> Any:
        code, body = self._http(
            "POST",
            f"{self._host}/v1/admin/jobs/{parse.quote(job_id)}/rounds/{parse.quote(round_id)}/reopen",
            api_key=self._api_key,
            payload={},
        )
        return self._expect_ok(code, body)

    def inspect(self, *, job_ref: str, round_id: str) -> Any:
        job_id = self._job_backend._resolve_job_id(job_ref)
        code, body = self._http(
            "GET",
            f"{self._host}/v1/admin/jobs/{parse.quote(job_id)}/rounds/{parse.quote(round_id)}/inspect",
            api_key=self._api_key,
        )
        return self._expect_ok(code, body)


class RemoteReviewBackend(_RemoteBase):
    def __init__(self, *, host: str, api_key: str, http: HttpCaller, job_backend: RemoteJobBackend) -> None:
        super().__init__(host=host, api_key=api_key, http=http)
        self._job_backend = job_backend

    def inspect(self, *, job_ref: str, round_id: str) -> Any:
        job_id = self._job_backend._resolve_job_id(job_ref)
        code, body = self._http(
            "GET",
            f"{self._host}/v1/admin/jobs/{parse.quote(job_id)}/rounds/{parse.quote(round_id)}/review/inspect",
            api_key=self._api_key,
        )
        return self._expect_ok(code, body)


class RemoteFinalBackend(_RemoteBase):
    def __init__(self, *, host: str, api_key: str, http: HttpCaller, job_backend: RemoteJobBackend) -> None:
        super().__init__(host=host, api_key=api_key, http=http)
        self._job_backend = job_backend

    def inspect(self, *, job_ref: str) -> Any:
        job_id = self._job_backend._resolve_job_id(job_ref)
        code, body = self._http(
            "GET",
            f"{self._host}/v1/admin/jobs/{parse.quote(job_id)}/final/inspect",
            api_key=self._api_key,
        )
        return self._expect_ok(code, body)

    def set_final(
        self,
        *,
        job_ref: str,
        payload: dict[str, Any],
        geojson_payload: dict[str, Any] | None,
    ) -> Any:
        raise _unsupported("final set-final")

    def set_correction(
        self,
        *,
        job_ref: str,
        payload: dict[str, Any],
        geojson_payload: dict[str, Any] | None,
    ) -> Any:
        raise _unsupported("final set-correction")


class RemoteArtifactBackend(_RemoteBase):
    def __init__(self, *, host: str, api_key: str, http: HttpCaller, job_backend: RemoteJobBackend) -> None:
        super().__init__(host=host, api_key=api_key, http=http)
        self._job_backend = job_backend

    def fetch(self, *, job_ref: str, kind: str) -> Any:
        job_id = self._job_backend._resolve_job_id(job_ref)
        job_meta = self._job_backend.inspect(job_ref=job_ref)
        job_number = str(job_meta.get("job_number") or job_ref).strip()
        payload, headers = self._download(
            f"/v1/admin/jobs/{parse.quote(job_id)}/artifacts/{parse.quote(kind)}"
        )
        export_dir = Path.cwd() / "exports" / job_number
        export_dir.mkdir(parents=True, exist_ok=True)
        filename = ""
        content_disposition = headers.get("Content-Disposition") or headers.get("content-disposition") or ""
        if "filename=" in content_disposition:
            filename = content_disposition.split("filename=", 1)[1].strip().strip('"')
        if not filename:
            filename = f"{job_number}_{kind.replace('-', '_')}"
        saved_path = export_dir / filename
        if kind in {"transcript", "final-json"}:
            saved_path.write_bytes(payload)
        else:
            saved_path.write_bytes(payload)
        return {
            "job_number": job_number,
            "job_id": job_id,
            "kind": kind,
            "variant": headers.get("X-Artifact-Variant") or headers.get("x-artifact-variant"),
            "saved_path": str(saved_path),
        }


class RemoteTreeBackend(_RemoteBase):
    def identify(
        self,
        *,
        image_paths: list[str],
        organs: list[str] | None = None,
        project: str | None = None,
        include_related_images: bool = False,
        no_reject: bool = False,
        nb_results: int | None = None,
        lang: str | None = None,
    ) -> Any:
        paths = [Path(item) for item in image_paths]
        missing = [str(path) for path in paths if not path.exists()]
        if missing:
            raise RuntimeError(f"Missing image files: {', '.join(missing)}")
        if len(paths) > 5:
            raise RuntimeError("Maximum 5 images are allowed")
        files: list[tuple[str, str, bytes, str]] = []
        for path in paths:
            files.append(
                (
                    "images",
                    path.name,
                    path.read_bytes(),
                    "image/png" if path.suffix.lower() == ".png" else "image/jpeg",
                )
            )
        payload: dict[str, Any] = {
            "project": project,
            "include_related_images": include_related_images,
            "no_reject": no_reject,
            "nb_results": nb_results,
            "lang": lang,
        }
        for organ in organs or []:
            payload.setdefault("organs", []).append(organ)
        code, body = self._http(
            "POST",
            f"{self._host}/v1/trees/identify",
            api_key=self._api_key,
            payload=payload,
            files=files,
        )
        return self._expect_ok(code, body)


class RemoteNetBackend(_RemoteBase):
    def ipv4(self) -> Any:
        raise _unsupported("net ipv4")

    def ipv6(self) -> Any:
        raise _unsupported("net ipv6")


def build_remote_backend(*, host: str, api_key: str, http: HttpCaller) -> CliBackendBundle:
    job_backend = RemoteJobBackend(host=host, api_key=api_key, http=http)
    return CliBackendBundle(
        mode_name="remote",
        device=RemoteDeviceBackend(host=host, api_key=api_key, http=http),
        customer=RemoteCustomerBackend(host=host, api_key=api_key, http=http),
        billing=RemoteBillingBackend(host=host, api_key=api_key, http=http),
        job=job_backend,
        round=RemoteRoundBackend(host=host, api_key=api_key, http=http, job_backend=job_backend),
        review=RemoteReviewBackend(host=host, api_key=api_key, http=http, job_backend=job_backend),
        final=RemoteFinalBackend(host=host, api_key=api_key, http=http, job_backend=job_backend),
        artifact=RemoteArtifactBackend(host=host, api_key=api_key, http=http, job_backend=job_backend),
        tree=RemoteTreeBackend(host=host, api_key=api_key, http=http),
        net=RemoteNetBackend(host=host, api_key=api_key, http=http),
    )
