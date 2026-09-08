"""Whose name is on the paper.

Every document EMCargo draws itself carries the installation's brand —
name and logo — on every page, and EMCargo's own where nothing was set.
The official forms are somebody else's paper and are left alone.
"""
from __future__ import annotations

import io

import fitz
import pytest
from PIL import Image

from app.services.documents import brand
from app.services.documents.equipment_sheet import render_equipment_sheet
from app.services.documents.onboard_pack import render_onboard_documents
from app.services.documents.pdf_render import render_document_pdf
from app.services.documents.registry import get_document
from tests.test_export_bundle import CONSIGNMENT, DG


def _png(colour=(200, 30, 30)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (120, 40), colour).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def _no_brand_left_behind():
    yield
    brand.set_current(None)


def pages_of(path):
    with fitz.open(path) as pdf:
        return [(page.get_text(), len(page.get_images())) for page in pdf]


def test_the_default_paper_is_cargopilots(tmp_path):
    brand.set_current(None)
    path = render_equipment_sheet(CONSIGNMENT, [], DG, language="en")
    text, images = pages_of(path)[0]
    assert "EMCargo" in text
    assert "Drawn up with EMCargo on" in text
    assert images >= 1, "the default logo is drawn"
    assert "Page 1" in text


def test_an_installations_brand_is_on_every_page_of_every_document(tmp_path):
    brand.set_current(brand.Brand(name="Mooiweer Logistics", logo=_png(), own=True))
    rendered = [
        render_equipment_sheet(CONSIGNMENT, [], DG, language="nl"),
        render_onboard_documents(CONSIGNMENT, [], DG, language="de", regime="ADR"),
        render_document_pdf(get_document("packing_list"), CONSIGNMENT,
                            [{"description": "Vaten", "quantity": 4, "unit": "pcs",
                              "weight_total_kg": 800.0}], DG, language="fr"),
    ]
    for path in rendered:
        pages = pages_of(path)
        assert pages, path
        for text, images in pages:
            assert "Mooiweer Logistics" in text, path
            assert images >= 1, path
    # The generated-with line names the brand, in each language.
    assert "Opgesteld met Mooiweer Logistics op" in pages_of(rendered[0])[0][0]
    assert "Généré avec Mooiweer Logistics le" in pages_of(rendered[2])[0][0]
    # The disclaimer keeps naming the software: the licence is EMCargo's.
    assert "EMCargo" in pages_of(rendered[2])[-1][0]


def test_resolving_reads_the_instance_setting_and_the_uploaded_logo(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from app.services import branding, settings_store

    monkeypatch.setattr(settings_store, "instance_settings",
                        lambda db: SimpleNamespace(brand_name="  Havenbedrijf  "))
    monkeypatch.setattr(branding, "logo_image", lambda: (_png((0, 0, 255)), "png"))
    resolved = brand.resolve(db=object())
    assert resolved.name == "Havenbedrijf" and resolved.own and resolved.logo_size() == (120, 40)

    # A name without a logo keeps EMCargo's logo beside the name; nothing
    # set at all is the default, and says so.
    monkeypatch.setattr(branding, "logo_image", lambda: None)
    named = brand.resolve(db=object())
    assert named.name == "Havenbedrijf" and named.own and named.logo
    monkeypatch.setattr(settings_store, "instance_settings", lambda db: SimpleNamespace(brand_name=""))
    assert not brand.resolve(db=object()).own
    assert brand.resolve(None).name == "EMCargo"


def test_a_logo_that_is_not_an_image_does_not_break_the_document():
    brand.set_current(brand.Brand(name="Broken Logo BV", logo=b"<svg/>", own=True))
    path = render_equipment_sheet(CONSIGNMENT, [], DG, language="en")
    text, _images = pages_of(path)[0]
    assert "Broken Logo BV" in text
