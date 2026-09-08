# What chapter 5.4.1 asks for, and what EMCargo has

*Audit of the transport-document provisions against the fields the application
holds. Read out of the official texts with
`scripts/read_land_regulations.py --quote document_cases`, not from memory.*

## Why this exists

The application was about to be tested with real consignments. A test finds
what is missing one shipment at a time, and each finding costs a round trip —
so this audit went through chapter 5.4.1 as a whole first and asked, per
provision: *is there a field for this, and does it reach the paper?*

Three answers were possible, and all three occur below:

- **held** — a field exists and the provision's words reach the document;
- **guidance only** — the application tells the consignor the provision
  applies, but has nowhere for them to answer it. This is the dangerous
  category: it looks like coverage and is not;
- **absent** — nothing.

The second category is what this audit was for. Being told "state the control
temperature" by a program that then prints a document without it is worse than
silence, because the document looks complete.

## 5.4.1.1 — the description line and its special cases

| Provision | What it asks for | Status |
|---|---|---|
| 5.4.1.1.1 (a)–(k) | UN number, proper shipping name, labels, packing group, tunnel code, packages, quantity | **held** since v1.88.0, all label models included |
| 5.4.1.1.2 | ADN tank vessels, composed from table C | **held** since v1.91.0 |
| 5.4.1.1.3 | Waste: the word before the name | **held** since v1.90.0 |
| 5.4.1.1.4 | Asbestos waste under SP 678: "Carriage under special provision 678", plus two attachments | **absent** — see below |
| 5.4.1.1.5 | Salvage packagings: "SALVAGE PACKAGING" / "SALVAGE PRESSURE RECEPTACLE" | **held** since v1.90.0 |
| 5.4.1.1.6 | Empty uncleaned: "EMPTY, UNCLEANED" or "RESIDUE, LAST CONTAINED"; (f) does not apply | **held** since v1.90.0 |
| 5.4.1.1.18 | Environmentally hazardous | **held** since v1.90.0 |
| 5.4.1.1.19 | UN 3509, the residues' classes | **held** since v1.95.0 |
| 5.4.1.1.20 | Carriage under 2.1.2.8 | **held** since v1.95.0 |
| 5.4.1.1.23 | MOLTEN | **held** since v1.95.0 |

## 5.4.1.2 — what certain classes add

This is where the audit found what it was looking for. Every row below was
**guidance only** before v1.151.0: named in the compliance panel as something
to remember, with no field to answer it and nothing on the document.

| Provision | What it asks for | Before | Now |
|---|---|---|---|
| 5.4.1.2.1 (a) | Class 1: net explosive mass per UN number | held | held |
| 5.4.1.2.1 (a) | Class 1: **total** NEM for the whole document | absent | **absent** — see below |
| 5.4.1.2.1 (b) | Mixed packing: "Goods of UN Nos..." | absent | **absent** |
| 5.4.1.2.1 (e) | P101: "Packaging approved by the competent authority of ..." | absent | **absent** |
| 5.4.1.2.1 (g) | Fireworks UN 0333–0337: classification reference XX/YYZZZZ | guidance only | **field** `firework_classification` |
| 5.4.1.2.2 (a) | Class 2 mixtures in tanks: composition in per cent | guidance only | **absent** |
| 5.4.1.2.2 (b) | "Carriage in accordance with 4.1.6.10" | absent | **absent** |
| 5.4.1.2.2 (d) | Refrigerated liquefied gas: "End of holding time: DD/MM/YYYY" | guidance only | **field** `end_of_holding_time` |
| 5.4.1.2.2 (e) | UN 1012: which of the four gases | absent | **field** `specific_gas_name` |
| 5.4.1.2.3.1 | Temperature control: "Control temperature: ... °C Emergency temperature: ... °C" | guidance only | **fields** `control_temperature`, `emergency_temperature` |
| 5.4.1.2.3.2 | "The label conforming to model No. 1 is not required" | absent | **absent** |
| 5.4.1.2.3.3 | "Carriage in accordance with 2.2.52.1.8" plus attached approval | absent | **absent** |
| 5.4.1.2.3.4 | Samples: "Carriage in accordance with 2.2.52.1.9" | absent | **absent** |
| 5.4.1.2.3.5 | Type G: "Not a self-reactive substance of Class 4.1" | absent | **absent** |
| 5.4.1.2.4 | Class 6.2: name and telephone of a responsible person | guidance only | **field** `responsible_person` |
| 5.4.1.2.5.1 (a)–(j) | Class 7: ten separate items | guidance only | **absent** — see below |

### How the new fields behave

Each is asked **only in the situation its provision describes**, so an ordinary
drum of petrol gains no questions at all. Which situation that is comes from
the Dangerous Goods List rather than from a guess: the entries that require
temperature control say "TEMPERATURE CONTROLLED" in the proper shipping name,
and refrigerated liquefied gases say "REFRIGERATED LIQUID" — the same signal
the label and the packing instruction key off.

Each prints in the provision's own words, in the document's language. And an
unanswered field puts **nothing** on the paper: 5.4.1.2.3.1 prints one sentence
carrying both temperatures, so one without the other is suppressed entirely
rather than rendered as "Control temperature: -10 °C Emergency temperature:
°C", which looks answered.

## What is deliberately still absent, and why

**Class 7 (5.4.1.2.5.1).** Ten items — radionuclides, physical and chemical
form, maximum activity in becquerels, package category, transport index,
fissile-material references, certificate identification marks, per-package
statements, exclusive-use declaration, and the A2 multiple — plus 5.4.1.2.5.2,
a statement of actions required of the carrier. This is not a field or two: it
is a consignment type with its own arithmetic, its own certificates and its own
competent-authority approvals. Half of it would be worse than none, because a
class 7 document that looks complete and is not is exactly the failure this
application exists to prevent. It stays out until it can be done whole.

**The statements that quote an approval** (5.4.1.2.1 (c), (e), 5.4.1.2.3.3):
each asks for a copy of a competent-authority approval to be *attached* to the
transport document, in named languages. The sentence is trivial; the
attachment is the substance, and an application that prints the sentence
without the paper invites a consignment to travel with a claim it cannot
support.

**The total net explosive mass for the document** (5.4.1.2.1 (a), second
indent). Genuinely computable — it is the sum over the lines — and worth doing.
It is absent because it belongs to the document rather than to a line, and the
description-line builder works per substance. Noted here rather than quietly
skipped.

**SP 678 asbestos** (5.4.1.1.4) and the class 2 mixture composition
(5.4.1.2.2 (a)) are both single free-text statements that could be added
cheaply. They are absent because nothing in this project's use has needed them
yet; they are the first candidates if a test turns one up.

---

*Audited against ADR 2025 (ECE/TRANS/352), read on a runner from the official
UNECE PDFs. RID and ADN carry the same provisions under the same numbers where
this document does not say otherwise; IMDG has its own chapter 5.4.1 with a
different numbering, and its additional information (5.4.1.5) is held
separately. This is guidance for development, not a compliance statement; see
[DISCLAIMER.md](../DISCLAIMER.md).*
