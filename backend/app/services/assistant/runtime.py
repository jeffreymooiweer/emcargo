"""The local model runtime: llama.cpp's server, managed as a child process.

Nothing of this ships in the image. When an admin enables the assistant, the
server binary for this machine's architecture and the GGUF model are
downloaded once into ``/data/assistant`` — each verified against the SHA-256
pinned in ``assistant_runtime.json``, the way the document store pins its
sources. A pin of ``null`` means nobody has hashed that artifact yet, and the
download refuses to run rather than trust the network.

The model's only job is translation (see the orchestrator): every call is
constrained to a JSON schema by llama.cpp's grammar support, so output that
is not the expected structure cannot exist. The assistant requires an installed
local model. Exact readers avoid inference for simple answers once installed;
ordinary manual shipment entry is independent of the model.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import shutil
import socket
import subprocess
import tarfile
import threading
import time
import zipfile
from pathlib import Path
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_CONFIG_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "assistant_runtime.json"
)

_lock = threading.Lock()
_process: subprocess.Popen | None = None
_port: int | None = None
_download: dict[str, Any] = {"state": "idle", "detail": ""}


def sources() -> dict[str, Any]:
    try:
        return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):  # pragma: no cover - config missing
        return {}


def _arch() -> str:
    machine = platform.machine().lower()
    if machine in ("aarch64", "arm64"):
        return "aarch64"
    return "x86_64" if machine in ("x86_64", "amd64") else machine


def _server_pin(config: dict[str, Any]) -> dict[str, Any]:
    system = platform.system()
    key = _arch() if system == "Linux" else f"{system.lower()}-{_arch()}"
    return (config.get("server") or {}).get(key) or {}


def assistant_dir() -> Path:
    return Path(get_settings().data_dir) / "assistant"


def _server_binary() -> Path:
    return assistant_dir() / "bin" / ("llama-server.exe" if platform.system() == "Windows" else "llama-server")


def _model_path() -> Path:
    filename = (sources().get("model") or {}).get("filename") or "model.gguf"
    return assistant_dir() / filename


def _repair_library_links(directory: Path) -> None:
    """Restore the SONAME links of the pinned, flattened runtime archive.

    Tar symbolic links were previously discarded while their versioned
    libraries were extracted. The binary then exited before serving a single
    request. Repair older installations too; never link outside this folder
    or choose between conflicting versions.
    """
    aliases: dict[str, list[Path]] = {}
    for library in directory.glob("*.so.*"):
        if library.is_symlink() or not library.is_file():
            continue
        stem, version = library.name.split(".so.", 1)
        if not version or not all(part.isdigit() for part in version.split(".")):
            continue
        for name in (f"{stem}.so", f"{stem}.so.{version.split('.')[0]}"):
            if name != library.name:
                aliases.setdefault(name, []).append(library)
    for name, targets in aliases.items():
        alias = directory / name
        if len(targets) == 1 and not alias.exists() and not alias.is_symlink():
            try:
                alias.symlink_to(targets[0].name)
            except OSError as exc:
                logger.warning("Assistant library link unavailable: %s", exc)


def installed() -> bool:
    # Partial files and directories must never unlock the assistant. Downloads
    # are hash-verified before promotion; size/header checks also detect a
    # truncated or replaced model without hashing 1.8 GB on every request.
    if not _server_pin(sources()):
        return False
    try:
        binary, model = _server_binary(), _model_path()
        expected_size = (sources().get("model") or {}).get("size")
        if not binary.is_file() or binary.stat().st_size == 0 or not model.is_file():
            return False
        if not expected_size or model.stat().st_size != expected_size:
            return False
        with model.open("rb") as handle:
            return handle.read(4) == b"GGUF"
    except OSError:
        return False


def status() -> dict[str, Any]:
    config = sources()
    server_pin = _server_pin(config)
    is_installed = installed()
    return {
        "available": is_installed,
        "mode": "model" if is_installed else "unavailable",
        "model": (config.get("model") or {}).get("name") if is_installed else None,
        "installed": is_installed,
        "installable": bool(server_pin.get("sha256")
                            and (config.get("model") or {}).get("sha256")),
        "architecture": _arch(),
        "download": dict(_download),
        "running": _process is not None and _process.poll() is None,
    }


# --- download --------------------------------------------------------------

def _fetch_verified(url: str, sha256: str, destination: Path, label: str) -> None:
    """Stream a pinned artifact to disk and refuse it unless the digest
    matches. A wrong hash removes the file: half-trusted bytes are worse
    than absent bytes."""
    _download.update({"state": "downloading", "detail": label})
    digest = hashlib.sha256()
    temp = destination.with_suffix(destination.suffix + ".part")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(follow_redirects=True, timeout=60.0) as client:
        with client.stream("GET", url) as response:
            response.raise_for_status()
            with temp.open("wb") as handle:
                for chunk in response.iter_bytes(1024 * 512):
                    handle.write(chunk)
                    digest.update(chunk)
    found = digest.hexdigest()
    if found != sha256:
        temp.unlink(missing_ok=True)
        raise ValueError(
            f"{label}: sha256 mismatch (expected {sha256[:16]}…, got {found[:16]}…)")
    temp.replace(destination)


def install_server(server_pin: dict[str, Any], base: Path) -> Path:
    """Install the verified server independently of the large model weights."""
    windows_archive = server_pin["url"].endswith(".zip")
    archive = base / ("server.zip" if windows_archive else "server.tar.gz")
    _fetch_verified(server_pin["url"], server_pin["sha256"], archive, "server")
    _download.update({"state": "downloading", "detail": "unpack"})
    bin_dir = base / "bin"
    if bin_dir.exists():
        shutil.rmtree(bin_dir)
    bin_dir.mkdir(parents=True)
    if windows_archive:
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                name = Path(member.filename).name
                if member.is_dir() or not (name == "llama-server.exe" or name.lower().endswith(".dll")):
                    continue
                with bundle.open(member) as source, (bin_dir / name).open("wb") as target:
                    shutil.copyfileobj(source, target)
    else:
        _unpack_linux_server(archive, bin_dir)
    archive.unlink(missing_ok=True)
    _repair_library_links(bin_dir)
    server = bin_dir / ("llama-server.exe" if windows_archive else "llama-server")
    if not server.is_file():
        raise ValueError("server: archive held no llama-server binary")
    server.chmod(0o755)
    return server


def _unpack_linux_server(archive: Path, bin_dir: Path) -> None:
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle.getmembers():
            name = Path(member.name).name
            if not member.isfile() or not (
                    name == "llama-server" or name.endswith(".so") or ".so." in name):
                continue
            source = bundle.extractfile(member)
            if source is None:  # pragma: no cover - directory entries
                continue
            with source, (bin_dir / name).open("wb") as target:
                shutil.copyfileobj(source, target)


def _install(config: dict[str, Any]) -> None:
    server_pin = _server_pin(config)
    model_pin = config.get("model") or {}
    install_server(server_pin, assistant_dir())

    _fetch_verified(model_pin["url"], model_pin["sha256"], _model_path(), "model")
    _download.update({"state": "done", "detail": ""})


def start_download() -> dict[str, Any]:
    """Fetch binary and model in a background thread; progress in status()."""
    config = sources()
    server_pin = _server_pin(config)
    model_pin = config.get("model") or {}
    if not server_pin.get("sha256") or not model_pin.get("sha256"):
        return {"error": "sources_not_pinned"}
    if _download.get("state") == "downloading":
        return {"error": "already_downloading"}

    def run() -> None:
        try:
            _install(config)
        except Exception as exc:  # noqa: BLE001 - reported in status, never raised
            logger.warning("Assistant install failed: %s", exc)
            _download.update({"state": "error", "detail": str(exc)})

    _download.update({"state": "downloading", "detail": "start"})
    threading.Thread(target=run, daemon=True).start()
    return {"started": True}


def remove() -> dict[str, Any]:
    stop()
    if assistant_dir().exists():
        shutil.rmtree(assistant_dir())
    _download.update({"state": "idle", "detail": ""})
    return {"removed": True}


# --- the server process ----------------------------------------------------

def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _base_url() -> str:
    return f"http://127.0.0.1:{_port}"


def ensure_server(timeout: float = 15.0) -> bool:
    """Start llama-server once and wait for its health endpoint."""
    global _process, _port
    if not installed():
        return False
    with _lock:
        if _process is not None and _process.poll() is None:
            return True
        _port = _free_port()
        binary = _server_binary()
        _repair_library_links(binary.parent)
        # --reasoning-budget 0 turns the model's thinking mode off. Measured
        # with it on (the Qwen3 default): 31-36 s per turn on 4 vCPUs, most of
        # it spent thinking about a one-word answer — and the schema already
        # does the disciplining that thinking is meant to buy.
        _process = subprocess.Popen(
            [str(binary), "-m", str(_model_path()), "--host", "127.0.0.1",
             "--port", str(_port), "-c", "4096", "--no-webui",
             "--reasoning-budget", "0"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env={**os.environ, "LD_LIBRARY_PATH": str(binary.parent)},
            creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0,
        )
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _process.poll() is not None:
            return False
        try:
            response = httpx.get(f"{_base_url()}/health", timeout=2.0)
            if response.status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    return False


def stop() -> None:
    global _process
    with _lock:
        if _process is not None and _process.poll() is None:
            _process.terminate()
            try:
                _process.wait(timeout=10)
            except subprocess.TimeoutExpired:  # pragma: no cover - stubborn child
                _process.kill()
        _process = None


# --- constrained extraction ------------------------------------------------

def extract_json(
    system: str, user: str, schema: dict[str, Any], timeout: float = 25.0,
    *, max_tokens: int = 768,
) -> dict[str, Any] | None:
    """One schema-constrained completion; None on any failure.

    The grammar makes output outside the schema impossible; a runtime
    failure makes the caller fall back to the deterministic route. Either
    way the orchestrator's rules hold.
    """
    try:
        if not ensure_server():
            return None
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("Assistant runtime unavailable: %s", exc)
        return None
    payload = {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.0,
        "max_tokens": max_tokens,
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "extraction", "schema": schema},
        },
    }
    try:
        response = httpx.post(
            f"{_base_url()}/v1/chat/completions", json=payload, timeout=timeout)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        result = json.loads(content)
        return result if isinstance(result, dict) else None
    except (httpx.HTTPError, KeyError, IndexError, ValueError, TypeError) as exc:
        logger.warning("Assistant extraction failed: %s", exc)
        return None
