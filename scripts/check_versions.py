#!/usr/bin/env python3
"""Fail CI when EMCargo's published version files disagree.

Four files carry the version and they have to say the same thing: ``VERSION``,
``backend/VERSION``, ``frontend/package.json`` and — twice — the lock file that
npm generates from it.

That last one is the reason this script grew. The lock file was left out, so it
drifted at every release, and the release workflow repaired it by committing to
``main`` after the merge. The repair worked, but it moved ``main`` out from under
whatever branch came next, which then conflicted on ``VERSION`` and
``CHANGELOG.md`` and could not be merged until it was rebased. Twice in one day.

Checking it here moves the failure to where the mistake is made: a pull request
that forgot the lock file goes red before it is merged, and the release does not
have to write to ``main`` at all. Use ``scripts/bump_version.py`` and this stays
green by construction.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def collect() -> dict[str, str]:
    """Every place the version is written, and what it says there."""
    package = json.loads((ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((ROOT / "frontend" / "package-lock.json").read_text(encoding="utf-8"))
    return {
        "VERSION": (ROOT / "VERSION").read_text(encoding="utf-8").strip(),
        "backend/VERSION": (ROOT / "backend" / "VERSION").read_text(encoding="utf-8").strip(),
        "frontend/package.json": package.get("version", ""),
        # npm writes the version in two places and keeps them in step; if we
        # only checked one, a half-updated lock file would still pass.
        "frontend/package-lock.json": lock.get("version", ""),
        'frontend/package-lock.json packages[""]': (
            lock.get("packages", {}).get("", {}).get("version", "")
        ),
    }


def main() -> None:
    versions = collect()
    unique = set(versions.values())
    if len(unique) != 1:
        print("EMCargo version mismatch:", file=sys.stderr)
        for name, version in versions.items():
            print(f"  {name}: {version or '(missing)'}", file=sys.stderr)
        print(
            "\nRun `python scripts/bump_version.py <version>` to set all of them at once.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    print(f"EMCargo version is consistent: {unique.pop()}")


if __name__ == "__main__":
    main()
