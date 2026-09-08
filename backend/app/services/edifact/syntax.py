"""The UN/EDIFACT syntax: segments as values, and values as segments.

ISO 9735 in the small: a segment is a tag and a list of data elements, a
data element is a value or a composite of component values, and five
service characters keep them apart — ``:`` between components, ``+``
between elements, ``.`` as the decimal mark, ``?`` as the release character
and ``'`` as the segment terminator. ``UNA:+.? '`` at the front says so.

Two rules matter more than the rest and both live here so a message cannot
get them wrong by accident. **Everything is escaped**: a value that carries
one of the service characters gets a ``?`` in front of it, which is the one
way a consignee named "O'Neill & Sons" survives the trip. **Nothing trails**:
empty elements and components at the end of a segment or composite are
dropped, because ``NAD+CZ+++Afzender BV''`` and ``NAD+CZ+++Afzender BV+++''``
are the same segment and the shorter is the one every reader expects.

The reverse direction, ``parse``, exists for the tests and for the validator:
a message EMCargo wrote is read back and checked against the segment table
before it is handed out.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

COMPONENT = ":"
ELEMENT = "+"
DECIMAL = "."
RELEASE = "?"
TERMINATOR = "'"

#: The service string advice that names the characters above.
UNA = f"UNA{COMPONENT}{ELEMENT}{DECIMAL}{RELEASE} {TERMINATOR}"

_SERVICE = (RELEASE, COMPONENT, ELEMENT, TERMINATOR)

Element = str | list[str] | None


@dataclass
class Segment:
    tag: str
    elements: list[Element] = field(default_factory=list)

    def __getitem__(self, index: int) -> Element:
        return self.elements[index] if index < len(self.elements) else None


def escape(value: Any) -> str:
    text = "" if value is None else str(value)
    for char in _SERVICE:
        text = text.replace(char, RELEASE + char)
    return text


def _trim(values: list[str]) -> list[str]:
    values = list(values)
    while values and values[-1] == "":
        values.pop()
    return values


def write_segment(segment: Segment) -> str:
    """One segment as text, escaped and trimmed, terminator included."""
    rendered: list[str] = []
    for element in segment.elements:
        if isinstance(element, list):
            rendered.append(COMPONENT.join(_trim([escape(c) for c in element])))
        else:
            rendered.append(escape(element))
    return segment.tag + "".join(ELEMENT + e for e in _trim(rendered)) + TERMINATOR


def write(segments: list[Segment], una: bool = True) -> str:
    """The interchange as text, one segment per line for a person to read.

    The line breaks are outside the segments and after each terminator, so
    a reader that ignores whitespace between segments — every EDIFACT
    reader — sees exactly the same stream as without them.
    """
    lines = [UNA] if una else []
    lines.extend(write_segment(s) for s in segments)
    return "\n".join(lines) + "\n"


def parse(text: str) -> list[Segment]:
    """The segments of an interchange written by :func:`write`, values
    unescaped, composites as lists. ``UNA`` is read and dropped."""
    text = text.strip()
    if text.startswith("UNA"):
        text = text[9:]
    segments: list[Segment] = []
    for raw in _split(text, TERMINATOR):
        raw = raw.strip()
        if not raw:
            continue
        parts = _split(raw, ELEMENT)
        tag = parts[0]
        elements: list[Element] = []
        for part in parts[1:]:
            components = [_unescape(c) for c in _split(part, COMPONENT)]
            elements.append(components if len(components) > 1 else components[0])
        segments.append(Segment(tag, elements))
    return segments


def _split(text: str, separator: str) -> list[str]:
    """Split on a service character, honouring the release character."""
    parts: list[str] = []
    current: list[str] = []
    i = 0
    while i < len(text):
        char = text[i]
        if char == RELEASE and i + 1 < len(text):
            current.append(char + text[i + 1])
            i += 2
            continue
        if char == separator:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
        i += 1
    parts.append("".join(current))
    return parts


def _unescape(text: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(text):
        if text[i] == RELEASE and i + 1 < len(text):
            out.append(text[i + 1])
            i += 2
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def validate(segments: list[Segment], structure: list[dict[str, Any]]) -> list[str]:
    """Check a message against a segment table.

    ``structure`` is the table as ``config/iftdgn_d16a.json`` holds it: a
    list of nodes, each a segment (``tag``) or a group (``group`` with
    ``children``), with a status (``M`` or ``C``) and a maximum repeat.
    Matching is the ordinary sequential one: each node takes as many
    consecutive segments as it may, a group starts on its first child's tag,
    and what a node does not take falls through to the next. Returns the
    problems found, empty when the message conforms.
    """
    errors: list[str] = []
    end = _match(structure, segments, 0, errors, "")
    if end < len(segments):
        errors.append(f"unexpected segment {segments[end].tag} at position {end + 1}")
    return errors


def _trigger(node: dict[str, Any]) -> str:
    child = node["children"][0]
    return child["tag"] if "tag" in child else _trigger(child)


def _match(nodes: list[dict[str, Any]], segments: list[Segment], index: int,
           errors: list[str], where: str) -> int:
    for node in nodes:
        label = f"{where}{node.get('tag') or 'SG' + str(node['group'])} ({node['pos']})"
        if "tag" in node:
            count = 0
            while index < len(segments) and segments[index].tag == node["tag"] and count < node["max"]:
                index += 1
                count += 1
            if index < len(segments) and segments[index].tag == node["tag"] and count >= node["max"]:
                errors.append(f"{label}: more than {node['max']} occurrences")
            if node["status"] == "M" and count == 0:
                errors.append(f"{label}: mandatory segment missing")
            continue
        trigger = _trigger(node)
        repeats = 0
        while index < len(segments) and segments[index].tag == trigger and repeats < node["max"]:
            index = _match(node["children"], segments, index, errors, f"{label} > ")
            repeats += 1
        if node["status"] == "M" and repeats == 0:
            errors.append(f"{label}: mandatory group missing")
    return index
