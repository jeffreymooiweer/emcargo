"""Fill official, fillable PDF forms (AcroForm) with EMCargo data.

The templates sit in ``templates/forms/`` as genuine PDF forms published by the
issuing body and are filled in — not rebuilt. Signature, carrier and
operational fields are deliberately left empty.
"""

import os
import re
import tempfile
import textwrap
from pathlib import Path
from typing import Any

from pypdf import PdfReader, PdfWriter
from pypdf.generic import BooleanObject, NameObject

try:
    import fitz
except ImportError:  # pragma: no cover
    fitz = None

from app.core.config import get_settings
from app.core.languages import pick
from app.services.dg.naming import resolve_for_profile
from app.services.dg.autofill import adr_category_totals, description_line

# IATA open format: each of the two choice pairs consists of two /Ch fields. The
# struck-through (non-applicable) field gets the "XXX" option, the applicable
# field the empty option. The template pre-fills these fields, so both are always
# set explicitly so the default value does not leak through.
_IATA_AIRCRAFT_STRIKE = "XXX"
_IATA_AIRCRAFT_BLANK = " " * 11
_IATA_SHIPTYPE_STRIKE = "XXXXXXXXXXX"
_IATA_SHIPTYPE_BLANK = " " * 12

CMR_MAX_ROWS = 16


def templates_forms_dir() -> Path:
    settings = get_settings()
    candidates = [
        settings.data_dir / "templates" / "forms",
        Path(__file__).resolve().parents[3] / ".." / "templates" / "forms",
    ]
    for path in candidates:
        resolved = path.resolve()
        if resolved.exists():
            return resolved
    # Fall back to the repo bundle so development without /data works too.
    return (Path(__file__).resolve().parents[3] / ".." / "templates" / "forms").resolve()


def _party(name: str, address: str, contact: str = "") -> str:
    parts = [p.strip() for p in (name, address, contact) if p and p.strip()]
    return "\n".join(parts)


def _first(*values: Any) -> str:
    for value in values:
        if value not in (None, ""):
            return str(value)
    return ""


def _freight_payment_label(value: str, lang: str) -> str:
    labels = {
        "prepaid": {"nl": "Franco", "en": "Carriage paid", "de": "Frei", "fr": 'Port payé'},
        "collect": {"nl": "Ongefrankeerd", "en": "Carriage forward", "de": "Unfrei", "fr": 'Port dû'},
        "agreement": {"nl": "Volgens overeenkomst", "en": "As per agreement",
                      "de": "Laut Vereinbarung", "fr": 'Selon convention'},
    }
    return pick(labels.get(value), lang, value or "")


#: What one goods row of the CMR template legibly holds. Measured on the
#: rendered form: the row clipped a description around the 64th character, and
#: 5.4.1.1.2 requires the information on a transport document to be legible —
#: a line the box cuts off is not.
CMR_ROW_WIDTH = 60


def _wrap_goods_rows(
    rows: list[tuple[str, str, str]],
) -> list[tuple[str, str, str]]:
    """A description longer than the row continues on the next row.

    The weight and volume stay with the first segment, so the totals columns
    keep one figure per consignment line. Before this, a long description —
    the full 5.4.1.1.1 line of a substance with a long name — was silently
    clipped at the box edge, packing group and tunnel code first.
    """
    wrapped: list[tuple[str, str, str]] = []
    for description, weight, volume in rows:
        parts = textwrap.wrap(description, width=CMR_ROW_WIDTH) or [""]
        wrapped.append((parts[0], weight, volume))
        wrapped.extend((part, "", "") for part in parts[1:])
    return wrapped


def _amount(value: Any) -> str:
    """A number the way it goes on paper: 100 plates, not 100.0.

    The counts and weights arrive as floats from the calculation, and
    ``str()`` printed them with their decimal point — "100.0 ×" on the goods
    row of a waybill. A genuine decimal keeps its digits; the artificial one
    goes."""
    if value in (None, ""):
        return ""
    try:
        return f"{float(value):g}"
    except (TypeError, ValueError):
        return str(value)


def _cmr_goods_rows(
    lines: list[dict[str, Any]],
    dangerous_goods: list[dict[str, Any]] | None = None,
) -> list[tuple[str, str, str]]:
    """Goods lines for boxes 6-12.

    For packages with dangerous goods the official description under ADR
    5.4.1.1.1 takes the place of the free description. That makes the CMR itself
    satisfy the transport document and a separate ADR document unnecessary (ADR
    5.4.1.4.1 prescribes no form).
    """
    dg_by_line: dict[Any, list[str]] = {}
    for entry in dangerous_goods or []:
        for product in entry.get("products") or []:
            if str(product.get("un_number") or "").strip():
                dg_by_line.setdefault(entry.get("line_id"), []).append(
                    description_line(product, "ADR")
                )

    rows: list[tuple[str, str, str]] = []
    for line in lines:
        if not line.get("include", True):
            continue
        qty = line.get("quantity")
        dg_descriptions = dg_by_line.get(line.get("line_id"))
        if dg_descriptions:
            weight = line.get("weight_total_kg")
            volume = line.get("transport_volume_m3")
            for description in dg_descriptions:
                rows.append((description, _amount(weight), _amount(volume)))
                weight = volume = ""  # count the mass only once
            continue
        desc = line.get("output_description") or line.get("description") or ""
        prefix = f"{_amount(qty)} × " if qty not in (None, "") else ""
        rows.append((
            f"{prefix}{desc}".strip(),
            _amount(line.get("weight_total_kg")),
            _amount(line.get("transport_volume_m3")),
        ))
    return rows


def fill_cmr(
    values: dict[str, Any],
    lines: list[dict[str, Any]],
    dangerous_goods: list[dict[str, Any]] | None,
    lang: str,
) -> dict[str, str]:
    fields: dict[str, str] = {}
    fields["VakRood01"] = _party(
        values.get("consignor_name", ""),
        values.get("consignor_address", ""),
        values.get("consignor_contact", ""),
    )
    fields["VakRood02"] = _party(
        values.get("consignee_name", ""),
        values.get("consignee_address", ""),
        values.get("consignee_contact", ""),
    )
    fields["VakRood03"] = _first(values.get("place_of_delivery"), values.get("discharge_point"))
    fields["VakRood04-1"] = _first(values.get("loading_point"), values.get("place_of_receipt"))
    if values.get("loading_date"):
        fields["VeldRood04-2"] = str(values["loading_date"])
    fields["VakRood05"] = _first(values.get("attached_documents"))
    instructions = [_first(values.get("sender_instructions"))]
    if dangerous_goods:
        totals = adr_category_totals(dangerous_goods, lang)
        if totals["statement"]:
            instructions.append(totals["statement"])
    fields["VakRood13"] = "\n".join(x for x in instructions if x)
    fields["VakRood14"] = _freight_payment_label(str(values.get("freight_payment", "")), lang)
    fields["VakRood15"] = _first(values.get("cod_amount"))
    fields["VakRood16"] = _first(values.get("carrier_name"))
    fields["VakRood17"] = _first(values.get("successive_carriers"))
    fields["VakRood19"] = _first(values.get("special_agreements"))
    fields["VakRood21-1"] = _first(values.get("established_place"))
    fields["VakRood21-2"] = _first(values.get("established_date"))

    rows = _wrap_goods_rows(_cmr_goods_rows(lines, dangerous_goods))
    if len(rows) <= CMR_MAX_ROWS:
        for i, (desc, weight, volume) in enumerate(rows, start=1):
            n = f"{i:02d}"
            fields[f"VakRood06Regel{n}Kolom06"] = desc
            fields[f"VakRood06Regel{n}Kolom11"] = weight
            fields[f"VakRood06Regel{n}Kolom12"] = volume
    else:
        # More lines than the form can take: first lines + a reference to an annex.
        for i in range(1, CMR_MAX_ROWS):
            desc, weight, volume = rows[i - 1]
            n = f"{i:02d}"
            fields[f"VakRood06Regel{n}Kolom06"] = desc
            fields[f"VakRood06Regel{n}Kolom11"] = weight
            fields[f"VakRood06Regel{n}Kolom12"] = volume
        total_weight = sum(float(w) for _, w, _ in rows if w)
        total_volume = sum(float(v) for _, _, v in rows if v)
        n = f"{CMR_MAX_ROWS:02d}"
        overflow = pick(
            {
                "nl": "+{count} regels — zie bijgevoegde paklijst",
                "en": "+{count} lines — see attached packing list",
                "de": "+{count} Zeilen — siehe beigefügte Packliste", "fr": '+{count} lignes — voir la liste de colisage jointe'},
            lang,
        )
        fields[f"VakRood06Regel{n}Kolom06"] = overflow.format(
            count=len(rows) - (CMR_MAX_ROWS - 1)
        )
        fields[f"VakRood06Regel{n}Kolom11"] = str(round(total_weight, 2))
        fields[f"VakRood06Regel{n}Kolom12"] = str(round(total_volume, 3))
    return {k: v for k, v in fields.items() if v not in (None, "")}


def _iata_dg_block(dangerous_goods: list[dict[str, Any]],
                   authorization: str = "") -> str:
    """Lines for the 'Nature and Quantity of Dangerous Goods' field, IATA column order.

    The Authorization box of the DGD belongs with this table: that is where the
    reference goes under which the consignment may fly — an approval from the
    competent authority, an exemption, a DGR paragraph. The template EMCargo
    fills in has no separate field for it, so it is put as a line of its own
    below the table. Visible and named is better than omitted: without that
    reference, a consignment that needs one cannot be offered.
    """
    out: list[str] = []
    for entry in dangerous_goods or []:
        for p in entry.get("products", []):
            un = str(p.get("un_number") or "").strip()
            un = un if un.upper().startswith(("UN", "ID")) else (f"UN {un}" if un else "")
            psn = resolve_for_profile(p, "IATA_DGR")[0]
            technical = str(p.get("technical_name") or "").strip()
            if technical:
                psn = f"{psn} ({technical})"
            hazard = str(p.get("class") or "").strip()
            subsidiary = str(p.get("subsidiary_risks") or "").strip()
            if subsidiary:
                hazard = f"{hazard} ({subsidiary})"
            pg = str(p.get("packing_group") or "").strip()
            qty_parts = [
                str(p.get("quantity_packages") or "").strip(),
                str(p.get("type_of_package") or "").strip(),
            ]
            qty = " x ".join(x for x in qty_parts if x)
            per = str(p.get("net_mass_liters_per_package") or "").strip()
            if per:
                qty = f"{qty}, {per}" if qty else per
            # The IATA packing instruction belongs on the air waybill. The
            # packing_instruction field is filled by the automatic derivation
            # with the ADR instruction (P001, IBC02, …) and that is invalid in
            # the air — better empty than wrong, then it stands out at a check.
            pi = str(p.get("iata_packing_instruction") or "").strip()
            if not pi:
                fallback = str(p.get("packing_instruction") or "").strip()
                if fallback and not re.match(r"(?i)^(P|IBC|LP|R)\d", fallback):
                    pi = fallback
            segments = [s for s in [un, psn, hazard, pg, qty, pi] if s]
            if segments:
                out.append("   ".join(segments))
    if authorization:
        out.append(f"Authorization: {authorization}")
    return "\n".join(out)


def fill_iata(values: dict[str, Any], dangerous_goods: list[dict[str, Any]], lang: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    fields["Shipper"] = _party(
        values.get("consignor_name", ""),
        values.get("consignor_address", ""),
        values.get("consignor_contact", ""),
    )
    fields["Consignee"] = _party(
        values.get("consignee_name", ""),
        values.get("consignee_address", ""),
        values.get("consignee_contact", ""),
    )
    if values.get("awb_number"):
        fields["Air Waybill No"] = str(values["awb_number"])
    if values.get("shipment_reference"):
        fields["Shipper Reference"] = str(values["shipment_reference"])
    fields["Departure Airport"] = _first(values.get("loading_point"))
    fields["Destination Airport"] = _first(values.get("discharge_point"))
    handling = [str(values.get("handling_information") or "").strip()]
    emergency = str(values.get("emergency_contact") or "").strip()
    if emergency:
        # Various state and operator variations require a 24-hour emergency
        # number on the declaration; the handling information box is the place
        # for it.
        handling.append(f"24-hour emergency contact: {emergency}")
    fields["Additional Handling Information"] = " / ".join(x for x in handling if x)
    fields["Nature and Quantity of Dangerous Goods"] = _iata_dg_block(
        dangerous_goods, str(values.get("authorization") or "").strip()
    )

    # "Delete non-applicable": strike through the NON-applicable option and set
    # the applicable field explicitly empty (otherwise the template default leaks
    # through).
    aircraft = str(values.get("aircraft_limitation") or "")
    if aircraft == "cargo_only":
        fields["Passenger and Cargo Aircraft"] = _IATA_AIRCRAFT_STRIKE
        fields["Cargo Aircraft Only"] = _IATA_AIRCRAFT_BLANK
    elif aircraft == "passenger_and_cargo":
        fields["Cargo Aircraft Only"] = _IATA_AIRCRAFT_STRIKE
        fields["Passenger and Cargo Aircraft"] = _IATA_AIRCRAFT_BLANK

    ship_type = str(values.get("shipment_type") or "")
    if ship_type == "non_radioactive":
        fields["radioactive ship type"] = _IATA_SHIPTYPE_STRIKE
        fields["non-rad ship type"] = _IATA_SHIPTYPE_BLANK
    elif ship_type == "radioactive":
        fields["non-rad ship type"] = _IATA_SHIPTYPE_STRIKE
        fields["radioactive ship type"] = _IATA_SHIPTYPE_BLANK

    signatory = _first(values.get("signatory_name"))
    if signatory:
        fields["Name-title"] = signatory
    place_date = " / ".join(
        x for x in [_first(values.get("declaration_place")), _first(values.get("declaration_date"))] if x
    )
    if place_date:
        fields["place-date"] = place_date
    return {k: v for k, v in fields.items() if v not in (None, "")}


def _cim_payment_label(value: str, lang: str) -> str:
    labels = {
        "franco": {"nl": "Franco de port", "en": "Carriage paid", "de": "Franco de port", "fr": 'Port payé'},
        "collect": {"nl": "Non franco", "en": "Carriage forward", "de": "Non franco", "fr": 'Port dû'},
        "shared": {"nl": "Volgens afspraak", "en": "As agreed", "de": "Laut Vereinbarung", "fr": 'Comme convenu'},
    }
    return pick(labels.get(value), lang, value or "")


def fill_cim(
    values: dict[str, Any],
    lines: list[dict[str, Any]],
    dangerous_goods: list[dict[str, Any]] | None,
    lang: str,
) -> dict[str, str]:
    fields: dict[str, str] = {}
    # Vak 1: afzender, vak 4: geadresseerde (naam + adres + contact).
    fields["Expéditeur1"] = _party(values.get("consignor_name", ""), values.get("consignor_address", ""))
    fields["Destinataire4"] = _party(values.get("consignee_name", ""), values.get("consignee_address", ""))
    fields["Déclaration expéditeur7"] = _first(values.get("consignor_declarations"))
    fields["Référence Expéditeur8"] = _first(values.get("shipment_reference"))
    fields["Annexes9"] = _first(values.get("attached_documents"))
    fields["Lieu de livraison10"] = _first(values.get("place_of_delivery"), values.get("discharge_point"))
    fields["Conditions commerciales13"] = _first(values.get("commercial_conditions"))
    fields["Numéro accord client14"] = _first(values.get("contract_number"))
    fields["Info destinataire15"] = _first(values.get("info_for_consignee"))
    fields["Prise en charge1-16"] = _first(values.get("loading_point"), values.get("place_of_receipt"))
    if values.get("loading_date"):
        fields["Mois/jour/heure"] = str(values["loading_date"])
    fields["Franco de port20"] = _cim_payment_label(str(values.get("payment_instruction", "")), lang)
    if values.get("declared_value"):
        fields["Déclaration de valeur-26"] = str(values["declared_value"])
    if values.get("cod_amount"):
        fields["Remboursement28"] = str(values["cod_amount"])

    # Box 21: goods description (one large field).
    desc_lines = []
    for line in lines:
        if not line.get("include", True):
            continue
        qty = line.get("quantity")
        prefix = f"{_amount(qty)} × " if qty not in (None, "") else ""
        desc = line.get("output_description") or line.get("description") or ""
        weight = line.get("weight_total_kg")
        suffix = f"  ({_amount(weight)} kg)" if weight not in (None, "") else ""
        desc_lines.append(f"{prefix}{desc}{suffix}".strip())
    fields["Description21"] = "\n".join(desc_lines)

    # Vak 24/25: NHM-code en totale massa (eerste rij).
    if values.get("nhm_code"):
        fields["NHM Code0"] = str(values["nhm_code"])
    total_weight = sum(
        float(l.get("weight_total_kg") or 0) for l in lines if l.get("include", True)
    )
    if total_weight:
        fields["Masse0"] = str(round(total_weight, 2))

    # Box 29: place and date of issue.
    place_date = " ".join(
        x for x in [_first(values.get("established_place")), _first(values.get("established_date"))] if x
    )
    if place_date:
        fields["Lieu et date d'établissement29"] = place_date

    return {k: v for k, v in fields.items() if v not in (None, "")}


# Per document: template-bestand.
PDF_FILLERS: dict[str, str] = {
    "cmr": "cmr.pdf",
    "iata_dgd": "iata_dgd.pdf",
    "cim": "cim.pdf",
}


def build_fields(
    document_key: str,
    values: dict[str, Any],
    lines: list[dict[str, Any]],
    dangerous_goods: list[dict[str, Any]] | None,
    lang: str,
) -> dict[str, str]:
    if document_key == "cmr":
        return fill_cmr(values, lines, dangerous_goods, lang)
    if document_key == "iata_dgd":
        return fill_iata(values, dangerous_goods or [], lang)
    if document_key == "cim":
        return fill_cim(values, lines, dangerous_goods, lang)
    raise ValueError(f"No PDF filler for {document_key}")


def has_pdf_template(document_key: str) -> bool:
    if document_key not in PDF_FILLERS:
        return False
    return (templates_forms_dir() / PDF_FILLERS[document_key]).exists()


# Where the consignor's signature is placed on each form.
# CMR: box 22 (signature and stamp of the consignor) — the left box on all four
# copies. IATA: the "Signature" image field of the open format. The CIM has no
# consignor signature box (box 61 is the consignee's acknowledgement of receipt
# and always stays empty).
_SIGNATURE_RECTS: dict[str, list[tuple[int, tuple[float, float, float, float]]]] = {
    "cmr": [(page, (48.0, 742.0, 200.0, 786.0)) for page in range(4)],
}
_SIGNATURE_WIDGETS: dict[str, str] = {
    "iata_dgd": "Signature image_af_image",
}


def _stamp_signature(doc, document_key: str, signature_png: bytes) -> None:
    spots: list[tuple[int, Any]] = list(_SIGNATURE_RECTS.get(document_key, []))
    widget_name = _SIGNATURE_WIDGETS.get(document_key)
    if widget_name:
        for page_no in range(doc.page_count):
            for widget in doc[page_no].widgets() or []:
                if widget.field_name == widget_name:
                    spots.append((page_no, tuple(widget.rect)))
    for page_no, rect in spots:
        if page_no >= doc.page_count:
            continue
        target = fitz.Rect(rect) + (2, 2, -2, -2)
        doc[page_no].insert_image(target, stream=signature_png, keep_proportion=True)


def _fill_with_pymupdf(
    template_path: Path,
    fields: dict[str, str],
    disclaimer: str,
    document_key: str = "",
    signature_png: bytes | None = None,
) -> Path:
    """Fill AcroForm fields and flatten them so values are visible in all PDF viewers.

    ``widget.update()`` (appearance streams) alone is not enough for Chrome/Edge/
    some Preview viewers: those ignore AcroForm appearances. ``bake()`` puts the
    values permanently into the page content.
    """
    if fitz is None:
        raise RuntimeError("PyMuPDF (pymupdf) is required for PDF form filling")

    doc = fitz.open(template_path)
    try:
        for page in doc:
            for widget in page.widgets() or []:
                name = widget.field_name
                if not name or name not in fields:
                    continue
                widget.field_value = fields[name]
                widget.update()

        if signature_png:
            _stamp_signature(doc, document_key, signature_png)

        # Flattening: visible in the Chrome PDF viewer and the like, not only in
        # Acrobat/MuPDF.
        doc.bake(annots=True, widgets=True)

        doc.set_metadata(
            {
                "producer": "EMCargo",
                "creator": "EMCargo",
                "subject": disclaimer,
            }
        )

        fd, temp_name = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        out_path = Path(temp_name)
        try:
            out_path.chmod(0o600)
        except OSError:
            pass
        doc.save(str(out_path), garbage=3, deflate=True)
        return out_path
    finally:
        doc.close()


def _fill_with_pypdf(template_path: Path, fields: dict[str, str], disclaimer: str) -> Path:
    """Fallback without visible appearances (/V values only)."""
    reader = PdfReader(str(template_path))
    writer = PdfWriter()
    writer.append(reader)

    for page in writer.pages:
        writer.update_page_form_field_values(page, fields, auto_regenerate=False)

    try:
        writer.add_metadata(
            {
                "/Producer": "EMCargo",
                "/Creator": "EMCargo",
                "/Subject": disclaimer,
            }
        )
    except Exception:
        pass

    try:
        writer.set_need_appearances_writer(True)
    except Exception:
        root = writer._root_object
        if "/AcroForm" in root:
            root["/AcroForm"][NameObject("/NeedAppearances")] = BooleanObject(True)

    fd, temp_name = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    out_path = Path(temp_name)
    try:
        out_path.chmod(0o600)
    except OSError:
        pass
    with open(out_path, "wb") as fh:
        writer.write(fh)
    return out_path


def fill_pdf_document(
    document_key: str,
    values: dict[str, Any],
    lines: list[dict[str, Any]],
    dangerous_goods: list[dict[str, Any]] | None,
    lang: str = "nl",
    signature_png: bytes | None = None,
) -> Path:
    if document_key not in PDF_FILLERS:
        raise ValueError(f"No PDF template for {document_key}")
    template_name = PDF_FILLERS[document_key]
    template_path = templates_forms_dir() / template_name
    if not template_path.exists():
        raise FileNotFoundError(f"PDF template not found: {template_path}")

    fields = build_fields(document_key, values, lines, dangerous_goods, lang)

    from app.services.documents.notices import output_notice
    disclaimer = output_notice(lang)

    if fitz is not None:
        return _fill_with_pymupdf(template_path, fields, disclaimer, document_key, signature_png)
    return _fill_with_pypdf(template_path, fields, disclaimer)
