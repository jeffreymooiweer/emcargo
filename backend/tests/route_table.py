"""The application's route table as the tests read it.

Since FastAPI 0.141 ``app.routes`` no longer holds one flattened ``APIRoute``
per address: an included router sits in it as one entry, with its prefix and
its router-level dependencies kept aside and combined on request. A test that
walked ``app.routes`` for paths and guards therefore saw nothing — and, worse,
passed, because "no route is unguarded" is vacuously true of an empty list.
``iter_route_contexts`` is FastAPI's own way to the effective table: the full
path, the methods and the dependant with the router's dependencies folded in.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from fastapi.routing import iter_route_contexts


@dataclass(frozen=True)
class Address:
    path: str
    methods: frozenset[str]
    guards: frozenset[Callable[..., Any]]
    #: Whether this is an API operation (with a dependant) or a mount, a
    #: static file handler, FastAPI's own documentation.
    operation: bool


def addresses(app) -> list[Address]:
    """Every effective address of ``app``, with the dependencies that guard it."""
    out: list[Address] = []
    for context in iter_route_contexts(app.routes):
        path = context.path
        if not path:
            continue
        dependant = getattr(context, "dependant", None)
        def dependencies(node):
            for child in node.dependencies:
                yield child.call
                yield from dependencies(child)
        guards = frozenset(dependencies(dependant)) if dependant is not None else frozenset()
        out.append(Address(path=path, methods=frozenset(context.methods or ()),
                           guards=guards, operation=dependant is not None))
    return out


def paths(app) -> set[str]:
    return {a.path for a in addresses(app)}
