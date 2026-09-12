"""Wizard import: spreadsheet to pasted text.

The wizard reads `description | quantity | unit`. A spreadsheet that comes from
somebody else rarely has those columns in that order and under those names, and
until now the import guessed silently: if it did not recognise the heading row,
it took columns 0, 1 and 2. With `Item no | Description | Quantity | Unit` that
yields the item number as the description and the description as the quantity.
What the user sees of that is `status=error` and 0 kg, with no hint that the
column mapping is to blame.

This module still guesses — it has to, or every import becomes handwork — but it
now says what it did and on what basis. With that information the interface can
let the mapping be adjusted instead of leaving the user with an unexplained zero.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from app.services.parser.paste_parser import detect_columns
from app.services.spreadsheet_io import rows_to_pipe_text

WIZARD_HEADERS = ["description", "quantity", "unit"]
WIZARD_EXAMPLE = ["staal hoekprofiel 80x80x8x6000", "8", "stuks"]

# How many sample values per column travel to the interface: enough to see
# *what* is in a column, few enough not to send half a consignment to a screen
# that does nothing further with it.
SAMPLE_ROWS = 3


@dataclass
class Column:
    """One column from the file, as the user recognises it."""

    index: int
    header: str
    samples: list[str] = field(default_factory=list)


@dataclass
class Analysis:
    """What the import made of this file, and how certain that is.

    `source` carries the difference that matters: "header" means the heading row
    was recognised, "position" that it was guessed from the order. Only in the
    second case is there reason to ask the user anything.
    """

    columns: list[Column]
    mapping: dict[str, int | None]
    source: str
    has_header: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "columns": [asdict(column) for column in self.columns],
            "mapping": self.mapping,
            "source": self.source,
            "has_header": self.has_header,
        }


def _columns(rows: list[list[str]], has_header: bool) -> list[Column]:
    width = max((len(row) for row in rows), default=0)
    body = rows[1:] if has_header else rows
    columns = []
    for index in range(width):
        header = rows[0][index] if has_header and index < len(rows[0]) else ""
        samples = [
            str(row[index]).strip()
            for row in body[:SAMPLE_ROWS]
            if index < len(row) and str(row[index]).strip()
        ]
        columns.append(Column(index=index, header=str(header).strip(), samples=samples))
    return columns


def analyse(rows: list[list[str]]) -> Analysis:
    """Which column passes for what, and whether that was recognised or guessed."""
    if not rows:
        return Analysis(columns=[], mapping={key: None for key in WIZARD_HEADERS},
                        source="none", has_header=False)

    header_map = detect_columns([str(cell).lower().strip() for cell in rows[0]])
    has_header = header_map["description"] is not None or header_map["quantity"] is not None
    if has_header:
        return Analysis(columns=_columns(rows, True), mapping=header_map,
                        source="header", has_header=True)

    # Nothing recognised: guess from the order, exactly as before — but now with
    # the notice that it is a guess.
    width = max((len(row) for row in rows), default=0)
    mapping: dict[str, int | None] = {
        "description": 0 if width >= 1 else None,
        "quantity": 1 if width >= 2 else None,
        "unit": 2 if width >= 3 else None,
    }
    return Analysis(columns=_columns(rows, False), mapping=mapping,
                    source="position", has_header=False)


def apply_mapping(rows: list[list[str]], mapping: dict[str, int | None],
                  has_header: bool) -> str:
    """Convert the rows with the mapping the user has chosen.

    Nothing of the file is left behind: the rows come with the request and go
    back as text. A consignment left lying half-finished on the server would
    conflict with what this application promises about storage.
    """
    body = rows[1:] if has_header else rows
    lines = []
    for row in body:
        def cell(key: str) -> str:
            index = mapping.get(key)
            if index is None or index < 0 or index >= len(row):
                return ""
            return str(row[index]).strip()

        description = cell("description")
        if not description:
            # A line without a description cannot be recognised and only
            # produces an error line in the wizard.
            continue
        lines.append(" | ".join([description, cell("quantity"), cell("unit")]).rstrip(" |"))
    return "\n".join(lines)


def spreadsheet_to_wizard_text(rows: list[list[str]]) -> tuple[str, bool]:
    if not rows:
        return "", False
    header_map = detect_columns([str(cell).lower().strip() for cell in rows[0]])
    has_header = header_map["description"] is not None or header_map["quantity"] is not None
    if has_header:
        return apply_mapping(rows, header_map, True), True
    return rows_to_pipe_text(rows, skip_header=has_header), has_header
