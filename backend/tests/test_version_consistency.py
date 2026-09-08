"""The version number is in four places and they have to agree.

This is not a theoretical risk. An external review of EMCargo came back with
a list of problems that had largely been solved already, because the reviewer saw
`frontend/package.json` at 1.14.1 while the rest of the project was well past it.
Hours of work on findings that no longer existed.

One place lagging behind is operationally annoying too: `GET /api/health` then
reports a different version from the Docker tag, and a user reporting a bug
gives a number that does not match the code the bug is in.
"""

import json
import re
from pathlib import Path

from app.version import get_version

ROOT = Path(__file__).resolve().parents[2]

SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def test_the_four_places_the_version_lives_agree():
    root_version = read(ROOT / "VERSION")
    backend_version = read(ROOT / "backend" / "VERSION")
    package = json.loads((ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))

    assert SEMVER.match(root_version), f"VERSION is geen semver: {root_version!r}"
    assert backend_version == root_version, (
        f"backend/VERSION ({backend_version}) loopt achter op VERSION ({root_version})"
    )
    assert package["version"] == root_version, (
        f"frontend/package.json ({package['version']}) loopt achter op "
        f"VERSION ({root_version})"
    )
    # What the application puts out itself — this is the number that ends up in
    # a bug report.
    assert get_version() == root_version


def test_the_changelog_documents_the_current_version():
    """A version bump without a changelog entry is a release nobody can see the
    contents of."""
    version = read(ROOT / "VERSION")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## [{version}]" in changelog, (
        f"CHANGELOG.md heeft geen kop voor {version}"
    )


def test_the_changelog_leads_with_the_current_version():
    """The newest version belongs at the top; otherwise an older heading has been
    left standing or something was written under the wrong heading."""
    version = read(ROOT / "VERSION")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    headings = re.findall(r"^## \[([^\]]+)\]", changelog, re.M)
    assert headings, "CHANGELOG.md heeft geen versiekoppen"
    assert headings[0] == version, (
        f"bovenste changelog-kop is {headings[0]}, verwacht {version}"
    )
