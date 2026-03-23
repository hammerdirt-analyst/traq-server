"""Standalone tree identification via the Pl@ntNet API."""

from __future__ import annotations

import json
import mimetypes
import uuid
from dataclasses import dataclass
from typing import Any
from urllib import error, parse, request


ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png"}
ALLOWED_ORGANS = {"auto", "bark", "flower", "fruit", "leaf"}
MAX_TREE_IDENTIFICATION_IMAGES = 5


@dataclass(frozen=True)
class TreeIdentificationImage:
    """One image payload submitted for standalone tree identification."""

    filename: str
    content_type: str
    data: bytes


class TreeIdentificationError(RuntimeError):
    """Base tree-identification failure."""


class TreeIdentificationConfigError(TreeIdentificationError):
    """Raised when upstream configuration is missing."""


class TreeIdentificationUpstreamError(TreeIdentificationError):
    """Raised when the Pl@ntNet API returns an error."""


class TreeIdentificationService:
    """Call Pl@ntNet and normalize the response to the server contract."""

    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str,
        default_project: str,
    ) -> None:
        self._api_key = (api_key or "").strip() or None
        self._base_url = base_url.rstrip("/")
        self._default_project = (default_project or "all").strip() or "all"

    def identify(
        self,
        *,
        images: list[TreeIdentificationImage],
        organs: list[str] | None = None,
        project: str | None = None,
        include_related_images: bool = False,
        no_reject: bool = False,
    ) -> dict[str, Any]:
        """Identify a tree from up to five images."""
        if not self._api_key:
            raise TreeIdentificationConfigError("TRAQ_PLANTNET_API_KEY is not set")
        if not images:
            raise ValueError("At least one image is required")
        if len(images) > MAX_TREE_IDENTIFICATION_IMAGES:
            raise ValueError(f"Maximum {MAX_TREE_IDENTIFICATION_IMAGES} images are allowed")
        for image in images:
            if image.content_type not in ALLOWED_IMAGE_TYPES:
                raise ValueError(f"Unsupported image content type: {image.content_type}")
            if not image.data:
                raise ValueError(f"Empty image payload: {image.filename}")

        normalized_organs = self._normalize_organs(images=images, organs=organs)
        normalized_project = (project or self._default_project or "all").strip() or "all"
        query_params = {"api-key": self._api_key}
        url = f"{self._base_url}/v2/identify/{parse.quote(normalized_project)}?{parse.urlencode(query_params)}"
        body, content_type = self._build_multipart_body(
            images=images,
            organs=normalized_organs,
            include_related_images=include_related_images,
            no_reject=no_reject,
        )
        req = request.Request(
            url,
            method="POST",
            data=body,
            headers={"Content-Type": content_type},
        )
        try:
            with request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode("utf-8")
        except error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            detail = raw
            try:
                payload = json.loads(raw)
                detail = json.dumps(payload)
            except Exception:
                pass
            raise TreeIdentificationUpstreamError(
                f"Pl@ntNet API error {exc.code}: {detail}"
            ) from exc
        except error.URLError as exc:
            raise TreeIdentificationUpstreamError(f"Pl@ntNet API request failed: {exc}") from exc

        payload = json.loads(raw) if raw else {}
        if not isinstance(payload, dict):
            raise TreeIdentificationUpstreamError("Pl@ntNet API returned a non-object response")
        return self._normalize_response(payload)

    def _normalize_organs(
        self,
        *,
        images: list[TreeIdentificationImage],
        organs: list[str] | None,
    ) -> list[str]:
        if not organs:
            return ["auto"] * len(images)
        normalized = [(item or "").strip().lower() for item in organs if (item or "").strip()]
        if not normalized:
            return ["auto"] * len(images)
        if len(normalized) == 1 and len(images) > 1:
            normalized = normalized * len(images)
        if len(normalized) != len(images):
            raise ValueError("organs must be omitted, provided once, or match the image count")
        invalid = [item for item in normalized if item not in ALLOWED_ORGANS]
        if invalid:
            raise ValueError(f"Invalid organs: {', '.join(sorted(set(invalid)))}")
        return normalized

    @staticmethod
    def _normalize_response(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "query": payload.get("query") if isinstance(payload.get("query"), dict) else {},
            "predictedOrgans": payload.get("predictedOrgans") if isinstance(payload.get("predictedOrgans"), list) else [],
            "bestMatch": str(payload.get("bestMatch") or ""),
            "results": payload.get("results") if isinstance(payload.get("results"), list) else [],
            "otherResults": payload.get("otherResults") if isinstance(payload.get("otherResults"), list) else [],
            "version": str(payload.get("version") or ""),
            "remainingIdentificationRequests": int(payload.get("remainingIdentificationRequests") or 0),
        }

    @staticmethod
    def _build_multipart_body(
        *,
        images: list[TreeIdentificationImage],
        organs: list[str],
        include_related_images: bool,
        no_reject: bool,
    ) -> tuple[bytes, str]:
        boundary = f"----traq-{uuid.uuid4().hex}"
        parts: list[bytes] = []

        def add_field(name: str, value: str) -> None:
            parts.extend(
                [
                    f"--{boundary}\r\n".encode("utf-8"),
                    f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
                    value.encode("utf-8"),
                    b"\r\n",
                ]
            )

        for organ in organs:
            add_field("organs", organ)
        if include_related_images:
            add_field("include-related-images", "true")
        if no_reject:
            add_field("no-reject", "true")

        for image in images:
            filename = image.filename or f"upload{mimetypes.guess_extension(image.content_type) or '.jpg'}"
            parts.extend(
                [
                    f"--{boundary}\r\n".encode("utf-8"),
                    (
                        f'Content-Disposition: form-data; name="images"; filename="{filename}"\r\n'
                    ).encode("utf-8"),
                    f"Content-Type: {image.content_type}\r\n\r\n".encode("utf-8"),
                    image.data,
                    b"\r\n",
                ]
            )

        parts.append(f"--{boundary}--\r\n".encode("utf-8"))
        return b"".join(parts), f"multipart/form-data; boundary={boundary}"
