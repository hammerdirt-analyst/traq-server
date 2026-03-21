from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from app.services.tree_identification_service import (
    MAX_TREE_IDENTIFICATION_IMAGES,
    TreeIdentificationConfigError,
    TreeIdentificationImage,
    TreeIdentificationService,
)


class TreeIdentificationServiceTests(unittest.TestCase):
    def test_identify_requires_api_key(self) -> None:
        service = TreeIdentificationService(
            api_key=None,
            base_url="https://my-api.plantnet.org",
            default_project="all",
        )
        with self.assertRaises(TreeIdentificationConfigError):
            service.identify(
                images=[
                    TreeIdentificationImage(
                        filename="leaf.jpg",
                        content_type="image/jpeg",
                        data=b"jpeg",
                    )
                ]
            )

    def test_identify_rejects_more_than_five_images(self) -> None:
        service = TreeIdentificationService(
            api_key="demo-key",
            base_url="https://my-api.plantnet.org",
            default_project="all",
        )
        with self.assertRaises(ValueError):
            service.identify(
                images=[
                    TreeIdentificationImage(
                        filename=f"leaf-{index}.jpg",
                        content_type="image/jpeg",
                        data=b"jpeg",
                    )
                    for index in range(MAX_TREE_IDENTIFICATION_IMAGES + 1)
                ]
            )

    def test_identify_normalizes_upstream_payload(self) -> None:
        service = TreeIdentificationService(
            api_key="demo-key",
            base_url="https://my-api.plantnet.org",
            default_project="all",
        )

        class DummyResponse:
            def __init__(self, payload: dict) -> None:
                self._payload = payload

            def read(self) -> bytes:
                return json.dumps(self._payload).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb) -> None:
                return None

        payload = {
            "query": {"project": "all"},
            "predictedOrgans": [{"organ": "leaf", "score": 0.9}],
            "bestMatch": "Ajuga genevensis L.",
            "results": [{"score": 0.9, "species": {"scientificNameWithoutAuthor": "Ajuga genevensis"}}],
            "otherResults": [{"score": 0.1}],
            "version": "2025-01-17 (7.3)",
            "remainingIdentificationRequests": 498,
        }

        with patch("app.services.tree_identification_service.request.urlopen", return_value=DummyResponse(payload)):
            result = service.identify(
                images=[
                    TreeIdentificationImage(
                        filename="leaf.jpg",
                        content_type="image/jpeg",
                        data=b"jpeg",
                    )
                ],
                organs=["leaf"],
                nb_results=3,
            )

        self.assertEqual(result["bestMatch"], "Ajuga genevensis L.")
        self.assertEqual(result["remainingIdentificationRequests"], 498)
        self.assertEqual(result["version"], "2025-01-17 (7.3)")
        self.assertEqual(len(result["results"]), 1)
        self.assertEqual(len(result["otherResults"]), 1)


if __name__ == "__main__":
    unittest.main()
