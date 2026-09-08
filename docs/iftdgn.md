# The IFTDGN notification

*The UN/EDIFACT dangerous goods notification, directory D.16A, written from the same
parts as the structured export.*

## What it is

IFTDGN is the message a party responsible for declaring dangerous goods sends to the
party that checks them — a port authority, a terminal, a carrier's agent — about one
conveyance of one means of transport: what dangerous goods are on it, in what
equipment, from where to where. Port community systems read it; a forwarder that gets
one re-keys nothing. It is specified by UN/CEFACT in the UN/EDIFACT directories; the
edition EMCargo writes is **D.16A, revision 8 of the message (2016-06-08)**, the one
in general use with port community systems.

The export step offers it as **Dangerous goods notification (UN/EDIFACT IFTDGN)** on
every transport mode, beside the JSON export, for a shipment that carries dangerous
goods. It is a text file with the extension `.edi` and the media type
`application/EDIFACT`.

## What is in it

The message is built from the document fields, the goods lines and the dangerous goods
entries — the parts the structured export is built from — and from nothing else. A
field the user left empty is absent from the message.

| Segment | Where it sits | What EMCargo puts there |
|---|---|---|
| `UNB` / `UNZ` | interchange envelope | Character set UNOC (ISO 8859-1); the consignor as sender and the carrier (else the forwarder) as recipient, or the marked placeholders `SENDER` / `RECIPIENT`; the moment of writing as the control reference |
| `UNH` / `UNT` | message header and trailer | `IFTDGN:D:16A:UN`, the segment count |
| `BGM` | 00020 | Document name code `890` (dangerous goods declaration), the shipment reference, message function `9` (original) |
| `DTM` | 00030 | `137` document issue date and time, `CCYYMMDDHHMM` |
| `TDT` | segment group 2 | `20` main carriage; the mode as a UN/ECE Recommendation 19 code (`3` road, `2` rail, `1` maritime, `8` inland water, `4` air); the vessel name, vehicle registration or wagon number as the transport means identification |
| `NAD` | segment group 4 | `CA` the carrier and `FW` the freight forwarder, name and address block |
| `EQD` | segment group 6 | `CN` the container number |
| `CNI` | segment group 7 | Consolidation item `1` and the shipment reference: one message, one consignment |
| `LOC` | segment group 7 | `9` place of loading, `11` place of discharge, as names |
| `NAD` | segment group 10 | `CZ` the consignor, name and address block |
| `GID` | segment group 12 | One goods item per dangerous product: number of packages and the package type as text (7064) |
| `FTX AAA` | segment group 12 | The goods description: the chosen or proper shipping name |
| `DGS` | segment group 14 | The regulation (`ADR`, `RID`, `IMD`, `ICA`; `ZZZ` for ADN, which the D.16A list has no code for), the class and one subsidiary risk, the UN number, the flashpoint in `CEL`, the packing group as danger level `1`/`2`/`3`, the EmS, the hazard identification number with the UN number as the orange placard, up to four labels, and the tunnel restriction code |
| `FTX AAD` | segment group 14 | The technical name — the technical name if given, else the chosen or proper shipping name, else `UN nnnn` |
| `FTX AAC` | segment group 14 | What the codes cannot say: `ADN`, `MARINE POLLUTANT`, `EMPTY UNCLEANED`, `WASTE`, the control temperature, the additional information. No `LIMITED QUANTITY`: the wizard's field holds column 7a of Table A, the limit up to which 3.4 applies, not whether this consignment travels under it |
| `MEA` | segment group 14 | `AAB` the goods item gross weight in `KGM` (gross per package × packages) and `AAF` the net quantity in `KGM` or `LTR` (the ADR total quantity; failing that, the net per package × packages), as far as known |
| `SGP` | segment group 15 | The container the product travels in and its number of packages |

A shipment with two dangerous products becomes two goods items, each with its own
`DGS`: the message allows one dangerous goods class per goods item, and that is how the
wizard holds them too.

A worked example, the shipment the test suite uses:

```
UNA:+.? '
UNB+UNOC:3+Afzender BV+Transport O?'Neill & Sons+260906:0830+20260906083000'
UNH+1+IFTDGN:D:16A:UN'
BGM+890+CP-2026-100+9'
DTM+137:202609060830:203'
TDT+20++3+++++:::12-BXG-3'
NAD+CA+++Transport O?'Neill & Sons'
EQD+CN+MSKU1234565'
CNI+1+CP-2026-100'
LOC+9+:::Rotterdam'
LOC+11+:::Duisburg'
NAD+CZ++Havenweg 1:3011 Rotterdam:Nederland+Afzender BV'
GID+1+4::::vaten'
FTX+AAA+++Benzine'
DGS+ADR+3+1203+-40:CEL+2++++33:1203+3++++D/E'
FTX+AAD+++Benzine'
MEA+AAE+AAB+KGM:880'
MEA+AAE+AAF+KGM:800'
SGP+MSKU1234565+4'
UNT+18+1'
UNZ+1+20260906083000'
```

## What is checked before it leaves

The export refuses, with a sentence in the user's language, a shipment without
dangerous goods (there is nothing to notify), a product without a UN number or a class,
a UN number that is not four digits, a quantity that is not a number greater than zero,
and a product without any mass or quantity — the `MEA` in segment group 14 is mandatory
and EMCargo invents no number to satisfy it.

**How a quantity is read.** The quantity fields are free text, and since v1.190.0 every
reader in EMCargo — the compliance check, the trip check and this message — reads
them through the same rules: `1.250,5 L` and `1,250.5` are both 1250.5, `1.250` is
1250, `12,5` is 12.5, and `1.2.3` is not a number. A negative quantity is not made
positive; it is named as the problem it is. The rules are written out in
`backend/app/services/quantities.py`.

Since 2.1.0 the complete quantity must be one finite number, optionally followed by
a textual unit. Leading decimals such as `.5 L` and `,5 L` mean `0.5 L`; previously
they could be read as `5 L`. Formulas (`10 x 20 L`), ranges (`10-20 L`), scientific
notation (`1e3 L`), prose before a number, space-grouped thousands (`1 250 L`) and
overflowing values are refused. Write the actual total using the separators above,
for example `200 L` or `1250 L`. Imported older values using these unsupported forms
must be corrected before export; the application no longer guesses their meaning.
Quantity text is limited to 256 characters before parsing, keeping malformed
input bounded even when it contains long runs of whitespace.

**The character set.** UNOC is ISO 8859-1. A character outside it — an emoji, a letter
from another script — is replaced by `?` *before* the service characters are released,
so it travels as `??` and reads back as a plain question mark. The v1.189.0 release
replaced it afterwards, which put a bare release character in the segment.

Every message is then parsed back and checked against the segment table — every
mandatory segment and group present, no repeat count exceeded, nothing out of order —
before it is written. A message that fails is not handed out; a notification that is
malformed is worse than one that is missing, because the receiver acts on what it can
parse. The service characters are released wherever a value carries one, so a carrier
named *O'Neill & Sons* survives the trip.

## What is deliberately not in it

- **The consignee.** IFTDGN names, for a consignment, the consignor and either the
  carrier's agent or the freight forwarder. The consignee is not among them and is left
  out rather than squeezed in under a function the message did not mean.
- **Coded package types.** Data element 7065 points at UN/ECE Recommendation 21, which is
  not part of the D.16A set and has not been read; the package type travels as text in
  7064 until it has.
- **Coded locations.** The places of loading and discharge are names, not UN/LOCODEs;
  the wizard does not hold the codes.
- **The sender's and recipient's EDI identifiers.** The envelope names the consignor and
  the carrier as a courtesy and marks the slots it cannot fill. The EDI gateway that
  sends the message owns those identifiers, and the port's own message implementation
  guide says which qualifiers and code lists it expects on top of the standard.
- **Handling instructions, pre- and on-carriage, contacts, seals, stowage cells.** Segments
  the message allows and the wizard has no field for.

## Where the structure comes from, and the licence

The D.16A directory is licensed by the United Nations: it may be used and copied within
an organisation, but not modified and redistributed. It is therefore **not in this
repository**. What the repository holds, in `backend/app/config/iftdgn_d16a.json`, is
the segment table of the IFTDGN message, the elements and the code values EMCargo
uses, with short descriptions in EMCargo's own words — the functional facts any
implementation of the message embeds — together with the checksums of the directory
files they were verified against. The test suite checks that structure against the
directory's own segment table and the code values against its code list whenever the
directory is at hand (`EMCARGO_EDIFACT_D16A` pointing at the unpacked `d16a`
folder), and skips those two checks otherwise. Three code lists the directory only
points at — Recommendation 19 for the mode, 20 for the units, 21 for the package types —
are named as such in the file.

The message conforms to the standard; whether it conforms to a particular port's
implementation guide is a question that guide answers, and the first thing to do against
a real counterparty is to read it.
