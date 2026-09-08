#!/usr/bin/env python3
"""Opt-in visual QA transport for environments with separate preview namespaces.

Only synthetic data is used. A temporary database and a real FastAPI TestClient
serve requests from Vite's development-only review bridge. This script is never
started by the application, Docker image, or native service.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile
import time


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--empty", action="store_true", help="Do not seed shipments")
    args = parser.parse_args()
    queue = args.queue.resolve()
    queue.mkdir(parents=True, exist_ok=True)
    repo = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo / "backend"))
    with tempfile.TemporaryDirectory(prefix="emcargo-visual-review-") as data:
        password = secrets.token_urlsafe(32)
        os.environ.update({
            "APP_ENV": "test", "EMCARGO_HISTORY": "true",
            "DATABASE_URL": f"sqlite:///{data}/review.db", "DATA_DIR": data,
            "CATALOG_AUTO_SYNC": "false", "UPDATE_CHECK_ENABLED": "false",
            "ADMIN_USERNAME": "review", "ADMIN_EMAIL": "review@example.invalid",
            "ADMIN_PASSWORD": password, "APP_SECRET_KEY": secrets.token_urlsafe(48),
            "COOKIE_SECURE": "false",
        })
        from fastapi.testclient import TestClient
        from app.main import create_app

        with TestClient(create_app()) as client:
            response = client.post("/api/auth/login", json={"username": "review", "password": password})
            response.raise_for_status()
            if not args.empty:
                for index, (mode, profile, destination) in enumerate([
                    ("road", "ADR", "Rijnhaven · Testontvanger"),
                    ("sea", "IMDG", "Noordkade · Testontvanger"),
                    ("rail", "RID", "Westpoort · Testontvanger"),
                ], 1):
                    response = client.post("/api/shipments", json={
                        "modality": mode, "language": "nl", "profiles": [profile],
                        "values": {"shipment_reference": f"DEMO-2026-00{index}",
                                   "consignor_name": "EMCargo · Testafzender",
                                   "consignee_name": destination},
                        "lines": [{"description": "Stalen platen", "quantity": 6, "weight_total_kg": 1200}],
                        "documents": [], "snapshot": {},
                    })
                    response.raise_for_status()
            print("Visual review worker ready; temporary synthetic database only.", flush=True)
            completed: set[str] = set()
            while True:
                inputs = list(queue.glob("*.request.json"))
                completed.intersection_update(path.name for path in inputs)
                for path in inputs:
                    if path.name in completed:
                        continue
                    try:
                        request = json.loads(path.read_text())
                    except (FileNotFoundError, json.JSONDecodeError):
                        continue
                    try:
                        result = client.request(request["method"], request["url"],
                            content=base64.b64decode(request.get("body", "")),
                            headers={"content-type": request.get("contentType") or "application/json"})
                        payload = {"status": result.status_code,
                            "headers": {key: value for key, value in result.headers.items()
                                        if key in {"content-type", "content-disposition"}},
                            "body": base64.b64encode(result.content).decode()}
                        print(f'{request["method"]} {request["url"]} {result.status_code}', flush=True)
                    except Exception as exc:
                        payload = {"status": 500, "headers": {"content-type": "application/json"},
                            "body": base64.b64encode(json.dumps({"detail": str(exc)}).encode()).decode()}
                    output = path.with_name(path.name.replace(".request.json", ".response.json"))
                    temporary = output.with_suffix(".tmp")
                    temporary.write_text(json.dumps(payload))
                    temporary.replace(output)
                    completed.add(path.name)
                time.sleep(0.035)


if __name__ == "__main__":
    main()
