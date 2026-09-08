"""The changelog, parsed so the interface can say what an update brought.

EMCargo updates itself the way any single-container app does: the operator
pulls a newer image and the next login is silently a different program. The
what's-new card closes that gap — after an update, the entries between the
version a user last saw and the version now running are shown once.

The source of truth is ``CHANGELOG.md`` itself, the same file a release is
written into. Serving it rather than duplicating it means the card can never
disagree with the record; the price is a parser, kept honest by the file's
one uniform heading form ``## [X.Y.Z] — YYYY-MM-DD``. The file rides along in
the Docker image next to ``VERSION`` (see the Dockerfile), and its entries
are in English by design — the repository's language — while the card's own
chrome is translated like the rest of the interface.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

#: In the image the file sits at /app/CHANGELOG.md beside /app/backend; in a
#: checkout it sits at the repository root. Same two-step lookup as VERSION.
_CANDIDATES = [
    Path(__file__).resolve().parents[2] / "CHANGELOG.md",
    Path(__file__).resolve().parents[3] / "CHANGELOG.md",
]

#: Every one of the file's release headings prints an em dash between the
#: version and the date; the character class also takes a hyphen so a heading
#: typed on a keyboard without one still parses.
_HEADING = re.compile(r"^## \[(\d+\.\d+\.\d+)\] [—–-]+ (\d{4}-\d{2}-\d{2})\s*$")

#: More than this many unseen releases stops being release notes and becomes
#: the whole history; the response says it was cut short instead.
MAX_ENTRIES = 20


def changelog_path() -> Path | None:
    for path in _CANDIDATES:
        if path.exists():
            return path
    return None


@lru_cache(maxsize=4)
def _parse(path: Path, mtime: float) -> tuple[dict, ...]:
    """All releases, newest first, exactly as the file orders them.

    The mtime is part of the cache key on purpose: a container never rewrites
    its changelog, but the development server does on every release.
    """
    entries: list[dict] = []
    body: list[str] = []
    current: dict | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _HEADING.match(line)
        if match:
            if current is not None:
                current["body"] = "\n".join(body).strip()
                entries.append(current)
            current = {"version": match.group(1), "date": match.group(2)}
            body = []
        elif current is not None:
            body.append(line)
    if current is not None:
        current["body"] = "\n".join(body).strip()
        entries.append(current)
    return tuple(entries)


def entries() -> list[dict]:
    path = changelog_path()
    if path is None:
        return []
    return [dict(entry) for entry in _parse(path, path.stat().st_mtime)]


def _version_key(version: str) -> tuple[int, ...] | None:
    try:
        return tuple(int(part) for part in version.split("."))
    except ValueError:
        return None


def entries_since(since: str) -> dict:
    """The releases newer than ``since``, newest first, capped at MAX_ENTRIES.

    An empty or unparseable ``since`` means the caller has no marker at all —
    a fresh account, or one from before the marker existed. That gets the cap's
    worth of history and ``truncated`` set if there was more; the interface
    decides for itself that a first login shows nothing.
    """
    all_entries = entries()
    floor = _version_key((since or "").strip())
    if floor is not None:
        newer = [e for e in all_entries
                 if (key := _version_key(e["version"])) is not None and key > floor]
    else:
        newer = list(all_entries)
    return {
        "entries": newer[:MAX_ENTRIES],
        "truncated": len(newer) > MAX_ENTRIES,
    }
