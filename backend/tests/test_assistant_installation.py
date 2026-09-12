"""Regressions from the Windows browser review of draft PR #13.

An unsupported host was offered a Linux executable, and any two paths could
unlock the assistant. Exercise real files and archive extraction independently
of inference so an incomplete installation never enables a conversation.
"""
import zipfile

import pytest

from app.services.assistant import runtime
from app.services.assistant.understanding import labelled_facts, quantity_answer


@pytest.mark.parametrize("system,machine,key", [
    ("Linux", "x86_64", "x86_64"), ("Linux", "arm64", "aarch64"),
    ("Windows", "AMD64", "windows-x86_64"),
    ("Darwin", "arm64", None), ("Linux", "riscv64", None),
    ("Windows", "arm64", None),
])
def test_download_matches_the_host_or_is_unavailable(monkeypatch, system, machine, key):
    monkeypatch.setattr(runtime.platform, "system", lambda: system)
    monkeypatch.setattr(runtime.platform, "machine", lambda: machine)
    config = runtime.sources()
    assert runtime._server_pin(config) == (config["server"][key] if key else {})
    if key is None:
        assert runtime.status()["installable"] is False
        assert runtime.start_download() == {"error": "sources_not_pinned"}


@pytest.mark.parametrize("payload", [None, b"", b"GGUF", b"wrong-header"])
def test_missing_empty_truncated_or_wrong_model_cannot_unlock(tmp_path, monkeypatch, payload):
    monkeypatch.setattr(runtime, "assistant_dir", lambda: tmp_path)
    monkeypatch.setattr(runtime, "_server_pin", lambda _: {"sha256": "pin"})
    monkeypatch.setattr(runtime, "sources", lambda: {"model": {"filename": "model.gguf", "size": 12}})
    binary = runtime._server_binary()
    binary.parent.mkdir()
    binary.write_bytes(b"executable")
    model = runtime._model_path()
    if payload is not None:
        model.write_bytes(payload)
    assert runtime.installed() is False
    assert runtime.status()["available"] is False
    model.write_bytes(b"GGUF12345678")
    assert runtime.installed() is True
    binary.write_bytes(b"")
    assert runtime.installed() is False
    binary.unlink()
    binary.mkdir()
    assert runtime.installed() is False


def test_windows_zip_installs_only_runtime_files_inside_bin(tmp_path, monkeypatch):
    def download(_url, _hash, destination, _label):
        with zipfile.ZipFile(destination, "w") as archive:
            archive.writestr("release/llama-server.exe", b"server")
            archive.writestr("../../ggml.dll", b"library")
            archive.writestr("../../unrelated.txt", b"ignored")
    monkeypatch.setattr(runtime, "_fetch_verified", download)
    server = runtime.install_server({"url": "https://example.invalid/runtime.zip", "sha256": "pin"}, tmp_path)
    assert server == tmp_path / "bin" / "llama-server.exe"
    assert server.read_bytes() == b"server"
    assert (server.parent / "ggml.dll").read_bytes() == b"library"
    assert {p.name for p in server.parent.iterdir()} == {"llama-server.exe", "ggml.dll"}
    assert not (tmp_path / "server.zip").exists()


@pytest.mark.parametrize("message", [
    "De vervoerder is Trans Janssen en het ordernummer is 4711.",
    "The carrier is Trans Janssen and the purchase order is 4711.",
    "Der Frachtführer ist Trans Janssen und die Bestellnummer ist 4711.",
    "Le transporteur est Trans Janssen et le numéro de commande est 4711.",
])
def test_joined_labels_never_append_articles_to_company_names(message):
    """A real Qwen-backed browser turn appended a conjunction and article
    to the carrier because the deterministic label reader missed the article.
    The next label owns its article; the company name ends before 'and'."""
    fields, prefix = labelled_facts(message)
    assert fields == {"carrier_name": "Trans Janssen", "purchase_order": "4711"}
    assert prefix == ""


def test_company_conjunctions_are_preserved():
    fields, _ = labelled_facts("Vervoerder: Janssen en Zonen; ordernummer: 4711")
    assert fields["carrier_name"] == "Janssen en Zonen"


@pytest.mark.parametrize("text", ["toch 5 pallets", "actually 5 pallets", "doch 5 Paletten", "finalement 5 palettes"])
def test_explicit_count_correction_accepts_a_single_quantity(text):
    """The summary's quantity editor rejected an unambiguous count
    correction. Accept a correction word while retaining
    the ordinary single-count and matching-unit requirements."""
    assert quantity_answer(text, "pallet") == 5


@pytest.mark.parametrize("text", ["toch 5 of 6 pallets", "toch ongeveer 5 pallets", "toch niet 5 pallets", "toch 5 dozen", "toch 5 pallets 800 kg"])
def test_uncertain_or_mismatched_correction_stays_open(text):
    assert quantity_answer(text, "pallet") is None
