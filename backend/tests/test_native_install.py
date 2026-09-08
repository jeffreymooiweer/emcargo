"""The routes in without Docker: the deploy files hang together, and the
settings screen is told which update route applies.

A shell script that does not parse, a unit that points at a path the script
never makes, an environment example naming a variable the application does
not read, a manifest that does not parse — each is a broken install for
somebody who cannot see this test. So they are checked here, against the
application's own settings, on every run.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
import yaml

from app.core.config import Settings, get_settings
from app.services import updater

ROOT = Path(__file__).resolve().parents[2]
NATIVE = ROOT / "deploy" / "native"
KUBERNETES = ROOT / "deploy" / "kubernetes" / "emcargo.yaml"


def settings_fields() -> set[str]:
    names = {name.upper() for name in Settings.model_fields}
    for field in Settings.model_fields.values():
        alias = field.validation_alias
        if isinstance(alias, str):
            names.add(alias)
        elif hasattr(alias, "choices"):
            names.update(choice for choice in alias.choices if isinstance(choice, str))
    return names


def env_keys(text: str) -> set[str]:
    return {m.group(1) for m in re.finditer(r"^([A-Z][A-Z0-9_]*)=", text, re.M)}


def test_the_scripts_parse():
    for script in ("install.sh", "update.sh"):
        subprocess.run(["bash", "-n", str(NATIVE / script)], check=True)


def test_the_unit_and_the_script_agree_on_the_paths():
    unit = (NATIVE / "cargopilot.service").read_text(encoding="utf-8")
    script = (NATIVE / "install.sh").read_text(encoding="utf-8")
    assert "WorkingDirectory=/opt/cargopilot/current/backend" in unit
    assert "EnvironmentFile=/etc/cargopilot/cargopilot.env" in unit
    assert "ExecStart=/opt/cargopilot/venv/bin/uvicorn app.main:app" in unit
    assert "Environment=INSTALL_METHOD=native" in unit
    assert 'PREFIX="/opt/cargopilot"' in script and 'CONF_DIR="/etc/cargopilot"' in script
    assert 'DATA_DIR="/var/lib/cargopilot"' in script
    assert "ReadWritePaths=/var/lib/cargopilot" in unit
    # The script installs the unit and the env example the bundle carries.
    assert "deploy/native/cargopilot.service" in script
    assert "deploy/native/cargopilot.env.example" in script


def test_the_environment_example_names_only_variables_the_application_reads():
    keys = env_keys((NATIVE / "cargopilot.env.example").read_text(encoding="utf-8"))
    assert keys, "the example is empty"
    assert keys <= settings_fields(), keys - settings_fields()
    assert {"DATA_DIR", "DATABASE_URL", "CARGOPILOT_MODE", "ADMIN_PASSWORD"} <= keys


def test_the_kubernetes_manifests_parse_and_name_real_variables():
    docs = list(yaml.safe_load_all(KUBERNETES.read_text(encoding="utf-8")))
    kinds = [d["kind"] for d in docs]
    assert kinds == ["Namespace", "PersistentVolumeClaim", "Secret", "ConfigMap",
                     "Deployment", "Service", "Ingress"]
    config = next(d for d in docs if d["kind"] == "ConfigMap")["data"]
    secret = next(d for d in docs if d["kind"] == "Secret")["stringData"]
    assert set(config) | set(secret) <= settings_fields()
    assert config["INSTALL_METHOD"] == "kubernetes"
    deployment = next(d for d in docs if d["kind"] == "Deployment")
    # One replica by design: SQLite on one volume.
    assert deployment["spec"]["replicas"] == 1
    assert deployment["spec"]["strategy"]["type"] == "Recreate"


@pytest.mark.parametrize("method", ["native", "kubernetes"])
def test_the_settings_screen_is_told_the_route_that_applies(monkeypatch, method):
    monkeypatch.setenv("INSTALL_METHOD", method)
    monkeypatch.setenv("UPDATE_APPLY_ENABLED", "true")
    get_settings.cache_clear()
    try:
        ability = updater.capability()
    finally:
        get_settings.cache_clear()
    assert ability["available"] is False
    assert ability["install_method"] == method
    assert ability["reason"] == method


def test_an_unknown_install_method_is_docker(monkeypatch):
    monkeypatch.setenv("INSTALL_METHOD", "bare-metal-typo")
    monkeypatch.delenv("UPDATE_APPLY_ENABLED", raising=False)
    get_settings.cache_clear()
    try:
        ability = updater.capability()
    finally:
        get_settings.cache_clear()
    assert ability["install_method"] == "docker"
    assert ability["reason"] == "switch_off"


def test_the_release_workflow_attaches_the_bundle_the_script_downloads():
    workflow = (ROOT / ".github" / "workflows" / "tag-release.yml").read_text(encoding="utf-8")
    script = (NATIVE / "install.sh").read_text(encoding="utf-8")
    assert 'tar -czf "cargopilot-$VERSION-native.tar.gz"' in workflow
    assert "gh release upload" in workflow
    assert "cargopilot-$VERSION-native.tar.gz" in script
