import importlib.util
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import unittest
from unittest.mock import patch


ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('public_check',ROOT/'tools/check_public.py')
public_check=importlib.util.module_from_spec(spec)
spec.loader.exec_module(public_check)


class PublicAssetTests(unittest.TestCase):
    def setUp(self):
        self.name='docs/screenshots/codex-settings.jpg'
        self.body=(ROOT/self.name).read_bytes()

    def test_reviewed_capture_has_exact_approved_bytes(self):
        self.assertTrue(public_check.approved_screenshot(self.name,self.body))

    def test_same_image_in_a_private_or_unreviewed_path_is_rejected(self):
        for name in ('test-results/account.jpg','docs/screenshots/another-account.jpg','docs/screenshots/codex-settings.jpeg'):
            self.assertFalse(public_check.approved_screenshot(name,self.body))

    def test_adding_metadata_or_replacing_pixels_invalidates_approval(self):
        # A previously reviewed filename does not approve a later unredacted capture.
        for changed in (self.body[:2]+b'EXIF private metadata'+self.body[2:],self.body[:-3]+b'X'+self.body[-2:]):
            self.assertFalse(public_check.approved_screenshot(self.name,changed))

    def test_public_scan_still_rejects_unreviewed_image(self):
        with patch.object(public_check,'tracked_files',return_value=['docs/screenshots/unreviewed.jpg']),patch.object(public_check,'staged_bytes',return_value=self.body),redirect_stdout(StringIO()):
            with self.assertRaises(RuntimeError):public_check.verify()


if __name__=='__main__':unittest.main()
