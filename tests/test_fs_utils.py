from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.fs_utils import write_json_file


class FsUtilsTests(unittest.TestCase):
    def test_write_json_file_creates_missing_parent_directories(self) -> None:
        with TemporaryDirectory() as tempdir:
            target = Path(tempdir) / 'jobs' / 'job_1' / 'sections' / 'job_photos' / 'images' / 'img_1.meta.json'
            write_json_file(target, {'image_id': 'img_1'})
            self.assertTrue(target.exists())
            self.assertEqual(json.loads(target.read_text(encoding='utf-8')), {'image_id': 'img_1'})


if __name__ == '__main__':
    unittest.main()
