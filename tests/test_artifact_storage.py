from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.artifact_storage import GCSArtifactStore, LocalArtifactStore


class _FakeBlob:
    def __init__(self, bucket: "_FakeBucket", name: str) -> None:
        self.bucket = bucket
        self.name = name

    def upload_from_filename(self, filename: str) -> None:
        self.bucket.objects[self.name] = Path(filename).read_bytes()

    def download_to_filename(self, filename: str) -> None:
        Path(filename).parent.mkdir(parents=True, exist_ok=True)
        Path(filename).write_bytes(self.bucket.objects[self.name])

    def exists(self) -> bool:
        return self.name in self.bucket.objects


class _FakeBucket:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def blob(self, name: str) -> _FakeBlob:
        return _FakeBlob(self, name)


class _FakeClient:
    def __init__(self) -> None:
        self.buckets: dict[str, _FakeBucket] = {}

    def bucket(self, name: str) -> _FakeBucket:
        bucket = self.buckets.get(name)
        if bucket is None:
            bucket = _FakeBucket()
            self.buckets[name] = bucket
        return bucket


class ArtifactStorageTests(unittest.TestCase):
    def test_local_store_round_trips_text(self) -> None:
        with TemporaryDirectory() as tempdir:
            store = LocalArtifactStore(Path(tempdir))
            key = store.resolve_key("jobs", "job_1", "final.json")
            path = store.write_text(key, "hello")
            self.assertEqual(path.read_text(encoding="utf-8"), "hello")
            self.assertTrue(store.exists(key))
            self.assertEqual(store.materialize_path(key), path)

    def test_gcs_store_uploads_and_materializes_via_cache(self) -> None:
        with TemporaryDirectory() as tempdir:
            client = _FakeClient()
            store = GCSArtifactStore(
                bucket_name="traq-artifacts",
                prefix="prod",
                cache_root=Path(tempdir) / "cache",
                client=client,
            )
            key = store.resolve_key("jobs", "job_1", "sections", "site_factors", "recordings", "rec_1.wav")
            local_path = store.write_bytes(key, b"abc123")
            self.assertTrue(local_path.exists())
            self.assertTrue(store.exists(key))
            bucket = client.bucket("traq-artifacts")
            self.assertEqual(bucket.objects["prod/jobs/job_1/sections/site_factors/recordings/rec_1.wav"], b"abc123")

            local_path.unlink()
            restored = store.materialize_path(key)
            self.assertEqual(restored.read_bytes(), b"abc123")

    def test_gcs_store_commits_staged_output(self) -> None:
        with TemporaryDirectory() as tempdir:
            client = _FakeClient()
            store = GCSArtifactStore(
                bucket_name="traq-artifacts",
                prefix="prod",
                cache_root=Path(tempdir) / "cache",
                client=client,
            )
            key = store.resolve_key("jobs", "job_1", "final_report_letter.pdf")
            staged = store.stage_output(key)
            staged.write_bytes(b"pdf-bytes")
            committed = store.commit_output(key, staged)
            self.assertEqual(committed.read_bytes(), b"pdf-bytes")
            bucket = client.bucket("traq-artifacts")
            self.assertEqual(bucket.objects["prod/jobs/job_1/final_report_letter.pdf"], b"pdf-bytes")


if __name__ == "__main__":
    unittest.main()
