#!/usr/bin/env python3
"""Copy a stopped installation's data to the EMCargo layout without overwriting it."""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sqlite3


def migrate(source: Path, database_name: str, target: Path) -> None:
    source = source.resolve(strict=True)
    target = target.resolve()
    database = (source / database_name).resolve(strict=True)
    if database.parent != source or not database.is_file():
        raise ValueError("The database must be a file directly inside the source directory.")
    if target.exists() or source == target or source in target.parents:
        raise ValueError("Choose a new destination outside the source directory.")
    if database.name != "emcargo.db" and (source / "emcargo.db").exists():
        raise ValueError("The source already contains emcargo.db; resolve the ambiguity first.")
    # Refuse symlinks rather than copying files outside the selected data directory.
    if any(path.is_symlink() for path in source.rglob("*")):
        raise ValueError("The source contains symlinks; migrate those explicitly first.")
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as old:
        if old.execute("PRAGMA quick_check").fetchone() != ("ok",):
            raise ValueError("The source database failed its integrity check.")
        ignored = {database.name, database.name + "-wal", database.name + "-shm"}

        def ignore(directory: str, names: list[str]) -> set[str]:
            return ignored.intersection(names) if Path(directory) == source else set()

        shutil.copytree(source, target, ignore=ignore)
        with sqlite3.connect(target / "emcargo.db") as new:
            old.backup(new)
            if new.execute("PRAGMA quick_check").fetchone() != ("ok",):
                raise ValueError("The copied database failed its integrity check.")
    print(f"Copied data to {target}; the source is unchanged.")
    print("Set ownership for the application user before starting the new installation.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--database", required=True, help="Existing database filename")
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--application-stopped", action="store_true", required=True)
    args = parser.parse_args()
    migrate(args.source, args.database, args.target)


if __name__ == "__main__":
    main()
