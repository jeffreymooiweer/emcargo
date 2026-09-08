"""What the compliance endpoint is allowed to receive.

The check used to be `list[dict]`: Pydantic did not look at it and the
calculation layer had to convert every value defensively itself. That makes one
kind of mistake invisible, and that is exactly the dangerous one here — a
quantity of -5 L lowers the ADR points total and mirrors an exemption that does
not exist, and a profile called "IDMG" silently produces no sea-transport check
instead of an error.

These models pin those two things down at the edge: an unknown profile or an
unusable quantity gives HTTP 422 before anything is computed. Where the
regulations themselves are concerned the fields stay deliberately wide — the
class of a substance is 1.4S or 4.1 or, before long, something that does not
exist yet, and that is for the regulatory layer to rule on, not the schema.
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_core import PydanticCustomError

from app.core.messages import text as message_text
from app.services.quantities import parse_number


class RegulatoryProfile(str, Enum):
    """The canonical profile names shared by frontend, API and engine."""

    ADR = "ADR"
    RID = "RID"
    ADN = "ADN"
    IMDG = "IMDG"
    IATA_DGR = "IATA_DGR"


# ADR 1.1.3.6 has categories 0 to 4; 0 means "no exemption possible".
TRANSPORT_CATEGORIES = {"0", "1", "2", "3", "4"}
PACKING_GROUPS = {"I", "II", "III"}

#: How a consignment travels. "packages" is what this application has always
#: modelled and stays the default; the other three are the ones whose answers
#: differ, and naming them is what lets a check say so.
CARRIAGE_MODES = {"packages", "tank", "portable_tank", "bulk"}


class DangerousGoodsProduct(BaseModel):
    """One dangerous substance in one position.

    Everything is optional: the wizard sends half-finished input along the way
    and the check should then report "incomplete" rather than fall over. What
    *is* enforced is that a value which has been filled in is usable.
    """

    model_config = ConfigDict(extra="allow")

    un_number: str | None = None
    proper_shipping_name: str | None = None
    hazard_class: str | None = Field(default=None, alias="class")
    subsidiary_risks: str | None = None
    classification_code: str | None = None
    packing_group: str | None = None
    segregation_group: str | None = None
    transport_category: str | None = None
    cargo_aircraft_only: bool | None = None
    # How the goods travel. Everything in this application was written for
    # packages and said so nowhere; a tank load used to get the packages answer
    # with nothing to mark it as the wrong one. Absent means packages, which is
    # what every consignment drawn up before v1.66.0 was.
    carriage_mode: str | None = None
    # The code on the tank that is actually standing there — column (12) says
    # which code the substance requires, not whether this tank may carry it.
    # ADR 4.3.3.1.2 and 4.3.4.1.2 answer that, and neither can be asked without
    # this field.
    tank_code: str | None = None

    # Quantities arrive as text ("5 kg", "12,5 L"); the engine peels the number
    # out. Only what cannot possibly be right is refused here.
    adr_total_quantity: str | float | int | None = None
    q_net_quantity: str | float | int | None = None
    q_max_net_quantity: str | float | int | None = None
    # Net per inner packaging, for the LQ/EQ check of 3.4 and 3.5.
    net_per_inner_packaging: str | float | int | None = None
    # Net explosive mass (class 1), for the 1.1.3.6 points and 5.4.1.2.1.
    net_explosive_mass: str | float | int | None = None

    # The special cases of 5.4.1.1.3, 5.4.1.1.5 and 5.4.1.1.6: waste, salvage
    # packagings and empty uncleaned means of containment each change what the
    # description line must say, and none of them can be derived — whether the
    # goods are waste is a fact about the consignment, not about the UN number.
    # The wizard sends these as select values ("" or "yes"), older callers may
    # send booleans; both spell truthiness the way the builder reads it.
    is_waste: str | bool | None = None
    empty_uncleaned: str | bool | None = None
    salvage_packaging: str | None = None
    # ADN 7.1.5.0.2: the consignor's statement that the goods travel
    # exclusively in containers — the reduction's own condition.
    containers_only: str | bool | None = None
    # 5.4.1.1.23 (molten), 5.4.1.1.19 (UN 3509 residues), 5.4.1.1.20 (2.1.2.8).
    molten: str | bool | None = None
    residue_classes: str | None = None
    classified_2_1_2_8: str | bool | None = None
    # --- 5.4.1.2, what certain classes add to the transport document ---------
    #
    # Every one of these is a *statement the consignor owes the carrier* that
    # cannot be derived from the UN number: table A says which substances may
    # need temperature control, not what the control temperature of this
    # consignment is. Until now they were named in the guidance panel as
    # things to remember, which is not the same as a field that reaches the
    # paper. Each is asked only in the situation its provision describes.
    #
    # 5.4.1.2.3.1, self-reactive substances and organic peroxides under
    # temperature control: "Control temperature: ... °C Emergency temperature:
    # ... °C", both or neither.
    control_temperature: str | float | int | None = None
    emergency_temperature: str | float | int | None = None
    # 5.4.1.2.2 (d), refrigerated liquefied gases in tanks: the date the actual
    # holding time ends. The provision prints its own format.
    end_of_holding_time: str | None = None
    # 5.4.1.2.2 (e), UN 1012 only: which of the butylenes is carried, in
    # brackets after the proper shipping name (special provision 398).
    specific_gas_name: str | None = None
    # 5.4.1.2.4, class 6.2: the name and telephone number of a responsible
    # person, beside the consignee's own details.
    responsible_person: str | None = None
    # 5.4.1.2.1 (g), fireworks of UN 0333 to 0337: the classification
    # reference in the form XX/YYZZZZ that the competent authority issued.
    firework_classification: str | None = None
    # The temperature the goods are offered at, in degrees Celsius. It decides
    # the elevated temperature mark — IMDG 5.3.2.2.1 at 100 °C liquid or 240 °C
    # solid, ADR/ADN/RID 5.3.3 on the same thresholds — and nothing else in the
    # consignment implies it: MOLTEN says the substance travels liquid, not how
    # hot, and a substance that is not molten can still be loaded hot. Absent
    # means unknown, which the checks report as unassessed rather than as "no
    # mark required": a bare triangle missing from a tank is not a detail.
    carriage_temperature: str | float | int | None = None
    # 3.1.2.2: the most applicable of several proper shipping names, chosen by
    # the consignor — in the document language and, where a Dutch document
    # pairs the names, in English beside it.
    chosen_name: str | None = None
    chosen_name_en: str | None = None

    @field_validator("salvage_packaging")
    @classmethod
    def _known_salvage(cls, value: str | None) -> str | None:
        """5.4.1.1.5 knows two words, and the wrong key must not become the
        packaging word by silent fallback."""
        if value is None or not str(value).strip():
            return None
        cleaned = str(value).strip().lower()
        if cleaned not in {"packaging", "pressure_receptacle"}:
            raise ValueError(
                f"onbekende bergingsverpakking {value!r}; verwacht "
                "packaging of pressure_receptacle")
        return cleaned

    @field_validator("carriage_mode")
    @classmethod
    def _known_carriage_mode(cls, value: str | None) -> str | None:
        """An unknown mode must not silently fall back to packages.

        That is the same failure this field exists to end: a tank consignment
        answered as if it were packages. A typo here is refused at the edge
        rather than rounded to the answer that looks normal.
        """
        if value is None or not str(value).strip():
            return None
        cleaned = str(value).strip().lower()
        if cleaned not in CARRIAGE_MODES:
            raise ValueError(
                f"onbekende vervoerswijze {value!r}; verwacht "
                + ", ".join(sorted(CARRIAGE_MODES)))
        return cleaned

    @field_validator("packing_group")
    @classmethod
    def _known_packing_group(cls, value: str | None) -> str | None:
        if value is None or not str(value).strip():
            return value
        cleaned = str(value).strip().upper()
        if cleaned not in PACKING_GROUPS:
            raise ValueError(f"onbekende verpakkingsgroep {value!r}; verwacht I, II of III")
        return cleaned

    @field_validator("transport_category")
    @classmethod
    def _known_transport_category(cls, value: str | None) -> str | None:
        if value is None or not str(value).strip():
            return value
        cleaned = str(value).strip()
        if cleaned not in TRANSPORT_CATEGORIES:
            raise ValueError(
                f"onbekende vervoerscategorie {value!r}; ADR 1.1.3.6 kent 0 t/m 4"
            )
        return cleaned

    @field_validator(
        "adr_total_quantity", "q_net_quantity", "q_max_net_quantity",
        "net_per_inner_packaging", "net_explosive_mass",
    )
    @classmethod
    def _usable_quantity(cls, value: Any) -> Any:
        """A quantity that has been filled in must be positive.

        Empty is allowed: the field simply is not filled in yet and the check
        reports that itself. Zero or negative is not — that would lower the
        points total or make a Q component disappear without anybody noticing.
        """
        if value is None or not str(value).strip():
            return value
        number = parse_number(value)
        # PydanticCustomError puts the code in the `type` field of the 422
        # body and the parameters in `ctx`, which is exactly what the interface
        # needs to translate it. A plain ValueError would leave the message as
        # the only thing to go on — and that message can only be in one language.
        if number is None:
            raise PydanticCustomError(
                "dg.quantity_not_a_number",
                message_text("dg.quantity_not_a_number", value=repr(value)),
                {"value": str(value)},
            )
        if number <= 0:
            raise PydanticCustomError(
                "dg.quantity_not_positive",
                message_text("dg.quantity_not_positive", value=repr(value)),
                {"value": str(value)},
            )
        return value


class ShipmentPosition(BaseModel):
    """A vehicle, container or line, with the substances on it."""

    model_config = ConfigDict(extra="allow")

    vehicle: str | None = None
    line_id: str | None = None
    products: list[DangerousGoodsProduct] = Field(default_factory=list)

    @field_validator("line_id", mode="before")
    @classmethod
    def _line_id_as_text(cls, value: Any) -> Any:
        """The wizard numbers its lines and sends line_id as a number.

        Pydantic v2 does not turn an int into a str, so 'line_id: 1' gave a 422
        and with it *every* live check from the wizard failed — the panel showed
        a validation error instead of a result.
        """
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return str(int(value)) if float(value).is_integer() else str(value)
        return value


class ComplianceRequest(BaseModel):
    entries: list[ShipmentPosition] = Field(default_factory=list)
    profiles: list[RegulatoryProfile] = Field(default_factory=list)
    language: str = "nl"

    @field_validator("profiles", mode="before")
    @classmethod
    def _normalise_profile_aliases(cls, value: Any) -> Any:
        """Accept the old name IATA for now, but work canonically internally.

        The wizard and the engine already use `IATA_DGR`. The API still used
        `IATA`, which gave the real frontend payload a 422 while a client that
        did send `IATA` activated no air-freight check at all. The alias exists
        for backwards compatibility only; the response and the engine always see
        `IATA_DGR`.
        """
        if value is None:
            return []
        if not isinstance(value, list):
            return value

        normalised: list[Any] = []
        for profile in value:
            if isinstance(profile, RegulatoryProfile):
                normalised.append(profile.value)
                continue
            name = str(profile).strip().upper()
            normalised.append("IATA_DGR" if name == "IATA" else name)
        return normalised

    def as_dicts(self) -> list[dict[str, Any]]:
        """The positions as the engine reads them.

        `by_alias` keeps "class" under its own name — in Python that cannot be a
        field name, but the whole engine and the frontend know it that way.
        """
        return [
            entry.model_dump(by_alias=True, exclude_none=True) for entry in self.entries
        ]

    def profile_names(self) -> list[str]:
        return [profile.value for profile in self.profiles]
