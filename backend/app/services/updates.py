"""Whether a newer EMCargo exists — asked, never acted on.

A container cannot update itself: the operator pulls a newer image, by hand or
through whatever they run for the purpose. What the application *can* do is
tell the administrator that there is something to pull. That takes exactly one
outbound request — GitHub's latest-release endpoint — and outbound requests
are the administrator's to allow, so the whole check sits behind the
``update_check_enabled`` switch next to address lookup and catalogue sync.

The answer is cached in-process: a successful reading is good for six hours
(release cadence is days, not minutes), a failed one for fifteen minutes so a
GitHub outage does not turn every settings visit into an eight-second wait.
"""
from __future__ import annotations

import logging
import time

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

RELEASES_URL = "https://api.github.com/repos/jeffreymooiweer/emcargo/releases/latest"
SUCCESS_TTL_SECONDS = 6 * 3600
FAILURE_TTL_SECONDS = 15 * 60

_cache: dict = {"at": 0.0, "release": None, "checked": False}


def version_key(version: str) -> tuple[int, ...] | None:
    try:
        return tuple(int(part) for part in (version or "").strip().split("."))
    except ValueError:
        return None


def clear_cache() -> None:
    _cache.update(at=0.0, release=None, checked=False)


def latest_release() -> dict | None:
    """The newest published release, or None when GitHub cannot say.

    None covers every way of not knowing — network down, rate limited, a tag
    that is not a version — because they all call for the same honest answer:
    the check did not work, not "you are up to date".
    """
    now = time.monotonic()
    ttl = SUCCESS_TTL_SECONDS if _cache["release"] is not None else FAILURE_TTL_SECONDS
    if _cache["checked"] and now - _cache["at"] < ttl:
        return _cache["release"]

    release = None
    try:
        response = httpx.get(
            RELEASES_URL,
            timeout=get_settings().update_check_timeout_seconds,
            headers={"Accept": "application/vnd.github+json"},
            follow_redirects=True,
        )
        response.raise_for_status()
        data = response.json()
        version = str(data.get("tag_name") or "").lstrip("v")
        if version_key(version) is not None:
            release = {"version": version, "url": str(data.get("html_url") or "")}
    except (httpx.HTTPError, ValueError) as exc:
        logger.info("Update check could not reach GitHub: %s", exc)

    _cache.update(at=now, release=release, checked=True)
    return release
