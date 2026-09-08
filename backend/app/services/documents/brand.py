"""Whose name is on the paper.

Every document EMCargo draws itself carries the installation's brand: the
name an administrator set (``brand_name``, or ``BRAND_NAME`` in the
environment) and the logo they uploaded, and EMCargo's own name and logo
where nothing was set. The official forms — CMR, CIM, AVC — are not touched:
they are somebody else's paper, filled in.

The brand is resolved once per request, at the two places that start a
rendering (the single export and the bundle), and read by every renderer
through :func:`current`. A context variable rather than a parameter, because
seven renderers and a dozen call sites would otherwise each carry a value
they only pass on — and the next renderer would forget to.
"""
from __future__ import annotations

import io
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path

from PIL import Image as PILImage
from sqlalchemy.orm import Session

DEFAULT_NAME = "EMCargo"
DEFAULT_LOGO = Path(__file__).resolve().parents[2] / "assets" / "logo.png"


@dataclass(frozen=True)
class Brand:
    name: str
    #: PNG, JPEG or WebP bytes that PIL can open, or nothing.
    logo: bytes | None
    #: Whether an installation set a brand of its own, or this is the default.
    own: bool

    def logo_size(self) -> tuple[int, int] | None:
        if not self.logo:
            return None
        try:
            with PILImage.open(io.BytesIO(self.logo)) as image:
                return image.size
        except Exception:
            return None


_current: ContextVar[Brand | None] = ContextVar("document_brand", default=None)


def _default_logo() -> bytes | None:
    try:
        return DEFAULT_LOGO.read_bytes()
    except OSError:
        return None


def default() -> Brand:
    return Brand(name=DEFAULT_NAME, logo=_default_logo(), own=False)


def resolve(db: Session | None) -> Brand:
    """The installation's brand, or the default where nothing is set."""
    if db is None:
        return default()
    from app.services import branding
    from app.services.settings_store import instance_settings

    name = str(getattr(instance_settings(db), "brand_name", "") or "").strip()
    uploaded = branding.logo_image()
    logo = uploaded[0] if uploaded else None
    if not name and not logo:
        return default()
    return Brand(name=name or DEFAULT_NAME, logo=logo or _default_logo(), own=True)


def use(db: Session | None) -> Brand:
    """Resolve the brand for this request and make it the current one."""
    brand = resolve(db)
    _current.set(brand)
    return brand


def set_current(brand: Brand | None) -> None:
    _current.set(brand)


def current() -> Brand:
    return _current.get() or default()


def fill(text: str) -> str:
    """``{brand}`` in a document text, replaced by the current name."""
    return text.replace("{brand}", current().name) if isinstance(text, str) else text
