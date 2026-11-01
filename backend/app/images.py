from io import BytesIO
from pathlib import Path
import warnings
from PIL import Image, ImageOps, UnidentifiedImageError

Image.MAX_IMAGE_PIXELS = 40_000_000


def optimize_image(data: bytes):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as source:
                if source.format not in {'JPEG', 'PNG', 'WEBP', 'GIF', 'BMP', 'TIFF', 'AVIF'}:
                    raise ValueError('지원하지 않는 이미지 형식입니다.')
                source.seek(0)
                image = ImageOps.exif_transpose(source)
                image.thumbnail((3072, 3072), Image.Resampling.LANCZOS)
                image = image.convert('RGBA' if 'A' in image.getbands() or 'transparency' in image.info else 'RGB')
                width, height = image.size
                # Both encodings discard original metadata. Pick the smaller optimized representation.
                lossy, lossless = BytesIO(), BytesIO()
                image.save(lossy, 'WEBP', quality=92, method=6)
                image.save(lossless, 'WEBP', lossless=True, method=6)
                compressed = min((lossy.getvalue(), lossless.getvalue()), key=len)
                return compressed, width, height
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError('이미지를 읽을 수 없거나 해상도가 너무 큽니다. 최대 4천만 픽셀입니다.') from exc
