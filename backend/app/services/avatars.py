"""Decode profile uploads into small, metadata-free, static WebP images."""
from hashlib import sha256
from io import BytesIO
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.messages import error

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 16_000_000


def normalize(data: bytes) -> tuple[bytes, str]:
    if len(data) > MAX_UPLOAD_BYTES:
        raise error(413, "avatar.too_large")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as source:
                if source.format not in {"JPEG", "PNG", "WEBP"} or getattr(source, "is_animated", False):
                    raise error(400, "avatar.invalid")
                if source.width * source.height > MAX_PIXELS:
                    raise error(413, "avatar.too_large")
                source.load()
                oriented = ImageOps.exif_transpose(source)
                image = ImageOps.fit(oriented.convert("RGBA"), (256, 256), method=Image.Resampling.LANCZOS)
                # New pixel storage intentionally excludes EXIF, comments and
                # embedded profiles; uploaded filenames never become paths.
                clean = Image.frombytes("RGBA", image.size, image.tobytes())
                output = BytesIO()
                clean.save(output, "WEBP", quality=85, method=4)
                rendered = output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise error(400, "avatar.invalid") from None
    return rendered, sha256(rendered).hexdigest()
