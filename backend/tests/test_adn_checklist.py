"""The ADN checklist of 8.6.3, and why it is served rather than composed.

Before a tank vessel is loaded or unloaded, 7.2.4.10 requires the checklist of
8.6.3 to be filled in and signed by the boatmaster and the shore facility. Like
the instructions in writing, the regulation *prints* that checklist: it is a
model, and a model is handed over as the edition sets it, never rebuilt from a
database and never paraphrased.

That made it the second document of its kind, which is the change these tests
guard: a model is addressed by its provision as well as by its regime and
language. 5.4.3 keeps working exactly as it did — the endpoint it has is
untouched — and 8.6.3 is reached the same way through the general one.

What the application does *not* do is fill the checklist in. Every answer on it
is agreed between the vessel and the shore at the moment of loading; a form
EMCargo had already ticked would be a claim about a conversation that has
not happened.
"""
import json
from pathlib import Path

import pytest

from app.services import regulations

REGISTER = Path(__file__).resolve().parents[1] / "seed" / "dg" / "sources.json"


def register() -> dict:
    return json.loads(REGISTER.read_text(encoding="utf-8"))


def test_the_checklist_is_registered_in_every_language():
    """Four languages, all of them ADN. A language nobody has supplied is
    registered as missing — that is what lets the application say so."""
    models = {(d["model_of"]["regime"], d["model_of"]["language"])
              for d in regulations.instruction_documents("8.6.3")}
    assert models == {("adn", language) for language in regulations.LANGUAGES}


def test_the_instructions_are_untouched_by_it():
    """The provision the store had before is still answered exactly as it was,
    with all eight of its models."""
    models = {(d["model_of"]["regime"], d["model_of"]["language"])
              for d in regulations.instruction_documents()}
    assert models == {(regime, language)
                      for regime in regulations.REGIMES
                      for language in regulations.LANGUAGES}
    assert regulations.model_provisions()[0] == "5.4.3"
    assert "8.6.3" in regulations.model_provisions()


@pytest.mark.parametrize("language", ["nl", "en", "de", "fr"])
def test_every_page_range_was_measured(language):
    """A range that was guessed at would put the wrong pages in a boatmaster's
    hand, and nothing downstream would notice. The register carries what
    measured it, and every range is a real span of pages."""
    doc = next(d for d in register()["documents"]
               if d["id"] == f"adn_checklist_{language}")
    cut = doc["cut_from"]
    assert "8.6.3" in cut["measured_with"]
    first, last = cut["pages"]
    assert 0 < first < last
    assert cut["document"] in {d["id"] for d in register()["documents"]}


def test_a_missing_edition_is_reported_and_not_filled_in_from_another():
    """The one thing that must never happen: a language the store cannot
    produce being answered with a neighbouring language's model. Where the
    edition is absent the status says so and names what would produce it."""
    for language in regulations.LANGUAGES:
        status = regulations.instruction_status("adn", language, "8.6.3")
        assert status["provision"] == "8.6.3"
        assert status["language"] == language
        if not status["available"]:
            assert status["needs"]
        else:
            assert regulations.instructions_pdf("adn", language, "8.6.3") is not None


def test_an_unregistered_provision_has_no_model():
    """8.6.4, the degassing checklist, is a model of the same kind and is not
    registered yet. Asking for it must come back empty rather than fall back to
    another provision's model."""
    assert regulations.instruction_documents("8.6.4") == []
    status = regulations.instruction_status("adn", "nl", "8.6.4")
    assert status["available"] is False
    assert status["reason"] == "not_registered"
