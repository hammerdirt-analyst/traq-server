"""Tests for GeoJSON export storage decisions."""

from __future__ import annotations

import unittest

from server.app.db_models import Job, JobGeoJSONExport, JobStatus


class GeoJSONExportStorageTests(unittest.TestCase):
    def test_geojson_export_row_keeps_payload_on_job(self) -> None:
        job = Job(job_id="job_geo", job_number="J7777", status=JobStatus.archived)
        payload = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [-121.0, 38.5]},
                    "properties": {
                        "job_number": "J7777",
                        "user_name": "Roger Erismann",
                        "form_data": {"client_tree_details": {"gps": {"latitude": 38.5, "longitude": -121.0}}},
                        "images": [{"caption": "Tree base", "uploaded_at": "2026-03-01T10:00:00Z"}],
                    },
                }
            ],
        }
        row = JobGeoJSONExport(job=job, kind="final", payload=payload)
        job.geojson_exports.append(row)

        self.assertEqual(job.geojson_exports[0].kind, "final")
        self.assertEqual(job.geojson_exports[0].payload["type"], "FeatureCollection")
        self.assertEqual(job.geojson_exports[0].payload["features"][0]["geometry"]["type"], "Point")


if __name__ == "__main__":
    unittest.main()
