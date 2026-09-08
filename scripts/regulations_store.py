#!/usr/bin/env python3
"""The document store behind the regulatory database.

Every fact in ``backend/seed/dg`` was read out of a book, and this session
after session turned out to be the fragile half: UNECE refuses non-browser
requests, the web archive rate-limits by mood, the Dutch editions arrived as
uploads into a container that forgets. The books themselves cannot go into the
repository — they are not ours to redistribute, and ``docs/data-sources.md``
promises they never will — so what the repository holds is this register:
``backend/seed/dg/sources.json``, one entry per document, with the sha256 of
the exact file the facts were read from.

This tool connects the register to a directory that lasts:

    python scripts/regulations_store.py status
        What the store holds, what is missing, what fails its hash.

    python scripts/regulations_store.py fetch [id ...]
        Download every fetchable document that is missing (or the named ones),
        through the same ladder read_land_regulations.py uses: browser
        headers first, the web archive when the publisher refuses.

    python scripts/regulations_store.py add <id> <file>
        Register a document obtained by hand — the Dutch editions came this
        way. Copies the file in under its canonical name and pins its sha256
        into sources.json if none is pinned yet.

    python scripts/regulations_store.py verify
        Exit non-zero if any present document contradicts its pinned hash.

The store is ``/data/regulations`` (a volume that outlives the container),
overridable with ``EMCARGO_REGULATIONS_DIR``; the CI cache path
``/tmp/emcargo-regulations`` is read as a fallback so runner-fetched
volumes count too. A hash pinned once is never silently rewritten: a mismatch
is an error to look at, because either the publisher changed the file or the
store copy is damaged — and those two need different answers.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "backend" / "seed" / "dg" / "sources.json"

sys.path.insert(0, str(ROOT / "scripts"))
import read_land_regulations as reader  # noqa: E402


def load_manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def store_dir(manifest: dict) -> Path:
    override = os.environ.get(manifest["store"]["environment_variable"])
    if override:
        return Path(override)
    default = Path(manifest["store"]["default_path"])
    if default.parent.is_dir():
        return default
    return Path(manifest["store"]["fallback_path"])


def locate(manifest: dict, doc: dict) -> Path | None:
    """The document's file, wherever it currently lives."""
    for base in (store_dir(manifest), Path(manifest["store"]["fallback_path"])):
        candidate = base / doc["filename"]
        if candidate.is_file() and candidate.stat().st_size > 0:
            return candidate
    return None


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _pin(manifest: dict, doc: dict, value: str) -> None:
    doc["sha256"] = value
    MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"    pinned sha256 for {doc['id']} into {MANIFEST.name}")


def cmd_status(manifest: dict) -> int:
    base = store_dir(manifest)
    print(f"store: {base}")
    missing = 0
    for doc in manifest["documents"]:
        path = locate(manifest, doc)
        if path is None:
            state = "missing" + ("" if doc["urls"] else " (no URL — operator-supplied)")
            missing += 1
        elif doc["sha256"] is None:
            state = f"present, hash not pinned ({path})"
        elif sha256(path) == doc["sha256"]:
            state = f"present, hash verified ({path})"
        else:
            state = f"PRESENT BUT WRONG HASH ({path})"
        print(f"  {doc['id']:16s} {state}")
    return 0 if missing == 0 else 1


def cmd_fetch(manifest: dict, ids: list[str]) -> int:
    base = store_dir(manifest)
    base.mkdir(parents=True, exist_ok=True)
    reader.CACHE = base  # the reader's download ladder writes where we point it
    failures = 0
    for doc in manifest["documents"]:
        if ids and doc["id"] not in ids:
            continue
        if not doc["urls"]:
            if ids:
                print(f"  {doc['id']}: operator-supplied, nothing to fetch")
            continue
        if locate(manifest, doc):
            continue
        try:
            if doc["id"] in reader.SOURCES:
                fetched = reader.fetch(doc["id"])
                target = base / doc["filename"]
                if fetched != target:
                    shutil.move(fetched, target)
            else:
                target = base / doc["filename"]
                code, _kind = reader._ask(doc["urls"][0], target, [], "direct")
                if not target.is_file() or target.stat().st_size == 0:
                    raise SystemExit(f"download answered {code}")
        except SystemExit as exc:
            print(f"  {doc['id']}: could not fetch — {exc}")
            failures += 1
            continue
        digest = sha256(target)
        if doc["sha256"] is None:
            _pin(manifest, doc, digest)
        elif digest != doc["sha256"]:
            print(f"  {doc['id']}: FETCHED FILE CONTRADICTS PINNED HASH — "
                  "either the publisher replaced the file (a new printing, or "
                  "worse) or the download is damaged. Not overwriting the pin; "
                  "read the two files before believing either.")
            failures += 1
        # The hash goes to the log deliberately: a runner cannot commit the pin,
        # so the log line is what a pin is later copied from.
        print(f"  {doc['id']}: {target} "
              f"({target.stat().st_size:,} bytes, sha256 {digest})")
    return 1 if failures else 0


def cmd_add(manifest: dict, doc_id: str, source: Path) -> int:
    docs = {doc["id"]: doc for doc in manifest["documents"]}
    if doc_id not in docs:
        print(f"unknown id {doc_id!r}; the register knows: {', '.join(docs)}")
        return 1
    doc = docs[doc_id]
    base = store_dir(manifest)
    base.mkdir(parents=True, exist_ok=True)
    target = base / doc["filename"]
    digest = sha256(source)
    if doc["sha256"] is not None and digest != doc["sha256"]:
        print(f"  {doc_id}: this file contradicts the pinned hash. If it is a "
              "newer edition, that is a manifest change (new entry or new "
              "edition), not a silent swap. Nothing copied.")
        return 1
    shutil.copyfile(source, target)
    if doc["sha256"] is None:
        _pin(manifest, doc, digest)
    print(f"  {doc_id}: stored as {target} ({target.stat().st_size:,} bytes)")
    return 0


def cmd_adopt(manifest: dict, incoming: Path, mapping: dict[str, str]) -> int:
    """Take in files the operator supplied — a phone upload, a Drive folder.

    A file whose sha256 matches a pinned hash is recognised and stored under
    its canonical name, whatever it arrived as. A file named in the mapping
    (``filename=document-id``) is stored as that document and its hash pinned
    if none was. Everything else is reported with name, size and hash, so the
    next mapping can be written from the report instead of from guesswork.
    """
    base = store_dir(manifest)
    base.mkdir(parents=True, exist_ok=True)
    docs = {doc["id"]: doc for doc in manifest["documents"]}
    by_pin = {doc["sha256"]: doc for doc in manifest["documents"] if doc["sha256"]}
    failures = 0
    # Recursive, because a Drive folder arrives as a tree: the operator's
    # subfolders are organisation, not a boundary for recognition.
    for path in sorted(incoming.rglob("*")):
        if not path.is_file():
            continue
        digest = sha256(path)
        doc = by_pin.get(digest)
        if doc is None and path.name in mapping:
            doc_id = mapping[path.name]
            if doc_id not in docs:
                print(f"  {path.name}: mapped to unknown id {doc_id!r}")
                failures += 1
                continue
            doc = docs[doc_id]
            if doc["sha256"] is not None and doc["sha256"] != digest:
                print(f"  {path.name}: contradicts the pinned hash of {doc_id} "
                      "— not stored; a different file needs a manifest change, "
                      "not a silent swap")
                failures += 1
                continue
        if doc is None:
            print(f"  unrecognized: {path.name} "
                  f"({path.stat().st_size:,} bytes, sha256 {digest})")
            continue
        target = base / doc["filename"]
        if not target.is_file():
            shutil.copyfile(path, target)
        if doc["sha256"] is None:
            _pin(manifest, doc, digest)
        print(f"  {doc['id']}: {path.name} -> {target.name} (verified)")
    return 1 if failures else 0


def cmd_path(manifest: dict, ids: list[str]) -> int:
    """Where the named documents are, one path per line, missing ones silent.

    So that a tool that reads a volume can be handed the store's own answer
    instead of a path spelled out again in a workflow.
    """
    docs = {doc["id"]: doc for doc in manifest["documents"]}
    missing = 0
    for doc_id in ids:
        doc = docs.get(doc_id)
        path = locate(manifest, doc) if doc else None
        if path is None:
            print(f"{doc_id}: not in the store", file=sys.stderr)
            missing += 1
            continue
        print(path)
    return 1 if missing else 0


def cmd_verify(manifest: dict) -> int:
    bad = 0
    for doc in manifest["documents"]:
        path = locate(manifest, doc)
        if path is None or doc["sha256"] is None:
            continue
        if sha256(path) != doc["sha256"]:
            print(f"  {doc['id']}: {path} contradicts its pinned hash")
            bad += 1
    print("all present documents match their pinned hashes" if bad == 0
          else f"{bad} document(s) fail verification")
    return 1 if bad else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    fetch_parser = sub.add_parser("fetch")
    fetch_parser.add_argument("ids", nargs="*")
    add_parser = sub.add_parser("add")
    add_parser.add_argument("id")
    add_parser.add_argument("file", type=Path)
    adopt_parser = sub.add_parser("adopt")
    adopt_parser.add_argument("directory", type=Path)
    adopt_parser.add_argument("--as", dest="mapping", action="append", default=[],
                              metavar="FILENAME=ID",
                              help="store this incoming file as this document")
    adopt_parser.add_argument("--map-file", type=Path,
                              help="the same mappings, one per line — a file "
                                   "because uploaded names contain spaces")
    path_parser = sub.add_parser("path")
    path_parser.add_argument("ids", nargs="+")
    sub.add_parser("verify")
    args = parser.parse_args()

    manifest = load_manifest()
    if args.command == "status":
        return cmd_status(manifest)
    if args.command == "fetch":
        return cmd_fetch(manifest, args.ids)
    if args.command == "add":
        return cmd_add(manifest, args.id, args.file)
    if args.command == "adopt":
        pairs = list(args.mapping)
        if args.map_file and args.map_file.is_file():
            pairs += [line.strip() for line
                      in args.map_file.read_text(encoding="utf-8").splitlines()
                      if line.strip()]
        mapping = dict(pair.split("=", 1) for pair in pairs if "=" in pair)
        return cmd_adopt(manifest, args.directory, mapping)
    if args.command == "path":
        return cmd_path(manifest, args.ids)
    return cmd_verify(manifest)


if __name__ == "__main__":
    raise SystemExit(main())
