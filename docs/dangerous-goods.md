# Dangerous goods

EMCargo aims to need one thing from you: the **UN number**. Everything the regulations
derive from that number, it derives for you — and then it checks the result.

> [!IMPORTANT]
> This is a typing aid built on factual reference data. It is not a safety adviser, and
> it does not replace a DGSA. Classification, packaging, marking, labelling and
> documentation remain the shipper's responsibility. The current edition of ADR, RID,
> ADN, the IMDG Code and the IATA DGR is always the authority.

- [What one UN number gives you](#what-one-un-number-gives-you)
- [The checks it runs](#the-checks-it-runs)
- [What blocks an export](#what-blocks-an-export)
- [Per transport mode](#per-transport-mode)
- [UN cards](#un-cards)
- [Rule set editions](#rule-set-editions)
- [How complete is the data?](#how-complete-is-the-data)

## What one UN number gives you

Type `1203`, or search for "gasoline". EMCargo fills in:

| | |
|---|---|
| **Proper shipping name** | English, German or Dutch, depending on what the rulebook for that document allows — see below |
| **Class and division** | Real divisions, not just the class — see the note below |
| **Subsidiary risks** | From the labels column, e.g. `8 (5.1)` for nitric acid |
| **Classification code** | `F1`, `M4`, `C1` — kept separate, never mixed into the description |
| **Packing group** | I, II or III |
| **Packing instruction** | Per rulebook — the ADR instruction is never used for air |
| **Transport category and tunnel code** | For the 1,000-point rule and route restrictions |
| **Kemler number** | Hazard identification number |
| **LQ and EQ limits** | Limited and excepted quantities, explained in plain language — and checked against your quantities, see below |
| **EmS emergency schedules** | Fire and spillage schedule for sea transport, with descriptions |
| **Segregation groups** | SGG1–SGG18, for example "SGG1 (Acids), SGG18 (Alkalis)" |
| **Stowage codes** | SW codes from column 16a, with the wording that explains them |
| **Segregation codes** | SG codes from column 16b, per substance |
| **Marine pollutant** | Column 4 — yes, no, or depends on the substance |
| **Bulk carriage** | Whether the substance may travel in bulk, and under which BK instruction |
| **Air freight rules** | Cargo Aircraft Only, IATA packing instruction, air prohibitions |
| **Carriage prohibition** | Substances ADR does not permit for carriage at all |

Quantities, packaging type and masses come from the packages you already entered. Only
empty fields are filled — your own corrections always survive.

**About the language of the shipping name.** ADR Table A carries an English and a German
name per UN number. Which one EMCargo uses depends on the mode, not on the screen:
ADR 5.4.1.4.1 — and along the same line RID and ADN — wants the transport document in an
official language of the forwarding country, so a German reader preparing a CMR or CIM
gets `BENZIN ODER OTTOKRAFTSTOFF`. IMDG 5.4.1.4.1 wants English, French or Spanish and
IATA DGR 8.1.2.1 wants English, so a sea or air document keeps `GASOLINE` — as does a
multimodal shipment, where English is the only choice that satisfies all three — one
shipment then carries the same goods description on every document, which is what a
forwarder and a customs officer want to see match.

**The interface speaks French; the shipping name does not.** Since v1.44.0 the screen, the
field labels, the compliance findings and the goods database are available in French, and
that is not decoration: ADR, RID and ADN are published by UNECE and OTIF in English, French
and Russian, and the CMR and CIM are French documents by origin. But the ADR Table A export
this application is built on carries only an English and a German name column — there is no
French one — so a French user preparing a road document gets the English proper shipping
name, not `ESSENCE`. That is a gap in the data rather than in the translation, and it is
better to say so than to manufacture a name that no table prescribes. IMDG 5.4.1.4.1 does
accept French, so a sea document could carry it if the names were held.

The language belongs to the document rather than to the shipment, so it is resolved when
the name goes on paper. Draft a German road document and add a sea leg afterwards, and
the IMO form gets `GASOLINE` while the CMR keeps `BENZIN ODER OTTOKRAFTSTOFF`; the export
tells you it did so. Only what EMCargo derived itself is adjusted — wording you typed,
such as a technical name on an N.O.S. entry, is left exactly as it stands.

**Dutch is the one language that cannot stand alone.** ADR 5.4.1.4.1 asks for an official
language of the forwarding country and, where that is not English, French or German, one
of those three *in addition*. So a Dutch road document does not read `ZOUTZUUR` but
`ZOUTZUUR (HYDROCHLORIC ACID)`, and `UN 1203, BENZINE OF MOTORBRANDSTOF (GASOLINE), 3, II,
(D/E)` is the description line a Dutch consignor needs. Those Dutch names are not
translations: they are read out of column (2) of Table A in the official Dutch edition of
ADR 2025 by `scripts/extract_adr_names.py`, cross-checked against the alphabetical index of
the same edition. Where the ADR knows no Dutch name — the IMDG-only additions do not have
one — the English name stays on its own.

**One UN number, several Table A rows.** Paint has three packing groups; aerosols have
twelve rows and *no* packing group at all, told apart only by the classification code of
column (3b) — 5A is non-flammable, 5F flammable, 5T toxic — and each with its own transport
category, tunnel code and labels. EMCargo narrows the rows by whatever you have already
filled in, the classification code first, and where more than one row is still in the
running it says so: how many, what they differ in, and which field settles it. Until
v1.51.0 it warned only when the *packing group* varied, so a shipment of ordinary flammable
spray cans was quietly given the row for the non-flammable ones — transport category 3
instead of 2, which is a points factor three times too low, and tunnel code E instead of D.

**About divisions.** ADR Table A lists gases as class "2" and explosives as class "1",
with the real division hiding in the labels column (2.1 / 2.2 / 2.3) or the
classification code (`1.4S`). EMCargo resolves the actual division, because
segregation and loading compatibility depend on it.

### The description line, written for you

Each rulebook wants the same facts in a different order. EMCargo assembles the
official line per profile and shows it before you export:

| Profile | Example |
|---|---|
| **ADR / RID / ADN** | `UN 1203, BENZINE OF MOTORBRANDSTOF (GASOLINE), 3, II, (D/E), 10 jerrycan, 200 L` |
| **IMDG** | Adds the EmS code and marine pollutant marking |
| **IATA** | Adds the packing instruction and Cargo Aircraft Only |

Plus the total per transport category (ADR 5.4.1.1.1.1), which is mandatory when you use
the 1,000-point exemption and used to be manual work.

## The checks it runs

The compliance panel updates as you type.

**ADR 1.1.3.6 — the 1,000-point rule.** Quantities are multiplied by the factor for
their transport category (×50, ×3, ×1, ×0) and totalled. You get one of four verdicts:
exemption possible, over 1,000 points, category 0 (no exemption), or incomplete — plus
what the exemption does and does not release you from.

**ADR 8.6.3 — the tunnel restriction code of the whole load.** The code from column (15)
has always been printed on the document, as 5.4.1.1.1 (k) requires. Since v1.50.0 it is
also evaluated. 8.6.3.2 assigns the *most restrictive* code of the load to the whole load —
a driver has one route to choose and needs one code, not a list to reconcile — and the
table of 8.6.4 turns that code into the tunnel categories that are barred. `B1000C` and
`C5000D` split on the total net explosive mass per transport unit, so those are totalled
over the load rather than read per line.

8.6.3.3 is the provision that changes the answer rather than adding to it: goods carried
under 1.1.3 are not subject to tunnel restrictions **and must not be counted** when
determining the load's code. A consignment inside the 1.1.3.6 exemption therefore gets no
code at all, and the panel says why. The one exception the article names is the transport
unit carrying the 3.4.13 mark, which is barred from category E tunnels however mild its
goods' own codes are.

Two things the answer does not cover, and both are stated next to it: which tunnels lie on
the route and what category they carry — 1.9.5 puts that with the carrier — and carriage in
tanks or in bulk, which is stricter for five of the twelve codes and which EMCargo,
being a packaged-goods tool, does not model.

**ADR 8.1.4 and 8.1.5 — what has to be aboard.** Equipment was absent from every mode, and
for a reason: EMCargo cannot see a vehicle, so it can never establish that a wheel chock
is in the cab. What it can do is derive the list, and 8.1.5.1 asks for exactly that — the
equipment is chosen *according to the hazard label numbers of the goods loaded*, and the
article points at the transport document to identify them. So since v1.53.0 the panel shows
the checklist: the general equipment of 8.1.5.2, the eye-rinsing liquid where the footnote
does not exempt it (label numbers 1, 1.4, 1.5, 1.6, 2.1, 2.2 and 2.3 are exempt, so a load
of propane cylinders is not asked for one), the escape mask for 2.3 and 6.1, and the shovel,
drain seal and collecting container for solids and liquids with labels 3, 4.1, 4.3, 8 and 9.
The fire extinguishers come with the whole table of 8.1.4.1 rather than one answer, because
they hang on the maximum permissible mass of the transport unit — except inside the 1.1.3.6
exemption, where 8.1.4.2 replaces the table with a single 2 kg extinguisher. It is a
checklist, and the panel says so.

**ADR 7.5.2 — loading together.** Warns on class 1 (other than 1.4S) with other classes,
on mixed compatibility groups within class 1, and on the CV28 separation of foodstuffs
from labels 6.1/6.2 and certain class 9 substances.

Three cells of table 7.5.2.1 are not prohibitions but footnotes, and EMCargo honours
them per pair rather than per consignment — one forbidden combination does not condemn a
permitted one, and one permitted combination does not excuse the rest:

- **(b)** class 1 with life-saving appliances of class 9 (UN 2990, 3072, 3268);
- **(c)** UN 0503 with UN 3268;
- **(d)** blasting explosives *except UN 0083* with ammonium nitrate (UN 1942, 2067),
  ammonium nitrate emulsion, suspension or gel (UN 3375) and the alkali and alkaline
  earth metal nitrates the footnote lists by number.

Footnote (d) comes with a condition that carries real consequences, so the panel and the
document both state it: the aggregate must be treated as blasting explosives of class 1
for placarding, segregation, stowage and the maximum permissible load of 7.5.5.2.1.

**Rail was checked before these permissions were extended to it.** EMCargo answers RID
and ADN mixed loading with ADR's table under a stated basis note, and borrowing another
regime's *prohibitions* is conservative in a way that borrowing its *permissions* is not.
RID 2025, table 7.5.2.1 on page 1101, carries footnotes (a) to (d) in the same words and
with the same UN numbers, so for rail this is RID's own rule and not a road rule on loan.
ADN is a different regime for stowage; there the table remains borrowed and labelled.

**ADN 1.1.3.6.1 — the inland waterway exemption, which is not the road one.** ADN has no
points calculation. It exempts a consignment in packages when the gross mass of everything
together stays under 3,000 kg *and* no class exceeds its own figure — 0 kg, 300 kg or
3,000 kg depending on packing group, class 2 group, or whether a model No. 1 label is
required. Carriage in tanks is never exempt. Pick the ADN profile and you get that
calculation with its own card in the panel, alongside the conditions of 1.1.3.6.2 that
survive the exemption. The two answers can differ: 1,200 litres of a packing group III
liquid loses the ADR exemption at 1,200 points and keeps the ADN one, because 1,200 kg is
well under 3,000.

**ADR/RID 1.1.3.6.3 note (a) — nine substances that count differently.** UN 0081, 0082,
0084, 0241, 0331, 0332, 0482, 1005 and 1017 may be carried up to 50 kg rather than the
20 kg of transport category 1, and they count times 20 instead of times 50. So 50 kg of
chlorine reaches exactly 1,000 and keeps the exemption.

**ADR/IMDG 3.4 and 3.5 — limited and excepted quantities.** Enter the net quantity per
inner packaging and EMCargo compares it against the LQ value of column 7a and the
E code of column 7b, per line. For LQ it also holds the package to the 30 kg gross limit
of 3.4.2 (naming the 20 kg tray limit of 3.4.3); for EQ it checks both the inner and the
outer limit of table 3.5.1.2 and warns when a position exceeds the 1,000-package cap of
3.5.5. Mass is never compared against a volume limit, and a number without a unit is
asked about rather than guessed at. Falling within the limits is reported as exactly
that — the LQ/EQ mark and the packaging requirements remain conditions, and a qualifying
line is never silently removed from the 1,000-point calculation. When LQ packages that
qualify on quantity total more than 8 tonnes gross per transport unit, 3.4.13/3.4.14 is
raised for the large mark of 3.4.15.

Two provisions of chapter 3.5 can only be seen across lines, and both are applied since
v1.50.0. **3.5.1.3**: excepted quantities with different E codes packed together in one
outer packaging are capped by the most restrictive of those codes — 400 g of an E1
substance beside 200 g of an E3 one is over the 300 g cap while each line on its own is
comfortably inside its own code. **3.5.1.4**: the smallest quantities under E1, E2, E4 and
E5 — at most 1 g or 1 ml per inner packaging and 100 g or 100 ml per package — are subject
only to 3.5.2 and 3.5.3, so the mark of 3.5.4 and the 1,000-package cap of 3.5.5 fall away
and those packages no longer count towards the cap. The two failed in opposite directions:
the first let a package through that the text caps, the second refused a load the text
permits.

On rail and inland waterway the same basis note
appears as for the points table; for air, which has its own LQ apparatus in the Y packing
instructions, no claim is made. The net-per-inner field is shown only when column 7a or
the E code offers a limited or excepted route.

**IMDG 7.2.4 — sea segregation.** The full class segregation table, with codes 1 to 4
from "away from" to "separated longitudinally". Subsidiary risks count too, and a
subsidiary class 1 risk is treated as division 1.3 (7.2.3.3), which is stricter than the
primary hazard alone. The table is pinned verbatim in a test so a future edit cannot slip
through unnoticed.

**IMDG 7.2.3.1 — which provision wins.** The class table and the substance's own SG codes
can say different things about the same pair. The Code settles it: *"In case of
conflicting provisions, the provisions of column 16b of the Dangerous Goods List, always
take precedence."* Nitric acid next to sulphur is the plain case — the table says "away
from", but the acid carries SG16, "separated from". EMCargo applies the precedence and
says so in both findings: the 16b provision is marked as governing, the table entry stays
visible with a note explaining that it has been superseded. Nothing is removed, so you can
always see what the table said and why it did not decide.

**IMDG 7.2.5 — segregation groups.** All eighteen groups, with 629 substance entries
across 539 UN numbers. Warns about acids with alkalis, acids with cyanides (hydrogen
cyanide), acids with chlorites or hypochlorites (chlorine dioxide, chlorine gas), acids
with nitrites, acids with azides (explosive hydrazoic acid), acids with metal powders
(hydrogen), and peroxides with acids.

**Columns 16a and 16b, per substance.** The stowage (SW) and segregation (SG) codes for
2,336 UN numbers, read from the UN cards. Nitric acid, for instance, yields
`SG6, SG16, SG17, SG19, SG36, SG49`.

Each is shown with the wording that explains it, because a bare code tells a user
nothing — and that wording now comes from the Code itself rather than from a paraphrase.
Chapters 7.1.5, 7.1.6 and 7.2.8 define **SW1–SW31**, the handling codes **H1–H5** and
**SG1–SG78**, and all of them are on board. SG16 reads *"Stow 'separated from' class
4.1"*, in those words.

Reading the official list also settled two things the card text had blurred. SW22 is not
one rule but three, by aerosol capacity. And SG75 is simply absent from the list, where
SG64, SG66 and SG73 are marked `[Reserved]` — independent confirmation that the SGG1a
marking for strong acids left the Code entirely.

**And they are checked, not just shown.** Load anhydrous ammonia with hydrochloric acid
and you get both sides of it: the ammonia carries SG35 (separated from acids) and the acid
carries SG36 (separated from alkalis).

Of the 70 codes in use:

| | |
|---|---|
| Checked against the rest of the shipment | 49 name a class or a segregation group |
| Checked against a named substance | 8 — sulphur, chlorine, ammonia, bromine, carbon tetrachloride, ammonium and mercury salts, chlorate explosives |
| Raised as a requirement to verify | 7 whose target is ordinary cargo: foodstuffs, oils, odour-absorbing cargo |
| Reported as an exemption | SG72 — the tables of IMDG 7.2.6.3 |
| Shown as text only | 5 |

**IMDG 7.2.6.3 relaxes rather than restricts.** SG72 reads "See tables in 7.2.6.3", which
sounds like an extra requirement; the section actually says no segregation needs to be
applied between substances listed in the same table. Two organic peroxides from table
7.2.6.3.4 may travel together.

EMCargo reports that exemption but **never uses it to remove a warning**. Hiding a
segregation finding is a worse failure than showing one too many, so the finding and the
exemption appear side by side, each naming its section, and the judgement stays with the
shipper.

The five that are only shown are not rules: two modify other provisions, two are
definitions, and one applies only to waste aerosols. Turning those into checks would mean
inventing them.

Exceptions count. SG14 reads "separated from class 1 **except** for division 1.4S", so a
1.4S package alongside does not raise it.

**IMDG 7.2.6.5 — the class 8 exception.** Acids and alkalis of packing group II or III
may travel together in packages up to 30 L or 30 kg, provided they do not react
dangerously and the transport document carries the 5.4.1.5.11.3 statement. When a
segregation finding involves such a pair, the exception is reported next to that pair as
an info note; the warning itself is left standing for the shipper to judge.

**IMDG 7.2.7.1.4 — explosives compatibility.** The full A-to-S compatibility group
matrix. Group S is compatible with everything except L; group L only with its own type;
the special provisions for groups G, L and N are shown as warnings. Includes the
ammonium nitrate exception of 7.2.7.2.1.

**IATA Table 9.3.A — air segregation.** Incompatible packages (class 1 excluding 1.4S
against 2.1/3/4.1/5.1; class 8 against 4.3), subsidiary risks included, plus the lithium
battery rule keeping UN 3090/3480 apart from classes 1, 2.1, 3, 4.1 and 5.1. Division 2.3
(toxic gases), including Table A entries that only state class "2" with a 2.3 label, is
refused for air carriage.

**IATA 5.0.2.11 — the Q value.** Q = Σ n/M, rounded up to one decimal, with a warning
above 1.0. The check runs only when at least one M is entered, so auto-filled n alone
does not mark every air shipment incomplete.

**Class-specific document requirements** are called out: net explosive mass and
compatibility group for class 1 (the NEM also drives the 1.1.3.6 points for class 1),
temperature control for self-reactive substances and organic peroxides (4.1 and 5.2), the
responsible person for class 6.2, and radionuclides, package category, transport index and
criticality safety index for class 7. Sea freight gets the container packing certificate;
air freight the signature in duplicate.

## What blocks an export

Most findings are warnings. Two things actually stop you:

1. **An incomplete classification.** Each profile has its own minimum — UN number,
   proper shipping name and class everywhere; IATA also needs the packing instruction,
   number of packages and quantity.
2. **A carriage prohibition.** Fourteen substances that ADR Table A does not permit for
   carriage (aqua regia UN 1798, symmetrical dichlorodimethyl ether UN 2249, refrigerated
   hydrogen chloride UN 2186 and some n.o.s. entries with incompatible hazards) are
   recognised, shown in red, and refused for export. Carriage is only possible with an
   exemption from the competent authority.

## What certain classes add to the document

Chapter 5.4.1.2 asks for statements no table can supply: table A says which substances
*may* need temperature control, never what the control temperature of this consignment
is. Since v1.151.0 each is a field, asked only in the situation its provision describes —
an ordinary drum of petrol is asked for none of them — and printed in the provision's own
words, in the document's language.

| Field | Provision | Asked when |
|---|---|---|
| Control and emergency temperature | 5.4.1.2.3.1 | the entry's name says TEMPERATURE CONTROLLED |
| End of holding time | 5.4.1.2.2 (d) | a REFRIGERATED LIQUID in a tank |
| Name of the gas | 5.4.1.2.2 (e) | UN 1012, which covers four gases |
| Responsible person and telephone | 5.4.1.2.4 | class 6.2 |
| Firework classification reference | 5.4.1.2.1 (g) | UN 0333 to 0337 |
| Carriage temperature | 5.3.2.2 (sea), 5.3.3 (land) | offered on every mode — it decides the elevated temperature mark, and nothing else in a consignment implies it |

Leave one empty and **nothing** appears on the paper. 5.4.1.2.3.1 prints one sentence
carrying both temperatures, so one without the other is suppressed rather than rendered
as a half-sentence that looks answered.

Which provisions are held, which are guidance only and which are absent — with reasons
for the absences — is audited in
[Document fields audit](document-fields-audit.md).

## Per transport mode

The mode you chose selects the rulebook: **ADR** for road, **RID** for rail, **ADN** for
inland waterway, **IMDG** for sea, **IATA DGR** for air. The description line and the
required fields follow from it.

**The checks do not, entirely, and that is worth knowing.** Sea and air have their own
checks. Road, rail and inland waterway share one set: the 1.1.3.6 points and the 7.5.2
mixed-loading table are computed with the **ADR** tables, because those are the ones
EMCargo holds. RID and ADN have their own versions of both chapters. When you pick rail
or inland waterway the compliance panel says so, in as many words, next to the points
table — an indication is worth having, a false certainty is not.

The tunnel restriction code is ADR-only and is printed only on road documents. It comes
from column 15 of ADR Table A; RID Table A has no such column and the ADN transport
document does not carry one. Up to v1.29.4 it appeared on the CIM and the ADN document
too, which was not a missing check but wrong information the application had added itself.

`docs/dg-coverage.md` sets out, per mode, what is checked and what is not.

For road transport there is no separate ADR document — the CMR and the AVC waybill carry
the 5.4.1.1.1 description themselves. See [Documents](documents.md#the-waybill-doubles-as-the-adr-transport-document).

## UN cards

At the end of the wizard, a shipment with dangerous goods can download the **UN cards**
for the substances it declared — a zip with one reference card per UN number, plus a
README listing what is in it and what is not.

Only the cards for **your** substances are bundled. A load of gasoline and chlorine gets
two cards, not the whole library. If a UN number has more than one card, all of them are
included; deciding which variant applies is not something this app should guess at.

The cards are for your own records. They are not transport documents, they are not
attached to anything EMCargo generates, and they do not replace the current edition of
the regulations.

Since v1.129.0 the cards are **EMCargo's own**: one datasheet per UN number *and*
regime (`UN1203_ADR.pdf`, `UN1203_IMDG.pdf`, …), generated from the same measured
regulatory tables the compliance checks run on, with the official label artwork cut from
the UNECE English ADR 2025 and the V/CV/S provision texts printed verbatim. The set is
published as a GitHub Release by the **Generate UN cards** workflow and imported by an
administrator under **Settings → UN Cards**; it lives on the data volume, not in the
image. On an installation without an imported set, the download option simply does not
appear. See [un-cards.md](un-cards.md) for the whole pipeline.

## Rule set editions

The data on board is not all from the same year, and that should be said plainly rather
than discovered:

| Component | Edition |
|---|---|
| ADR classification (Table A) | ADR 2025 |
| IMDG class segregation table, class 1 matrix, 7.2.6.3 tables, segregation groups | Amendment 40-20 — **confirmed unchanged in 42-24** |
| IMDG Dangerous Goods List (chapter 3.2: columns 16a and 16b, stowage category, special provisions) | **Amendment 42-24** |
| IMDG per-substance data from the UN cards (marine pollutant, bulk) | Amendment 41-22 (2023), with the 42-24 differences applied on top |
| EmS emergency schedules | MSC.1/Circ.1588/Rev.3, plus the schedules 42-24 adds |
| IATA lithium/sodium-ion rules | 2026 guidance |

**IMDG Amendment 42-24 has been mandatory since 1 January 2026.**

Chapter 3.2 — the Dangerous Goods List — is now read from the amendment itself:
`backend/seed/dg/imdg_dgl.json` holds all 2,860 rows, and columns 16a and 16b come from
there rather than from the UN cards. That matters because 7.2.3.1 lets column 16b take
precedence over the segregation table, so it is the one column that must not be partial.

What is left of the older data is the per-substance material the list does not carry —
marine pollutant status and bulk carriage, which come from the 41-22 UN cards. For those
EMCargo carries a *difference layer*: the changes 42-24 makes, laid over the 41-22
data, in `backend/seed/dg/imdg_42_24.json`.

Two things make that workable:

1. **Chapter 7.2 barely moved.** The only change 42-24 makes there is a rewording of
   7.2.6.1. The class segregation table (7.2.4), the exemption tables (7.2.6.3), the
   class 1 compatibility matrix (7.2.7.1.4) and the segregation groups (3.1.4.4) are
   unchanged — so the tables this app computes with are still the current ones. A test
   pins that list.
2. **The rest is per substance,** and that is what the layer holds: the eleven new UN
   numbers (sodium-ion batteries UN 3551/3552, the battery-powered vehicle entries
   UN 3556–3558, disilane, gallium in articles, the fire suppressant dispersing devices,
   the new tetramethylammonium hydroxide entry) with their EmS schedules, the substances
   whose stowage codes or marine pollutant status changed, and the new document
   requirement 5.4.1.5.18 for UN 1361.

What the layer deliberately does **not** do is silently rewrite a classification. UN 3423
becomes class 6.1 with a subsidiary 8 in 42-24 while ADR 2025 still lists it as class 8.
EMCargo keeps computing segregation on the ADR classification and says so in a warning,
because quietly swapping the class would change the outcome with nothing on screen to
explain why.

Every compliance result names the editions it used in its `rule_sets` metadata, including
a list of what the difference layer does not cover — packing and tank instructions, the
full text of the new special provisions, and the amended properties of UN 3090/3091/3480/3481
which the source reports without giving.

## How complete is the data?

| Data | Coverage |
|---|---|
| UN numbers with full ADR classification | 2,336 UN numbers, over 2,928 Table A rows — a substance with several packing groups has a row per group |
| EmS emergency schedules | 2,338 UN numbers — **99.5%** exact, from the official EmS Guide |
| Segregation groups | 629 entries across 539 UN numbers |
| UN packaging codes | All 107 codes of ADR 6.1.2 / 6.5.1.4 / 6.6.2 |
| Stowage and segregation codes per substance | 2,336 UN numbers — 1,242 with SW codes, 840 with SG codes |
| Marine pollutant status | 2,336 UN numbers — 202 confirmed, 38 explicitly not, the rest substance-dependent |
| IMDG class segregation table | Complete, Amendment 40-20 (unchanged in 42-24) |
| Class 1 compatibility matrix | Complete, groups A to S |

Where a value genuinely differs by packing group, EMCargo **shows both options rather
than guessing**. Forty-three UN numbers have a different EmS schedule per packing group —
UN 1826 (nitrating acid mixture) is treated as oxidising in group I and corrosive in
group II — and UN 3166 (vehicles) differs between gas and liquid propulsion.

Where an exact entry does not exist, an indicative class default is shown, clearly marked
as a suggestion, and it is not filled in automatically.

For where all this comes from, see [Data sources](data-sources.md).
