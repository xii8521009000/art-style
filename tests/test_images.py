"""Upload regressions: hostile input, privacy metadata, alpha and oversized images."""
from io import BytesIO
from pathlib import Path
import sys
import unittest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.images import optimize_image


class ImageTests(unittest.TestCase):
    def test_reject_non_image(self):
        with self.assertRaises(ValueError):
            optimize_image(b'<svg onload="alert(1)"></svg>')

    def test_orientation_and_private_metadata(self):
        source = BytesIO()
        exif = Image.Exif()
        exif[274] = 6
        exif[270] = 'private metadata must not survive'
        Image.new('RGB', (120, 80), 'red').save(source, 'JPEG', exif=exif)
        data, width, height = optimize_image(source.getvalue())
        result = Image.open(BytesIO(data))
        self.assertEqual((width, height), (80, 120))
        self.assertFalse(result.getexif())

    def test_alpha_and_size_limit(self):
        source = BytesIO()
        Image.new('RGBA', (4000, 2000), (30, 60, 90, 128)).save(source, 'PNG')
        data, width, height = optimize_image(source.getvalue())
        result = Image.open(BytesIO(data))
        self.assertEqual((width, height), (3072, 1536))
        self.assertEqual(result.getpixel((0, 0))[3], 128)


if __name__ == '__main__':
    unittest.main()
