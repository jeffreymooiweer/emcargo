"""What the installation looks like: a logo and the six tile images.

An organisation that hosts EMCargo for its own people would rather see its
own name on the door and its own pictures on the tiles. The name is an
instance setting (``brand_name``, with ``BRAND_NAME`` in the environment as
its starting value, like every other one). The images are files, and this
module is the whole of how they are kept:

- **Where.** ``DATA_DIR/branding``, one file per asset, named by what it is:
  ``logo.png``, ``modality-road.jpg``. The extension follows the bytes, not
  the upload's own name, so a file on disk is what it says it is. Operators
  may place the same files there by hand.
- **What.** PNG, JPEG or WebP, recognised by their first bytes rather than by
  the name or the declared type, both of which the uploader chooses. SVG is
  deliberately not accepted: it is a document that can carry script, and an
  image route that serves one is a page that runs it.
- **How much.** A logo is a megabyte at most, a tile three; more is not a
  logo. The caps are checked while reading, so an oversized upload is refused
  before it is held in memory whole.
- **Replacing.** Written beside, then moved over the old one, so a browser
  that asks in the middle of an upload gets the old picture or the new one
  and never half of either.

Nothing here reads the database. The images are public by nature — they are
what stands on the door — and the routes that serve them ask for no sign-in.
"""
from __future__ import annotations

import os
from pathlib import Path

from app.core.config import get_settings
from app.schemas.settings import MODALITIES

MAX_LOGO_BYTES = 1 * 1024 * 1024
MAX_MODALITY_BYTES = 3 * 1024 * 1024

#: The first bytes of each accepted format, the media type it is served as,
#: and the extension it is stored under.
_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "image/png", "png"),
    (b"\xff\xd8\xff", "image/jpeg", "jpg"),
)
_EXTENSIONS = ("png", "jpg", "webp")
_MEDIA_TYPES = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp"}


class BrandingError(ValueError):
    """An upload that is not an image this installation will show."""


def sniff(data: bytes) -> tuple[str, str] | None:
    """``(media type, extension)`` from the first bytes, or ``None``."""
    for magic, media_type, extension in _SIGNATURES:
        if data.startswith(magic):
            return media_type, extension
    # WebP is a RIFF container whose form type says WEBP.
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", "webp"
    return None


def directory() -> Path:
    return get_settings().data_dir / "branding"


def _stem(name: str) -> str:
    if name == "logo":
        return "logo"
    if name in MODALITIES:
        return f"modality-{name}"
    raise KeyError(name)


def limit_for(name: str) -> int:
    return MAX_LOGO_BYTES if name == "logo" else MAX_MODALITY_BYTES


def asset(name: str) -> tuple[Path, str] | None:
    """The stored file for ``logo`` or a modality key, with its media type.

    Looked up by the extensions this module writes, so a stray file with
    another extension — or a symlink somebody planted — is not served.
    """
    stem = _stem(name)
    for extension in _EXTENSIONS:
        candidate = directory() / f"{stem}.{extension}"
        if candidate.is_file():
            return candidate, _MEDIA_TYPES[extension]
    return None


def store(name: str, data: bytes) -> Path:
    """Keep ``data`` as the asset ``name``, replacing whatever was there."""
    if len(data) > limit_for(name):
        raise BrandingError("The image exceeds the size limit.")
    kind = sniff(data)
    if kind is None:
        raise BrandingError("Not a PNG, JPEG or WebP image.")
    _, extension = kind
    folder = directory()
    folder.mkdir(parents=True, exist_ok=True)
    stem = _stem(name)
    final = folder / f"{stem}.{extension}"
    partial = folder / f"{stem}.{extension}.part"
    partial.write_bytes(data)
    os.replace(partial, final)
    # A replacement in another format must not leave the old one beside it,
    # or ``asset`` would keep finding the old one first.
    for other in _EXTENSIONS:
        if other != extension:
            (folder / f"{stem}.{other}").unlink(missing_ok=True)
    return final


def remove(name: str) -> bool:
    """Back to the default picture. True when there was something to remove."""
    stem = _stem(name)
    removed = False
    for extension in _EXTENSIONS:
        path = directory() / f"{stem}.{extension}"
        if path.is_file():
            path.unlink()
            removed = True
    return removed


def _url(name: str, path: Path) -> str:
    # The modification time in the address, so a browser that cached the old
    # picture for a year asks for the new one the moment it changes.
    version = int(path.stat().st_mtime)
    if name == "logo":
        return f"/api/branding/logo?v={version}"
    return f"/api/branding/modality/{name}?v={version}"


def assets() -> dict:
    """Which pictures this installation has of its own, as addresses."""
    logo = asset("logo")
    return {
        "logo": _url("logo", logo[0]) if logo else None,
        "modalities": {
            key: (_url(key, found[0]) if (found := asset(key)) else None)
            for key in MODALITIES
        },
    }


def logo_image() -> tuple[bytes, str] | None:
    """The uploaded logo's bytes and MIME subtype, for the mail templates."""
    found = asset("logo")
    if not found:
        return None
    path, media_type = found
    try:
        return path.read_bytes(), media_type.split("/", 1)[1]
    except OSError:
        return None
