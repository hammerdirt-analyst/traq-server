"""Export sync CLI command handlers."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import Callable

from .backends import CliBackendBundle

JsonPrinter = Callable[[object], None]


def cmd_export_changes(
    args: argparse.Namespace,
    *,
    backend: CliBackendBundle,
    print_json: JsonPrinter,
) -> int:
    """Fetch export-visible job changes from the server."""
    try:
        payload = backend.export.changes(cursor=args.cursor)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1
    print_json(payload)
    return 0


def cmd_export_image_fetch(
    args: argparse.Namespace,
    *,
    backend: CliBackendBundle,
    print_json: JsonPrinter,
) -> int:
    """Download one export-visible image artifact."""
    try:
        payload = backend.export.image_fetch(
            job_id=args.job_id,
            image_ref=args.image_ref,
            variant=args.variant,
            output_path=args.output,
        )
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1
    print_json(payload)
    return 0


def cmd_export_geojson_fetch(
    args: argparse.Namespace,
    *,
    backend: CliBackendBundle,
    print_json: JsonPrinter,
) -> int:
    """Download one export-visible GeoJSON payload."""
    try:
        payload = backend.export.geojson_fetch(
            job_id=args.job_id,
            output_path=args.output,
        )
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1
    print_json(payload)
    return 0


def cmd_export_images_fetch_all(
    args: argparse.Namespace,
    *,
    backend: CliBackendBundle,
    print_json: JsonPrinter,
) -> int:
    """Download all export-visible image artifacts for one job."""
    try:
        job_payload = backend.job.inspect(job_ref=args.job)
        job_id = str(job_payload.get("job_id") or "").strip()
        job_number = str(job_payload.get("job_number") or args.job).strip()
        if not job_id:
            raise RuntimeError("Job inspection did not return job_id")
        changes = backend.export.changes(cursor=None)
        refs, duplicate_refs = _image_refs_for_job(changes, job_id=job_id)
        if not refs:
            raise RuntimeError(f"No export-visible images found for job {args.job}")
        output_root = Path(args.output) if args.output else (Path.cwd() / "exports" / job_number / "images")
        output_root.mkdir(parents=True, exist_ok=True)
        downloaded: list[dict[str, str]] = []
        failures: list[dict[str, str]] = []
        for image_ref in refs:
            try:
                payload = backend.export.image_fetch(
                    job_id=job_id,
                    image_ref=image_ref,
                    variant=args.variant,
                    output_path=None,
                )
                source_path = Path(str(payload.get("saved_path") or "").strip())
                if not source_path.exists():
                    raise RuntimeError(f"Downloaded file not found for image_ref={image_ref}")
                final_path = output_root / source_path.name
                if source_path.resolve() != final_path.resolve():
                    final_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(source_path), str(final_path))
                downloaded.append({"image_ref": image_ref, "saved_path": str(final_path)})
            except Exception as exc:
                failures.append({"image_ref": image_ref, "error": str(exc)})
        summary = {
            "job_id": job_id,
            "job_number": job_number,
            "variant": args.variant,
            "total_refs": len(refs),
            "skipped_duplicates": duplicate_refs,
            "downloaded_count": len(downloaded),
            "failed_count": len(failures),
            "downloaded": downloaded,
            "failed": failures,
            "output_dir": str(output_root),
        }
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1
    print_json(summary)
    return 0 if downloaded else 1


def _image_refs_for_job(payload: object, *, job_id: str) -> tuple[list[str], int]:
    """Collect unique image refs from export change payload rows for one job."""
    if not isinstance(payload, dict):
        return [], 0
    refs: list[str] = []
    seen: set[str] = set()
    duplicate_refs = 0
    for section in ("in_process", "completed", "transitioned_to_completed"):
        rows = payload.get(section)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            if str(row.get("job_id") or "").strip() != job_id:
                continue
            review = row.get("review")
            if isinstance(review, dict):
                images = review.get("images")
                if isinstance(images, list):
                    for item in images:
                        if not isinstance(item, dict):
                            continue
                        image_ref = str(item.get("image_ref") or "").strip()
                        if image_ref:
                            if image_ref in seen:
                                duplicate_refs += 1
                            else:
                                seen.add(image_ref)
                                refs.append(image_ref)
            final = row.get("final")
            if isinstance(final, dict):
                report_images = final.get("report_images")
                if isinstance(report_images, list):
                    for item in report_images:
                        if not isinstance(item, dict):
                            continue
                        image_ref = str(item.get("image_ref") or "").strip()
                        if image_ref:
                            if image_ref in seen:
                                duplicate_refs += 1
                            else:
                                seen.add(image_ref)
                                refs.append(image_ref)
    return refs, duplicate_refs


def register_export_commands(
    subparsers,
    handlers: dict[str, Callable[[argparse.Namespace], int]],
    *,
    default_host: str,
    default_api_key: str,
) -> None:
    """Register the export command group."""
    export = subparsers.add_parser("export", help="Incremental reporting export operations")
    export_sub = export.add_subparsers(dest="export_cmd", required=True)

    changes_cmd = export_sub.add_parser("changes", help="Fetch export-visible changes since a cursor")
    changes_cmd.add_argument("--cursor", default=None, help="ISO-8601 cursor from the previous sync")
    changes_cmd.add_argument("--host", default=default_host)
    changes_cmd.add_argument("--api-key", default=default_api_key)
    changes_cmd.set_defaults(func=handlers["changes"])

    image_cmd = export_sub.add_parser("image-fetch", help="Download one export image")
    image_cmd.add_argument("--job-id", required=True, help="Canonical job_id")
    image_cmd.add_argument("--image-ref", required=True, help="Image ref from export payload")
    image_cmd.add_argument(
        "--variant",
        default="auto",
        choices=["auto", "original", "report"],
        help="Preferred image variant",
    )
    image_cmd.add_argument("--output", default=None, help="Optional explicit output file path")
    image_cmd.add_argument("--host", default=default_host)
    image_cmd.add_argument("--api-key", default=default_api_key)
    image_cmd.set_defaults(func=handlers["image_fetch"])

    geojson_cmd = export_sub.add_parser("geojson-fetch", help="Download export GeoJSON")
    geojson_cmd.add_argument("--job-id", required=True, help="Canonical job_id")
    geojson_cmd.add_argument("--output", default=None, help="Optional explicit output file path")
    geojson_cmd.add_argument("--host", default=default_host)
    geojson_cmd.add_argument("--api-key", default=default_api_key)
    geojson_cmd.set_defaults(func=handlers["geojson_fetch"])

    images_all_cmd = export_sub.add_parser("images-fetch-all", help="Download all export images for one job")
    images_all_cmd.add_argument("--job", required=True, help="job_id or job_number")
    images_all_cmd.add_argument(
        "--variant",
        default="auto",
        choices=["auto", "original", "report"],
        help="Preferred image variant",
    )
    images_all_cmd.add_argument("--output", default=None, help="Optional output directory")
    images_all_cmd.add_argument("--host", default=default_host)
    images_all_cmd.add_argument("--api-key", default=default_api_key)
    images_all_cmd.set_defaults(func=handlers["images_fetch_all"])
