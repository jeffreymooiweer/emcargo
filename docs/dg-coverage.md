# Dangerous goods: what EMCargo covers, per mode

An assessment of the dangerous goods functionality against what the five transport
regimes ask of a consignor, written to answer one question honestly: **where would someone
relying on this application be caught out?**

- [How to read this, and what it is not](#how-to-read-this-and-what-it-is-not)
- [The three questions a consignor has to answer](#the-three-questions-a-consignor-has-to-answer)
- [What is held, per substance](#what-is-held-per-substance)
- [Road — ADR](#road--adr)
- [Rail — RID](#rail--rid)
- [Inland waterway — ADN](#inland-waterway--adn)
- [Sea — IMDG](#sea--imdg)
- [Air — IATA DGR](#air--iata-dgr)
- [Gaps ranked by what they cost](#gaps-ranked-by-what-they-cost)
- [What should and should not be built](#what-should-and-should-not-be-built)

## How to read this, and what it is not

Two columns run through this document. They do not have the same standing and it would be
dishonest to present them as if they did.

**What EMCargo does** is established from the code and the data in this repository.
Every claim in that column was read out of `backend/app/services/dg/`,
`backend/app/config/` or `backend/seed/dg/` while writing this, not remembered.

**What the regime requires** now splits in two, and the split matters more than anything
else in this document.

**For road, rail, inland waterway and sea it has been read.** Earlier versions of this
assessment said the regulatory texts were out of reach. That was wrong, and the error was
costly enough to be worth naming: **ADR and ADN are published free of charge by UNECE and
RID by OTIF.** All four PDFs are the official legal texts and cost nothing. What was
actually missing was a network route from the development container — not the documents.
`scripts/read_land_regulations.py` fetches them on a runner and quotes the provisions the
application implements, so a claim about ADR, RID or ADN can be checked against the text
rather than against someone's memory of it.

The same turned out to be true of the IMDG Code, and later than it should have been. The
consolidated volumes are sold by the IMO, so this document long recorded sea as unread —
but resolution MSC.556(108), which is freely distributed, states that "the complete text
of the IMDG Code is replaced by the following" and then prints it. The Dangerous Goods
List was extracted from it in v1.48.0 and chapter 5.3 in v1.150.0. Where this document
names a figure for these four regimes, it was read from:

| Text | Publisher | Edition |
|---|---|---|
| ADR 2025, Volumes I and II (ECE/TRANS/352) | UNECE | in force 1 January 2025 |
| RID 2025 (Appendix C to COTIF, Annex) | OTIF | in force 1 January 2025 |
| ADN 2025 | UNECE | in force 1 January 2025 |
| IMDG Code, Amendment 42-24, via IMO resolution MSC.556(108) | IMO | in force 1 January 2026 |

**For air it has not.** The IATA DGR is sold by IATA and there is no free official text to
read. That section is still written from knowledge of how the regime is structured, and is
reliable at the level of *which chapter governs what*, not at the level of an exact limit
or table value — which is exactly why air stays behind the modality lock. The standing
policy in [Data sources](data-sources.md) is unchanged either way: no regulatory text is
redistributed here, only the factual values read out of one.

The practical consequence:

> **A rule implemented from memory is worse than no rule, because it looks like an answer.**
> For IMDG and the DGR that constraint still binds, and every statement about them below is
> marked **[verify]**. For ADR, RID and ADN it no longer does — and reading them turned up
> two things the application had been getting wrong, both described in their own sections.

Where a statement about sea or air is one I would want checked before anyone leans on it,
it is marked **[verify]**. Statements about the three land regimes carry their provision
number instead.

## The three questions a consignor has to answer

Before any software helps, the work divides into three:

1. **Is it classified correctly?** UN number, proper shipping name, class and division,
   subsidiary hazards, packing group. This is where a mistake is most expensive and where
   it is least visible, because everything downstream inherits it.
2. **May it travel like this?** In this packaging, in this quantity, next to these other
   goods, on this vehicle or vessel or aircraft, along this route.
3. **Does the paperwork say what it must say?** In the right order, in a permitted
   language, with the declarations signed by someone entitled to sign them.

EMCargo is built for the third question, does a great deal of the first, and answers
part of the second. It does not attempt the parts of the second that depend on the
vessel, the aircraft or the route — and those are not marginal. The *vehicle* half moved
inside in v1.82.0: which tank may carry which goods is now answered from ADR 4.3.

## What the consignor can hand the driver and the boatmaster

The third question ends in paper, so this is the honest list of what comes out — and of
what has to be carried anyway and cannot come from here. One role note that governs the
whole table: **the person at the keyboard is the consignor.** The driver and the
boatmaster never draw these documents up — they receive them, carry them and, where a
provision says so (the 8.6.3 checklist), sign them on the spot. Every screen of the
wizard is therefore written to the consignor, and nothing in the application asks the
crew to prepare paperwork that is the consignor's to prepare.

| Document | Provision | Road (ADR) | Inland waterway (ADN) |
|---|---|---|---|
| Transport document | 5.4.1 | CMR with the dangerous goods particulars | ADN transport document; tank vessels get the 5.4.1.1.2 line from table C (v1.91.0) |
| Instructions in writing | 5.4.3 | the model out of the store, per language | the model out of the store, per language |
| Placarding and marking sheet | 5.3 | generated (v1.83.0) | — |
| Equipment sheet | 8.1.4 / 8.1.5 | generated (v1.96.0) | — |
| Container/vehicle packing certificate | 5.4.2 | generated, nothing pre-ticked (v1.93.0) | — |
| On-board documents list | 8.1.2 | generated (v1.93.0) | generated (v1.93.0) |
| Checklist for loading and unloading | ADN 8.6.3 | — | the model out of the store (v1.83.0) |
| Stowage plan | ADN 7.1.4.11.1 | — | generated (v1.84.0) |
| Packing list, delivery note, AVC, VGM | trade / SOLAS | generated | generated |

Two rules run through that table. **A model the regulation prints is never rebuilt**:
5.4.3.4 requires the instructions to correspond in form and content to a four-page model,
and 8.6.3 prints its checklist the same way, so both are served as the edition sets them —
page ranges measured on the edition, cut in CI from the pinned books and bundled since
v1.130.0 (`backend/seed/models/`), with the operator's own copy in the document store
taking precedence, and reported as missing rather than approximated where neither holds
a language.
**And nothing prescribed is filled in for you**: every answer on the 8.6.3 checklist is
agreed between vessel and shore at the moment of loading, and a form this application had
already ticked would be a claim about a conversation that has not happened.

What still has to be on board and cannot come from here: the driver's ADR certificate and
the ADN expert, the vehicle's certificate of approval (9.1.3) and the tank's, the vessel's
certificate of approval (ADN 8.1.2), and the insurance papers. Since v1.93.0 the on-board
documents list names every one of them, per consignment, next to the papers this
application drew up — the split between "here are your documents" and "this part you
must bring yourself" is itself a document now.

## What is held, per substance

| Source | Contents | Covers |
|---|---|---|
| `seed/dg/un_numbers.json` | ADR Table A: class, classification code, packing group, labels, special provisions, LQ, EQ, packing instructions, transport category, tunnel code, hazard number, English and German names | 2,928 rows over 2,336 UN numbers |
| `seed/dg/imdg_dgl.json` | IMDG Dangerous Goods List (Amdt. 42-24): class, subsidiary hazards, PG, special provisions, LQ, EQ, packing/IBC/tank instructions, EmS, stowage and handling (16a), segregation (16b), properties | 2,860 rows over 2,347 UN numbers |
| `seed/dg/card_data.json` | Per-substance marine pollutant status and bulk carriage | 2,336 UN numbers |
| `seed/dg/ems.json` | Fire and spillage schedules | 2,338 UN numbers |
| `seed/dg/segregation_groups.json` | SGG1–SGG18 assignments | 629 entries over 539 UN numbers |
| `seed/dg/imdg_codes.json` | SW1–SW31, H1–H5, SG1–SG78 with their wording | 110 codes |

What is **not** held for any substance: IATA quantity limits per packing instruction,
ADN Table C, and any state or operator variation.

**Tank carriage is modelled since v1.66.0.** Every check in this application was
written for packages and said so nowhere, so a tank load got the packages answer with
nothing to mark it as the wrong one. A per-substance **mode of carriage** — packages, ADR
tank, portable tank or bulk — now says how the goods travel, and the first check to use it
answers whether they may travel that way at all (ADR 3.2.1). Absent means packages, which
is what every consignment drawn up before this release was.

**Two more answers branch on it since v1.67.0.** The **tunnel** code of 8.6.4 gives five of
its twelve codes two answers — B/D, B/E, C/D, C/E and D/E bar more categories for tanks and
bulk than for packages — and both lists had been in this repository since v1.50.0 with only
the packages one ever read. And the **orange plates**: 5.3.2.1.6 *permits* the hazard and UN
numbers for packages, while 5.3.2.1.2 *requires* them on both sides of every tank and
compartment. Permitted and required are not the same finding.

**And since v1.68.0 the security table.** Table 1.10.3.1.2 has three quantity columns and
only the packages one was answered. Seven of its rows are footnote b) in packages — never
high consequence, whatever the quantity — and **3,000 litres in a tank**. Flammable liquids
of packing groups I and II are among them, so a road tanker of petrol is high consequence
dangerous goods and needs the security plan of 1.10.3.2; this check used to say it did not.

**And the exemption itself, since v1.69.0.** 1.1.3.6.2 grants it for goods carried *in
packages* in one transport unit. A tank or bulk load is not carriage in packages, so it
cannot claim the exemption whatever the quantity — and the points arithmetic, which exists
only to test that exemption, is answering a question that does not arise. This also reaches
the tunnel: 8.6.3.3 drops goods carried under 1.1.3 out of the determination, and a tank
load is no longer dropped on the strength of a points total.

**Column 6 read, since v1.163.0.** The last thing chapter 5.2 said it had not done.
IMDG 5.2.2.1.2 lets a special provision add a subsidiary label where column 4 shows none
and remove one where it does; 5.2.2.1.2.1 lets one drop the labelling altogether. The
column cites **262 distinct provision numbers** across the list, and all 262 were found in
chapter 3.3. **Forty-two** of them mention a label, a mark or an exemption, and each was
judged: eighteen bear on the labels a package carries, twenty-four name a mark or an
exemption while doing something else — classification, the watt-hour marking of a battery,
the technical name that supplements the proper shipping name. Both lists are in the seed by
number, because the difference between a provision that was judged and one that was never
opened is exactly what a coverage claim is about.

**Only one of the eighteen is applied.** Special provision **384** says in as many words
that the label is model No. 9A and that only the placard on the cargo transport unit is
model No. 9 — so the battery label now comes from the column that assigns it, per
substance, instead of from the inference across three provisions that v1.161.1 had to
make. The other seventeen condition rather than decide: on a competent authority's
permission (133, 181), on how much phlegmatizer a mixture holds (271), on whether an
article is water-activated (942), on which packing instruction was used (219, 294, 319),
on whether a vehicle is enclosed (405). Those are **named against the entry that cites
them**, with the effect they would have, and left to the packer who can see the drum.

Reading it took three wrong parsers, and the third is the one worth recording. The
provision numbers stand in a narrow column, and the chapter is printed with **mirrored
margins** — x=125 on one side of the spread, x=96 on the other. Calibrating on the single
most crowded position found 140 of the 262 and reported the other 122 as absent, with no
complaint about ordering, because the half it read was internally perfect. That the two
positions account for exactly 262 between them is what gave the layout away. The column is
now measured per page.

One more thing the reading turned up, in this repository rather than in the Code. Both
books have a column 6 and they are **different sets of numbers**: UN 3480 carries special
provision 384 in the Code and does not in Table A. The first version of the check read
Table A to answer the sea question, which is the exact mistake this module was built to
avoid and would have left no trace — the numbers look plausible either way. The two
readers are now named for the book they come from.

**The two remaining figures measured, since v1.162.0.** The battery mark and the
orientation arrows were named on the sheet instead of printed, because their artwork had
never been cut from the edition the way the twenty-three class label models were. Both are
now measured, and each answered a different question.

The **orientation arrows** are printed twice on the page, identical apart from a
rectangular border 5.2.1.10.1 calls optional, under two captions set side by side on one
line. Shape cannot tell them apart, so the captions were matched to the drawings by their
own horizontal position: the unframed pair is Figure 5.2.1.10.1.1 and the framed one is
Figure 5.2.1.10.1.2, and the framed one is what the sheet cuts. The provision gives them
**no size at all** — "clearly visible commensurate with the size of the package" — so the
size the sheet prints them at is named on the page as the sheet's own choice.

The **battery mark** is cut down to its symbol alone. Its printed figure is wrapped in
dimension annotations that abut the hatched edging, so a box around the whole mark takes
the annotations with it; and everything except the symbol is stated in 5.2.1.9.2 in words —
a rectangle 100 mm by 100 mm, red hatched edging at least 5 mm wide, the symbol above the
UN number or numbers. So the frame is built from those values and the symbol is the
edition's own. That also fixes something printing the figure verbatim would have got
wrong: the figure carries an asterisk where the number goes, and an asterisk on a package
says nothing.

One measurement fault was found on the way and is worth recording, because it would have
recurred. The blob detector that finds a figure on a rendered page thresholded the **red**
channel and called anything above it paper. Red ink has a high red value, so the battery
mark — whose edging is hatched in red — was invisible to a detector pointed straight at it,
and so would have been anything else printed in colour. For a chapter about coloured
labels that is the whole subject. It now thresholds the darkest of the three channels.

**Four of the open points closed by reading, since v1.161.1.** The IMDG Code was in the
store all along, so three of the four gaps v1.160.0 recorded needed a read rather than a
request. It places the **lithium battery mark at 5.2.1.10** — where the land regulations
put the orientation arrows, which is the sharpest illustration of why an IMDG rule may
never be cited by an ADR number. It asks for the three months' immersion **twice**, at
5.2.1.2 for marks and at **5.2.2.2.1.7** for labels. And **special provision 188** names
model No. 9A alongside that mark, and carries exemptions of its own: button cells
installed in equipment, and no more than four cells or two batteries in equipment where
the consignment holds at most two packages, plus an overpack rule requiring the mark to
stay visible or be reproduced with "OVERPACK" in lettering of at least 12 mm.

The sheet also now names **BS 5609**, the standard by which the labelling trade shows a
material survives those three months. Telling a packer that paper will not do, without
saying what will, is half an answer.

**Where that warning is printed, since v1.163.1.** It used to be printed once, in full,
on the working page. The material is not chosen there — it is chosen at the printer, and
the page in hand at that moment is the artwork page, so the only statement of what the
stock has to be sat on a sheet that may never be printed at all. Every page carrying a
figure now repeats it in one line, and a test asserts that none is without it, in all
four languages, finding those pages by the figure on them rather than by page number.

It sits above the cut marks by design. The label itself cannot carry it: a label with a
sentence printed on it is not the label the regulation prescribes. So the line does its
work before the cut and comes off with the offcut — which is the whole of what it can
do, and enough, because the argument for printing labels at all (a package label really
is printed on adhesive stock, where a placard on a laser printer is not a placard) rests
on the material being stated where the material is chosen.

**What an empty uncleaned packaging counts for, since v1.166.0.** ADR 1.1.3.6.1
reassigns it: one that contained a transport category 0 substance stays in category 0,
and one that contained anything else becomes **category 4** — whose factor is 0, so it
counts nothing at all towards the thousand. The two closing lines of the 1.1.3.6.3 table
say the same from the other side, with UN 2908 named as the exception because that entry
is itself an empty packaging and the table lists it under category 4.

The check used to read the substance's own category, so one empty drum of a packing
group II liquid came to **900 of the 1000 points**. That is wrong in the safe direction
and still wrong: a relief the regulation grants was withheld, and a load went out under
rules it did not have to follow.

Two things the fix had to keep apart. Category 0's factor is **null**, not zero, and the
two mean opposite things — zero is "counts nothing", null is "no exemption exists at
all". The first version treated them alike and reported a possible exemption for a drum
that had contained a category 0 substance, which is the one direction this arithmetic
must never be wrong in. And a reassigned line needs **no quantity**: 5.4.1.1.1 (f)
composes none for residues nobody has weighed, and factor 0 makes the arithmetic the same
whatever it would have been.

**The limited quantities mark, since v1.165.0.** It belongs to chapter 3.4 rather than
5.2, which is why 5.2 could be closed without it and why it was still owed. ADR 3.4.7.1
states nearly all of it — a square set at 45 degrees, top and bottom portions and the
surrounding line black, the centre white, minimum 100 mm a side, the line at least 2 mm —
and leaves exactly one thing to the drawing: how deep the black portions run, under
"where dimensions are not specified, all features shall be in approximate proportion to
those shown". That one number was measured off Figure 3.4.7.1 itself, at 81 and 82 pixels
of a 353-pixel height; the two agree to a pixel because the figure is symmetric, and that
agreement is the check on the measurement.

The mark is **drawn, not cut**, for the same reason the battery mark is: the edition
wraps the figure in dimension annotations that abut the diamond, and a mark carrying a
caption about its own minimum size is not the mark the regulation prescribes.

Whether a line travels under chapter 3.4 is **not decided twice**. The LQ check already
tests the line against column 7a and the 30 kg limit of 3.4.2, and the marking check
calls that same function rather than testing the limits again — two readings of one
question is how a package comes to carry the mark on one screen and not on the other.

What is named and not applied: the 250 mm mark of 3.4.15 on the transport unit, because
3.4.13 turns on 12 tonnes and 3.4.14 on 8 tonnes and both are about the whole load, which
this check does not see; the 50 mm reduction of 3.4.7.2, which is a judgement about the
package in front of the packer; and the "Y" of 3.4.8, which the Code says a package
*may* bear rather than shall.

**And the sea gets it too, since v1.170.0 — under its own numbers.** The IMDG Code has a
chapter 3.4 of its own, and for five releases the sea answer carried
`imdg_chapter_3_4_not_read` and claimed nothing, because the CI reader's anchor for it
landed in the Dangerous Goods List and answering the sea out of ADR 3.4.7 would be
exactly the mistake column 6 already made once. On 2026-08-26 the chapter was read
directly from the registered 42-24 edition (PDF pages 797–799), and the restraint paid
out in both directions:

- **The package mark is the identical diamond** — IMDG 3.4.5.1 states the same square at
  45°, the same 100 mm and 2 mm line, the same reduction to 50 mm and 1 mm. The drawn
  artwork serves both regimes; the sea cites 3.4.5.1 and never the land's number, and
  adds the durability clause the land does not state: readable after open weather
  exposure. The "Y" variant sits at 3.4.5.2, with the multimodal recognition of
  3.4.5.3.1.
- **Everything around the mark differs.** The unit mark of 3.4.5.5 turns on **no tonnage
  at all** — no 12 t trigger, no 8 t dispensation: a cargo transport unit carrying only
  LQ always bears the 250 mm mark, durable through three months' immersion, at the
  locations of 5.3.1.1.4.1; where the unit is placarded for other goods, the placards
  apply. And where ADR's chapter 3.4 lifts the transport document altogether, the sea
  keeps chapter 5.4 applicable (3.4.1.2.5) and 3.4.6.1 puts **"LIMITED QUANTITY" or
  "LTD QTY"** beside the description. The LQ check names both duties on every
  within-limits sea line; whether the consignment actually travels under chapter 3.4
  remains the consignor's declaration, so the words are named and never inserted.

**Chapter 5.2 answers per regime, since v1.160.0.** What goes on the *package* was the
half nobody asked for: the labels of column (5) were read for eight other purposes and
never turned into an answer for the person taping the drum shut. Four editions were read
before it was built, and the sea turned out not to be the land renumbered. The IMDG Code
marks the **proper shipping name on every package** (5.2.1.1) where ADR, RID and ADN ask
for it on Class 1 (5.2.1.5) and radioactive material (5.2.1.7.2) only. It calls the
environmentally hazardous substance mark the **marine pollutant mark** and puts it at
5.2.1.6, not 5.2.1.8, and its numbering diverges from 5.2.1.5 onwards, so no IMDG rule may
be cited by an ADR number. Its labels come from **two columns** — the primary from column 3
of the Dangerous Goods List, each subsidiary from column 4 — where Table A has one. And its
durability rule is three months' immersion in the sea against ADR's open weather exposure.
RID and ADN were quoted beside the ADR and are identical word for word.

Four things the answer refused to state when it shipped, of which one still stands. The
**orientation arrows** (5.2.1.10) turn on the kind of packaging, which the application
cannot see, so they are reported as not assessed with the provision's own four cases
named — and since v1.162.0 the figure is printed anyway, behind a caption that names the
four cases of 5.2.1.10.1, the six exceptions of 5.2.1.10.2 and the prohibition of
5.2.1.10.3. A packer who does need them would otherwise have nothing. The **marine
pollutant exemption** and the **sea battery label** were both closed by reading in
v1.161.1, and **column 6** by reading in v1.163.0. Nothing on this chapter is left open.

One value had to be settled outside the regulation. "100 mm x 100 mm" for a square set at
45 degrees leaves two readings — the side, or the bounding box — that differ by root two.
Measuring the official figure did not settle it: the ADR draws the prescribed 5 mm inner
line at a spacing of 0.51 pt on a 96.89 pt side, which is the stroke width of the outline
and not the border, so the drawing is schematic on this point. 49 CFR 172.407(c)(1)
prescribes the identical shape, the identical 100 mm and the identical 5 mm border measured
from the outside edge, and says "on each side". The side is the 100 mm; a full-size label
is 141.4 mm from point to point.

**The placards invert, since v1.70.0.** For packages 5.3.1.5 puts a placard on the vehicle
only for class 1 and class 7 — which is why the packages answer is mostly that none is
needed. For a tank or a bulk load 5.3.1.4.1 requires a placard of *every label model of the
load* on both long sides and the rear, and 5.3.1.2 the same on both sides and each end of a
tank container or portable tank. Answering a tank with the packages rule turned a
requirement into an absence.

**The ADR tank columns are held since v1.65.0** — the portable tank instruction (10) and its
provisions (11), the ADR tank code (12), its provisions (13) and the vehicle the substance
then requires (14). They were read and cross-checked from the first day of the extractor and
kept out of the seed on purpose, because nothing computed with them. That release carried
them as data and deliberately refused to read an empty column (12) as "not accepted in a
tank", however plainly the pattern suggested it — a statement about what the ADR *permits*
is not an observation about a table. v1.66.0 read the text (3.2.1, printed pages 546-547)
and the admission check acts on it now.

## Road — ADR

**Checked:** the 1.1.3.6 points calculation (categories, factors, the 1,000-point
threshold, category 0 as a hard stop); the 7.5.2 mixed-loading prohibitions including
CV28 for foodstuffs and, since v1.38.0, footnotes (b), (c) and (d) of table 7.5.2.1 read
from the official text and applied per pair of packages rather than per consignment; and
the quantity limits of chapters 3.4 and 3.5 — the entered net
per inner packaging against column 7a and the E code of column 7b, the 30 kg gross
limit of 3.4.2 (naming the 20 kg tray limit of 3.4.3), and the 1,000-package cap of
3.5.5. When packages that fall within the LQ limits total more than 8 tonnes gross on the
transport unit, ADR 3.4.13/3.4.14 is raised so the large LQ mark of 3.4.15 is not missed.
For class 1 the 1.1.3.6 points use the entered net explosive mass, not the product mass.
Classification comes from Table A; the row is narrowed by whatever the user has filled in —
the classification code first, then the packing group — and where more than one row is still
in the running, the panel says how many, what they differ in and which field settles it.
Until v1.51.0 only a varying *packing group* was flagged, which left fifteen UN numbers to
be resolved in silence, UN 1950 aerosols and UN 2037 gas cartridges among them. Carriage-prohibited
substances are kept out of the points table. The description line follows 5.4.1.1.1 and
the tunnel code is printed, correctly, only here — and since v1.50.0 the code for the whole
load is derived from it under 8.6.3.

Since v1.33.0 the figures behind those checks have been read out of ADR 2025 Volume I
rather than recalled. Confirmed verbatim: the 30 kg gross mass of **3.4.2**, the 20 kg for
shrink- or stretch-wrapped trays of **3.4.3**, the 1,000-package cap of **3.5.5**, and the
whole of table **3.5.1.2** — E1 30/1000, E2 30/500, E3 30/300, E4 1/500, E5 1/300, in grams
for solids and millilitres for liquids and gases, with E0 not permitted. Every value the
application had was correct. Saying so on the strength of the text is worth more than
saying so on the strength of a recollection that happened to be right.

**One thing was wrong, and it cost users money.** Note (a) to the table in 1.1.3.6.3 reads:
*"For UN Nos. 0081, 0082, 0084, 0241, 0331, 0332, 0482, 1005 and 1017, the total maximum
quantity per transport unit shall be 50 kg"* — and the matching multiplier, spelled out in
RID 1.1.3.6.4, is **× 20** rather than the × 50 of ordinary transport category 1.
EMCargo applied × 50 to all nine. 50 kg of chlorine (UN 1017) or anhydrous ammonia
(UN 1005) therefore scored 2,500 points and lost the 1.1.3.6 exemption, when 50 × 20 is
exactly the 1,000 the text allows. The application was insisting on orange plates, a driver
certificate, written instructions and an ADR vehicle for consignments entitled to the
exemption. Fixed in v1.33.0.

**Since v1.56.0 the table is ADR 2025 itself.** Until then it was an export of ADR **2023**,
patched: the eleven rows 2025 added were carried in by hand and the two it withdrew were
flagged in place. A patch covers what an edition added and nothing of what it changed, and
2025 changes a field on 316 of the 2,334 UN numbers the two share. All twenty-three columns
are now read out of the official Dutch edition — 3,158 rows, 2,345 UN numbers, no unreadable
page — and checked against the alphabetical index of that edition, which is the same table
set a second time. Eleven of the thirteen compared fields agree on every UN number.

Three of those changes are worth naming, because each was an answer the application was
giving with confidence:

- **UN 3423 tetramethylammonium hydroxide, solid** moved from class 8 to **class 6.1**.
  Different labels, transport category 1 instead of 2, hazard identification number 668
  instead of 80 — the number that goes on the orange plate.
- **The three UN 0015 rows** carry their own subsidiary hazard again: 1, 1 + 8 and
  1 + 6.1. The export gave all three the same labels column, so the corrosive and the toxic
  variant lost their second label on the way to the document.
- **UN 1950 aerosols** are in the ADR's own order, which opens at 5F — the flammable spray
  can. The export was sorted alphabetically, so an unspecified aerosol was filled in as 5A,
  the *non-flammable* row: the exact reading v1.51.0 showed costs a factor of three in
  points.

Two things the Dutch edition cannot supply, and where they come from instead: the **English
and German** proper shipping names, which have no column in it, and **which UN numbers are
not admitted for carriage** — the Dutch table writes a prohibition by leaving the row empty,
and writes "not subject to ADR" the same way, so the fourteen prohibited entries come from
the 2023 export, which names them in words. Both are in the manifest errata.

This is the mode EMCargo serves best, and the reason is simple: ADR Table A is the
dataset it was built on.

**Not checked, and worth knowing:**

- **The route is still not known, and that is the part that remains.** Since v1.50.0 the
  load's own tunnel restriction code *is* derived, from ADR 8.6.3 read out of the book:
  8.6.3.2 assigns the most restrictive code of the load to the whole load; 8.6.3.3 leaves
  goods carried under 1.1.3 out of that determination entirely, except where the 3.4.13
  marking applies; and the table of 8.6.4 turns the code into the tunnel categories that
  are barred, with B1000C and C5000D splitting on the total net explosive mass per
  transport unit. The result reaches the export as well as the panel. What EMCargo still
  does not know is which tunnels lie on the route and which category they carry — that is
  the carrier's, under 1.9.5 — and whether the goods travel in tanks or in bulk, which is
  stricter for five of the twelve codes. Both are said next to the answer.
- **LQ and EQ are compared, not granted.** The quantity check of 3.4 and 3.5 says
  whether a line falls within or outside the limits, or that the input is incomplete.
  What it deliberately does not do is treat qualifying as being exempt: the LQ/EQ mark,
  the packaging requirements of 3.4.1/3.5.2 and the tests of 3.5.3 are conditions the
  application cannot see, so a qualifying line is reported next to the points table and
  never removed from it. The limits have since been checked against the published 3.4.2,
  3.4.3, 3.5.1.2 and 3.5.5 and are correct.
- **The compatibility groups of 7.5.2.2 are evaluated since v1.41.0**, against ADR's own
  table read from printed page 593 — twelve groups, A to S, with no group K. An empty cell
  is an error, an X passes silently, and the four footnotes come back as the condition they
  state. Two releases were needed to get here and the order is worth recording: until
  v1.40.1 the check crashed when it fired, and it only ever fired if the group happened to
  sit in the class column, which for explosives it does not. Group S is now included, so
  1.4S beside a group L package is refused — the old code carried the 7.5.2.1 exception for
  1.4S into a table where it does not belong.
- **The two EQ provisions that only show up across lines are applied since v1.50.0.**
  3.5.1.3: where goods with different E codes are packed together, the total per outer
  packaging is capped by the most restrictive of those codes — 400 g of an E1 substance
  beside 200 g of an E3 one is over the 300 g cap while each line on its own is within its
  own code, which is exactly what assessing line by line cannot see. And 3.5.1.4 relieves
  the smallest quantities (E1/E2/E4/E5, ≤ 1 g or 1 ml inner and ≤ 100 g or 100 ml outer) of
  everything but 3.5.2 and 3.5.3 — including the 3.5.5 cap, so those packages no longer
  count towards the 1,000. The two fail in opposite directions: the first let a package
  through that the text caps, the second refused a load the text permits.
- **The vehicle, except its equipment and its tank.** Driver training (8.2) and the ADR
  certificate of approval are outside the application. The tank is not, since v1.82.0:
  column (12) says which tank code a substance *requires*, and **4.3.3.1.2 and 4.3.4.1.2
  now answer whether the tank that actually turned up may carry it** — see below. The
  equipment of **8.1.4 and 8.1.5 is derived** since v1.53.0, because 8.1.5.1 chooses it by
  the hazard label numbers of the goods loaded and points at the transport document to
  identify them — which is what EMCargo holds. It is a checklist and not a finding; the
  application cannot see what is in the cab.
- **Placarding and marking are derived since v1.57.0, for carriage in packages.** The
  useful half of 5.3 turned out to be the refusals. 5.3.1.5 gives a vehicle carrying
  packages two reasons to placard — class 1 other than division 1.4 compatibility group S,
  and class 7 other than excepted packages — so a load of packaged petrol, nitric acid or
  toxic liquid needs none, and the orange plates of 5.3.2.1.1 are the whole of it. Where the
  consignment is a single substance, 5.3.2.1.6 lets those plates carry the hazard
  identification number over the UN number, and both come out of table A, so they are
  printed. And 5.3.6.1 opens "when a placard is required": the environmentally hazardous
  mark on the *vehicle* therefore hangs on the placard, not on the substance, so packaged
  class 9 marine pollutant marks the package and not the truck. Tanks and bulk have their
  own subsections and are not answered; the elevated temperature mark of 5.3.3 turns on a
  carriage temperature nobody tells the application.
- **Since v1.83.0 the answer is also a sheet.** 5.3 was derived and shown on screen only,
  and the person who needs it is standing at the back of a trailer with plates in his hand.
  The placarding sheet lists the placards and the orange plates with the provision that
  asked for each and the numbers already worked out. It says out loud that it is not itself
  a placard: 5.3.1.7 and 5.3.2.2 govern the real ones. Putting it on paper found two errors
  in the answer, both a tank load being answered as if it were packages — `placards_required`
  counted only the placards 5.3.1.5 picks by class, so a tank of petrol reported "no
  placards required" underneath the finding that required them, and 5.3.6.1 inherited that
  miscount for the environmentally hazardous mark.
- **The tank hierarchy of 4.3 is applied since v1.82.0.** Two provisions that share nothing
  but their purpose: **4.3.3.1.2** is a hierarchy of *codes* for gases, and **4.3.4.1.2** is
  the rationalized approach for classes 3 to 9, where the offered code names the group of
  substances it may carry and the required code is never compared with it. Both were read
  from three books — the English volume II, the printed Dutch edition and the German volume
  II. Fifteen of the sixteen gas rows are settled by more than one reading; of the eighteen
  tank codes of the rationalized approach **fifteen are settled on every cell** since
  v1.86.0, when the German reading began to work, and the three that are not still make the
  check decline rather than answer. Finding the German table took the one anchor that is not
  a phrase: that edition heads the columns of *table A* with "Tankcodierung" and
  "Klassifizierungscode" as well, so a reader looking for headings started three hundred
  pages early and read table A instead. The provision's own number does not have that
  problem. Three measured details shape it: the regulation's own note that the
  hierarchy takes no account of the special provisions of 4.3.5 and 6.8.4 (column 13), which
  travel with every answer; a condition inside the packing group cell (LGBF admits packing
  group II of class 3 F1 only where the vapour pressure at 50 °C is at most 1.1 bar); and the
  test pressure printed as **x** in column (12) for most gases, which comes from the table of
  4.3.3.2.5 and is not in this application, so the answer says so instead of comparing a
  figure that is not there.
- **The degree of filling is computed since v1.87.0**, and what decides it is the same tank
  code. 4.3.2.2.1 gives four maxima — 100, 98, 97 and 95 — over `1 + α (50 − tF)`, and which
  applies turns on the tank's venting and on how dangerous the substance is. The venting is
  the *fourth letter of the tank code*: N is a breather device or safety valves, H is
  hermetically closed without a safety device, so that half is read rather than guessed. The
  other half — toxic or corrosive against merely flammable — is derived from the class and
  the subsidiary risks, and is shown as a derivation so it can be overruled. Table A carries
  neither density, so α comes from the consignor: with d15, d50 and the filling temperature
  the answer is a percentage, and without them the answer is the formula, which goes on the
  document as a condition. Above 50 °C the application says 4.3.2.2.3 has taken over and
  does not compute; classes 1, 5.2 and 7 are sent to 4.3.4.1.3, as the provision's own
  footnote does.
- **High consequence dangerous goods are derived since v1.58.0.** Table 1.10.3.1.2 turns
  out to be easier than it looks once it has been read: for carriage in packages its column
  holds two values and no others — **0**, meaning any quantity at all, and footnote **b)**,
  meaning 1.10.3 does not apply whatever the quantity. There is no threshold to compare
  against. What the table catches is class 1 (divisions 1.1, 1.2, 1.5, 1.6, 1.3 group C and
  fifteen named 1.4 entries), the toxic gases, the desensitised explosives, packing group I
  toxics and category A infectious substances. What it does *not* catch is the half a user
  would guess: flammable liquids, corrosives and packing group I oxidisers are all footnote
  b) in packages. Class 7 is not answered — 1.10.3.1.3 measures it in activity against
  3,000 A2 — and neither are the tank and bulk columns, whose 3,000 litre and 3,000 kg
  thresholds are relevant only where table A permits that form of carriage.

## Rail — RID

**Checked:** the 1.1.3.6 quantity calculation — and since v1.33.0 that is a statement about
RID, not a borrowed ADR figure.

RID 1.1.3.6 has been read. It settles a question this document previously listed as an
assumption:

- **RID 1.1.3.6.3** sets out the same five transport categories with the same maximum
  quantities — 0, 20, 333, 1000 and unlimited — as ADR.
- **RID 1.1.3.6.4** prescribes the same multipliers: category 1 × 50, category 2 × 3,
  category 3 × 1, against the same calculated value of **1000**.
- What differs is the **unit of account**. RID counts per *wagon or large container*; ADR
  per *transport unit*. RID 1.1.3.6.1 and 1.1.3.6.2 are `(Reserved)` where ADR has text.

So the arithmetic was right all along, and the old warning that "RID has its own 1.1.3.6
which EMCargo does not hold" was true but unhelpfully vague — it invited the user to
distrust a number that is in fact the number RID prescribes. The panel now cites
1.1.3.6.3/1.1.3.6.4 and names the difference in unit instead of hedging.

**And v1.124.0 read what the number *governs*, which differs more than the unit does.**
RID 1.1.3.6.3 opens "Where, in accordance with 1.1.3.1 (c), dangerous goods … are
carried" — and 1.1.3.1 (c), read on page 27 of the English edition and confirmed in the
German, is the exemption for **carriage by enterprises ancillary to their main activity**,
at most 450 litres per packaging and never class 7. RID has no general small-load relief
the way ADR 1.1.3.6 grants one: staying under 1000 relieves an ordinary rail consignment
of nothing. The points card says so now, and the absence of an exemption branch in the
rail placarding check is a reading rather than caution — chapter 5.3 stands whatever the
points total.

**And reading it found a bug that affects road as much as rail.** Note (a) to the table in
1.1.3.6.3 reads, in both ADR and RID: *"For UN Nos. 0081, 0082, 0084, 0241, 0331, 0332,
0482, 1005 and 1017, the total maximum quantity per transport unit shall be 50 kg."* RID
1.1.3.6.4 gives the matching multiplier in words — those goods count **× 20**, not × 50.
EMCargo applied × 50 to all of transport category 1, so 50 kg of chlorine scored 2500
and lost an exemption the text grants at exactly 1000. The application was demanding orange
plates, a driver certificate and an ADR vehicle for loads that do not need them. Fixed in
v1.33.0 for both ADR and RID.

The tunnel code remains correctly absent from the CIM: RID 5.4.1.1.1 has been read and its
list of particulars — (a) UN number, (b) proper shipping name, (c) labels or class,
(d) packing group, (e) number and description of packages, (f) total quantity, (g) consignor,
(h) consignee, (i) any special agreement declaration, (j) the hazard identification number
where 5.3.2.1 marking is prescribed — contains no tunnel restriction code.

**What a rail specialist would additionally expect:**

- ~~**The hazard identification number before the UN number.**~~ On the document since
  v1.88.0. RID 5.4.1.1.1 (j) requires it when 5.3.2.1 marking is prescribed, in the order
  (j), (a), (b), (c), (d) with no information interspersed — the RID's own example is
  `663, UN 1098 ALLYL ALCOHOL, 6.1(3), I`, and that is now the line EMCargo composes. What
  decides it is 5.3.2.1.1, read in the English edition and the German: the plate is
  prescribed for tank-wagons, battery-wagons, wagons with demountable tanks, tank-containers,
  MEGCs, portable tanks and wagons or containers for carriage in bulk. For a full load of
  packages of one and the same substance it *may* be affixed, and whether a wagon was plated
  is not visible from here — so that case is asked rather than decided, and a prescribed
  marking with no number in table A is reported as the incomplete description it makes.
- ~~**7.5.2.4**~~ — applied since v1.88.0: mixed loading of dangerous goods packed in limited
  quantities with any explosive substance or article is prohibited for rail, except division
  1.4 and UN 0161 and 0499. Read on page 1103 in the English edition and 1187 in the German.
  It needed no new data; which lines fall within the LQ limits is the 3.4 check's answer,
  taken from it rather than computed again. There is no ADR equivalent.
- ~~**Shunting and marshalling** beyond 7.5.3~~ — the shunting marking is derived since
  v1.121.0, and reading it showed the question is smaller than it looked. The column (5)
  explanation of 3.2.1 (page 258 of the English edition) says the bracketed models 13 and 15
  are only ever affixed in two cases: **class 1, on both sides of wagons comprising a full
  load; class 2, on both sides of tank-wagons, battery-wagons, wagons with demountable tanks
  and wagons carrying tank-containers, MEGCs or portable tanks**. Since v1.123.0 the
  per-substance half is read as well: column (5) of RID's own table A, extracted
  geometrically from the OTIF English and German editions, which agree on every one of the
  **351 rows** that bracket a model — 335 carry (+13), 16 carry (+15), all of them class 1
  (181) or class 2 (170), exactly the two cases the explanation names. The first probe run
  is worth recording: the plain (13) and (15) it matched were the table's own column
  headers, printed on every page — the cells print (+13) and (+15), and the plus sign is
  the discriminator. So a chlorine tank-wagon is told its model by name, UN 0331 — class 1,
  no bracketed model in either edition — is told the absence is real, and the one thing
  still named as a condition is the one thing still invisible: whether a wagon comprises a
  full load. The exclusion of model 13 from the description line (5.4.1.1.1 (c)) stays a
  guard.
- **The CIM's own dangerous goods fields.** Box 24 (NHM) is picked from the UIC's NHM 2025
  nomenclature since v1.184.0 (5,640 six-digit codes, English and French labels), with the
  six-digit format still enforced; the entries in boxes 21/23 come from the shared DG data
  without rail-specific validation.

**What rail did get, from its own text.** Two provisions moved out of this list in v1.41.0
and both came from OTIF's own pages rather than from ADR on loan:

- **7.5.2.2, the compatibility groups** (page 1102). RID's table is ADR's table *minus
  compatibility group A* — road runs A to S, rail B to S, and neither lists group K. So the
  rail leg is evaluated against the rail table, and a group A package on rail is told that
  the table does not cover it rather than being given ADR's row. The four footnotes are
  word for word the same in both texts.
- **7.5.3, the protective distance** (page 1103). 18 m, or two 2-axle wagons or one wagon
  with four or more axles, between a unit placarded 1, 1.5 or 1.6 and one placarded 2.1, 3,
  4.1, 4.2, 4.3, 5.1 or 5.2. Note what the text does *not* say: model 1.4 is not among the
  triggers, and classes 6.1, 8 and 9 are not among the counterparts. This is the one place
  where the ADR chapter could never have stood in — 7.5.3 is about how a train is made up,
  and a road transport unit travels alone, so borrowing would have produced no answer rather
  than a rough one. Since EMCargo cannot see the rest of the train, a consignment with a
  class 1 wagon and no counterpart of its own still gets the provision, addressed to the
  carrier.
- **CW 28 instead of CV28.** RID column (18) names the foodstuffs provision CW 28; the
  application cited ADR's CV28 on rail as well. The text of 7.5.4 is identical in both, so
  nothing changes about the requirement — but a CIM that quotes a code the RID does not have
  is the same category of defect as the tunnel code that used to be printed on it.

**Assessment:** rail is no longer the weakest of the five, and since v1.41.0 it is no longer
mostly road on loan either. The quantity calculation, the mixed-loading table, the
compatibility groups and the protective distance are all cited to RID — and since v1.88.0
so is 7.5.2.1, whose table is identical in both texts and whose *name* was not: "ADR
7.5.2.1" on a CIM is the same category of inaccuracy as the CV28 that used to appear there
in place of CW 28. **Since v1.121.0 rail has its own chapter 5.3 as well** — read in the
English edition (printed pages 837–845) and the German, which agree: a wagon carrying
packages is placarded for every class (5.3.1.5), where a road vehicle placards only for 1
and 7; the orange plates attach only where column (20) gives a hazard identification number
(5.3.2.1.1), each side of the tank or bulk wagon, with no plain front-and-rear plates at
all; the orange band of 5.3.5 follows the state of the gas out of the classification code
(2 liquefied, 3 refrigerated liquefied, 4 dissolved); and the shunting marking of 5.3.4 is
a named condition (see above). The per-substance bracketed models of
RID's own column (5) were extracted in v1.123.0 from two of the four editions the store
holds — the OTIF English and the German, which agree on all 351 rows — so nothing
genuinely rail-specific is left unread; what stays with the carrier stays named. Since
v1.124.0 both 5.3.4 cases are decidable per consignment: the class 2 case by the declared
mode of carriage, the class 1 case by the consignor's own **full-load statement** — a
wagon-level fact no table supplies, so it is a field, like the containers-only statement
of ADN 7.1.5.0.2 before it. And the RID's own **instructions in writing** (5.4.3.4, the
four-page model addressed to the train driver) are served from the store in all four
languages, page ranges measured per edition; 5.4.3.2 keeps providing them the carrier's
duty, and the application says so.

**The mode came off the lock in v1.122.0**, over the same bar inland waterway cleared in
v1.63.0: the checks a rail consignment gets are cited to RID rather than borrowed, the
placarding of chapter 5.3 is derived and on paper, and the CIM flow is verified end to
end in the rail archetypes — a package wagon and a chlorine tank-wagon, through the real
API, compliance and documents alike. What stays open stays named: everything that is the
wagon or the train itself — full-load status included, which is what keeps 5.3.4 a
condition even now that its column is read. (The CIM's NHM box, long on this list, came
off it in v1.184.0 with the UIC's own nomenclature behind it.)

## Inland waterway — ADN

**Checked:** ADN 1.1.3.6.1 — its own exemption, with its own table. Since v1.33.0 this is
the only mode whose exemption answer is not the ADR points total.

Reading ADN 1.1.3.6 produced the single most consequential finding in this assessment.
**ADN has no points calculation at all.** It does not use transport categories, it has no
multipliers, and there is no threshold of 1000. ADN 1.1.3.6.1 exempts a consignment carried
in packages when

- the **gross mass of all dangerous goods together does not exceed 3,000 kg**, and
- **no class exceeds its own figure** in the table: 0 kg, 300 kg or 3,000 kg depending on
  packing group, class 2 group, or whether a model No. 1 label is required.

Carriage in tanks is never exempt, for any class. Class 1 is 0 kg. Class 2 toxic groups
(T, TF, TC, TO, TFC, TOC) are 0 kg; group F is 300 kg; anything else in class 2 is 3,000 kg.
Class 7 is 0 kg except UN 2908–2911, which are 3,000 kg.

Until v1.33.0 an ADN shipment was shown the ADR points table. That is not an approximation
of the ADN answer — it answers a different question, and the two can point in opposite
directions. The concrete case, now pinned by a test:

> 1,200 litres of a packing group III liquid scores 1,200 ADR points and **loses** the
> exemption above the 1,000 threshold. Under ADN the class 3 "any other substances" figure
> is 3,000 kg and the total is under 3,000 kg, so the same consignment **is** exempt.

A user preparing an inland waterway shipment was being told to comply with requirements
that ADN does not impose on them — or, in the mirror case, reassured by a road threshold
that ADN does not use. The panel now shows an ADN card with its own status, the per-class
figures, and the conditions of 1.1.3.6.2 that survive the exemption (the 1.8.5 reporting
obligation, packagings to Parts 4 and 6, the 5.2 marking and labelling, the transport
document and stowage plan on board, stowage in the holds, and 3 m horizontal separation
between classes).

**Also checked, since v1.59.0:** ADN **7.1.4.3**, separation of packages in the holds. This
is not the road rule renamed. ADR 7.5.2 asks whether two packages may share a vehicle and
answers yes or no; 7.1.4.3 asks how many metres must lie between them, which is an answer
the application could not previously express at all. Different classes go 3.00 m apart and
are never stacked; class 1 goes 12 m from everything else.

**And since v1.61.0:** the ADN's **own table A**, read out of the Dutch edition by
`scripts/extract_adn_table_a.py`. Its first columns identify the goods as the ADR's do —
checked substance by substance against the ADR table already in the repository, and the
class and the name agree on all 2,343 they share — and then it answers a vessel's
questions. **Column (12), the number of blue cones or blue lights**, closes two things:

- the cone half of 7.1.4.3 — 7.1.4.3.2, which forbids two-cone goods a hold with one-cone
  flammable goods, and the three-cone extension of 7.1.4.3.3 to classes 4.1 and 5.2;
- **ADN 7.1.5.0.1**, the signals the vessel must show, which had no answer at all. With
  7.1.5.0.4: where the load disagrees with itself, the heaviest signal wins, so one package
  can set the signals for the whole vessel.

**And since v1.71.0:** **column (8)**, the way the goods may travel. Everything above it is
chapter 7.1, which is the ADN's chapter for *dry cargo vessels*, and until this release a
consignment declared as a cargo tank was measured against it anyway. Column (8) is where the
regulation says which way is open: empty means carriage in packages only, `B` adds bulk and
points at 7.1.1.11, `T` adds tank vessels and points at 7.2.1.21, where Table C takes over.
Two further provisions fix what the modes mean here — **7.1.1.21** forbids carriage in cargo
tanks on a dry cargo vessel, so a cargo tank load is a tank vessel; **7.1.1.18** puts tank
containers and portable tanks under the requirements for carriage of packages, so they sail
on a dry cargo vessel and keep every answer chapter 7.1 gives them.

So a cargo tank load now gets the chapter it belongs to named rather than the wrong
chapter's answers, and 1.1.3.6.1 — whose own note has said "carriage in tanks is never
exempt" since v1.32.0 while the arithmetic granted the exemption anyway — withholds it.

**What is missing beyond that:**

- ~~Column (8) rests on one edition~~ — since v1.73.0 the English ADN is in the document
  store (fetched via the web archive by the first run of the fetch workflow) and table C
  itself carries both editions' readings.
- **The tank vessel regime beyond table C's facts.** Since v1.73.0 **table C is in the
  repository** (`adn_table_c.json`): 678 printed rows, read **three times and, since
  v1.80.0, from three books** — the row set and every cell geometrically from the UNECE
  English 2025 PDF (those pages print the table rotated, which the extractor measures
  rather than assumes), the corroboration and the Dutch names from the printed Dutch
  edition (which prints it the ordinary way round, and needs its own reader for that),
  and the UNECE French 2025 PDF, the treaty's other authentic language, which decides a
  cell wherever two of the three agree. The comparison is recorded in the seed, not
  summarised away: **677 rows settle on every cell and one carries a `disputed` cell** —
  UN 2789's density, where all three editions print 1,05 and then qualify it in their own
  language. It was 491 settled and 153 disputed when the Dutch reading came from an HTML
  export, and 673 settled when the French edition was added to that. No row rests on one
  reading, no row of any edition is left unplaced, and the French reading decided 27
  stand-offs — siding with the Dutch against the English once, over UN 2672's density.
  Four cells it alone reads differently are recorded under `french_reads_differently` and
  do not re-open a cell the first two agreed on.

  What the export cost, for the record, since the seed no longer carries it: it split a
  printed row per alternative name (52 rows for the 26 printed rows of UN 1268), swapped
  the data cells of columns (7) and (9) against its own header — caught because 362 rows
  matched perfectly once swapped and every row that matched unswapped had design equal to
  equipment — and omitted UN 1977 and UN 1999 entirely. All three are simply absent from
  the printed edition's reading.

  What the application now answers from it: the **tank vessel type** of column (6) (or the
  variants, where petrol's six rows split between N and C), and the **signals** of column
  (19) under **7.2.5.0.1**, with 7.2.5.0.2 ranking two cones before one. What it still does
  not do: check the actual vessel (design, tank type, equipment, opening pressure, filling
  degree are shown as conditions to verify), or the rest of the regime — 7.2.x operations,
  9.3 construction, 8.1 documents — which is a different discipline again.
- **The rows the ADN table A holds only once.** The table is available one row per UN
  number and the book prints several for 452 of the 2,352 substances. Where those rows
  differ in the vessel's columns — UN 1203 petrol is the clear case — no cone count is
  offered and the substance is named. 1,913 substances are settled; 439 are not.
- ~~**ADN 7.1.5.0.2**~~ — applied since v1.94.0. The thresholds were read in v1.64.0 and
  sat recorded until the input the provision itself requires existed: the consignor's
  statement that the goods travel exclusively in containers (the `containers_only` field),
  never inferred from a packaging type. Declared without the gross mass the threshold
  compares against, the full signals stand and the answer says why — over-signalling is
  the safe direction.
- ~~**7.1.4.3.4**, the class 1 compatibility table~~ — applied since v1.64.0. Twelve groups,
  four numbered conditions, and the two readings the rule demands were not a formality: the
  Dutch HTML edition is damaged there (row N has thirteen cells where twelve belong, and the
  D/B cell lost its footnote marker). The English edition mirrors across its diagonal in all
  144 cells, which is a property of a compatibility table and not of a typesetting, and that
  check is kept as a test.
- **The stowage plan of 7.1.4.11.1 since v1.84.0**, and with it the one thing chapter 7.1
  could not do before. The provision — read in the printed Dutch and the English edition,
  which agree — asks the boatmaster to set down which goods are in which hold or on deck,
  described as 5.4.1.1.1 (a) to (d) describes them in the transport document; so the plan
  uses the transport document's own descriptions rather than a second rendering of them,
  and 7.1.4.11.2's container annex comes with it. What it is not is a drawing: the geometry
  of a vessel's holds is not something this application knows. **7.1.4.3.2 is applied now
  rather than stated**: the prohibition on two-blue-cone goods sharing a hold with one-cone
  flammable goods needed a hold to compare, and where the holds are written down the finding
  names the hold it is breached in — and claims nothing where they are not.
- **The checklist of 8.6.3 since v1.83.0.** 7.2.4.10 requires it to be filled in and signed
  by the boatmaster and the shore facility before a tank vessel is loaded or unloaded, and
  the regulation prints the model rather than describing it. So it is served as the edition
  sets it, in the language asked for, or reported missing with the edition that would
  produce it — and EMCargo fills in nothing on it: every answer there is agreed between
  vessel and shore at the moment of loading.
- **Anything else vessel-specific** for dry cargo: requirements following from the vessel
  type, degassing and venting. The degassing checklist of 8.6.4 is the same kind of model
  and is not registered yet, because there is no degassing operation in the application to
  hang it on.
- ~~**ADN 5.4.1.1.1 (j)**~~ — applied since v1.88.0. Where column (11) of its table A carries
  `ST01`, the consignor certifies in the transport document that the substance was stabilized
  as the IMSBC Code requires for ammonium nitrate fertilizers, and in some States the bulk
  carriage additionally needs the competent authority's approval; both come from 7.1.6.11,
  read on printed page 388. Two UN numbers carry it, 1942 and 2067. UN 2071's `ST02` is a
  condition on the carriage — a trough test — and not on the paper, and is not raised.
- ~~**The tank vessel document of 5.4.1.1.2**~~ — applied since v1.91.0. Its (c) is not the
  ADR's: the description takes the data of **column (5) of table C** —
  `"UN 1203 MOTOR SPIRIT OR GASOLINE OR PETROL, 3 (N2, CMR, F), II, 250 t"` is the composed
  line, after the ADN's own example — and its (h) names the column (20) remarks 3, 17, 22,
  39 (b), 42 and 47, whose text lives in 3.2.3.1 and is not held, so the export says which
  remark asks rather than guessing at what it asks for. Where rows disagree on column (5) or
  table C does not list the substance, nothing is invented.
- **The mixed loading answer is the ADN's own since v1.119.0.** An inland-only consignment
  used to be measured against ADR 7.5.2 — with a note claiming the ADN's own chapter was not
  held, while the distances of 7.1.4.3 had been applied since v1.59.0. The rest of the
  chapter is read now, in the English edition (printed pages 394–399) and the Dutch, which
  agree: **7.1.4.2** (a vessel with class 5.1 in bulk carries nothing else — a finding within
  the consignment, a condition for the rest of the vessel), **7.1.4.10** (the foodstuffs
  precaution, gated by special provision 802 in column (6) of the ADN's own table A — 652
  rows carry it — with the ADN's own separation measures instead of the road's CV28), and
  **7.1.4.4/7.1.4.5** (the container exceptions, on the consignor's `containers_only`
  statement: closed containers outside 7.1.4.3, 2.40 m for other containers, and a
  containers-only vessel may answer the whole prohibition with the IMDG Code's stowage and
  segregation requirements — which this application holds, on the sea side). A combined
  selection gets both answers, each under its own regime's name, and RID+ADN now evaluates
  the rail leg against RID's own table rather than the road's.
- **Placarding of the cargo transport units on board since v1.120.0.** ADN 5.3 addresses
  the containers, road vehicles and wagons that come on board a dry cargo vessel, and the
  kind of unit — which the application cannot see — decides everything: a container is
  placarded for any class, both sides and each end (5.3.1.2); a wagon carrying packages
  likewise, both sides (5.3.1.5.3); a road vehicle carrying packages only for classes 1
  and 7 (5.3.1.5.1/5.3.1.5.2) — except that the note to 5.3.1.5.2 placards it for every
  class when the ADN journey precedes a voyage by sea. So the label models of columns (5)
  and (6) are computed once — with the class 1 aggregation of 5.3.1.1.2 and model 9 in
  place of 9A (5.3.1.1.4) — and the placement rules are given per kind, each under its own
  provision, on the panel and on the ADN placarding sheet. The orange plates of 5.3.2.1.1,
  the numbered plates of 5.3.2.1.2 for portable tanks, the sea-chain alternative of
  5.3.4.1 and the environmentally hazardous mark of 5.3.6 come with it. Not derived, with
  the reason recorded: the elevated temperature mark of 5.3.3 (no carriage temperature is
  told) and the exclusive-use plates of 5.3.2.1.4 (exclusive use is not a field). A cargo
  tank consignment is named as chapter 7.2's — its vessel shows the cones of 7.2.5.0.
- **No ADN certificate and no expert on board.**

**Assessment:** for packaged goods on a dry cargo vessel the exemption, the separation and
the signals are all answered from the ADN's own text, and since v1.63.0 all three are
visible — in the compliance panel and on the document, where until then they were computed
for every consignment and shown to nobody.

**The mode came off the lock in v1.63.0.** It went on in v1.60.0 because inland waterway
answered its separation question with the *road* table and held no cone data at all. Since
v1.66.0 a consignment can say how it travels, which changed what the lock was holding back:
a tank vessel consignment can now be *entered*, and v1.71.0 is what makes entering one
honest. It is admitted or refused on column (8), and everything the application cannot say
about it is named rather than left to be discovered.

## Sea — IMDG

This is the most thoroughly developed part of the application, and the only mode where the
segregation question is genuinely answered.

**Checked:** the 7.2.4 class table; the 7.2.5 segregation groups; the per-substance
segregation provisions of column 16b with the 7.2.3.1 precedence rule applied and both
findings kept visible; the 7.2.6.3 exemption tables, reported but never used to remove a
warning; the 7.2.6.5 class 8 exception; the 7.2.7.1.4 class 1 compatibility matrix with
the ammonium nitrate exception; the LQ and EQ quantity limits of chapters 3.4 and 3.5,
read from the 42-24 Dangerous Goods List and flagged where the ADR value on the line
differs; and the Amendment 42-24 difference layer with its reclassifications flagged
rather than silently applied.

Subsidiary risks count throughout, and a subsidiary class 1 risk is treated as division
1.3, which is stricter than the primary hazard alone.

**Not checked:**

- **Stowage category is shown, not enforced.** Whether a substance may go on deck or under
  deck, and what that means for the rest of the load, is displayed as a category letter and
  left there. **[verify: IMDG 7.1]**
- **CTU packing.** The container/vehicle packing certificate is a set of declarations the
  user ticks. Nothing checks the load against them. The VGM has a real arithmetic
  cross-check, which is more than the certificate gets.
- **Segregation from foodstuffs** is raised as a requirement to verify for the seven codes
  whose target is ordinary cargo, because the application does not know what else is in the
  container. That is the right call and it is worth stating: it is a deliberate
  non-answer, not an oversight.
- **Nothing about the ship.** Stowage plans, the special list or manifest, and every
  provision that depends on the vessel.

**Placarding, since v1.150.0:** chapter 5.3 is derived and reaches paper. The placards
follow the primary hazard with 1.4S excepted and class 1 aggregated to the highest
division; the subsidiary placards of 5.3.1.1.3; the placement rules of 5.3.1.1.4.1 per
kind of unit, because the kind is not something the application can see; the proper
shipping name marking of 5.3.2.0; the UN number in the five cases of 5.3.2.1.1,
including the 4,000 kg arithmetic of 5.3.2.1.1.2, which reports itself as unassessed
rather than as "under the limit" when the mass was not entered; the marine pollutant
mark; and the elevated temperature mark of 5.3.2.2, which turns on a new carriage
temperature field.

**Assessment:** for the segregation of packaged dangerous goods this is solid, tested and
pinned against edits, and since v1.150.0 chapter 5.3 is derived as well. **Sea came off
the modality lock in v1.152.0**, over the same bar as rail and inland waterway: its checks
come out of the IMDG Code itself and the flow is verified end to end in the sea archetypes.
Everything downstream of "may these two travel together" — the stowage the carrier decides,
and the ship — remains out of scope and is said so on the screen.

## Air — IATA DGR

**Checked:** Table 9.3.A segregation including the lithium battery rule, the Q value of
5.0.2.11 (only when M is entered — auto-filled n alone does not start the check), the
Cargo Aircraft Only flag, division 2.3 as forbidden for air carriage, and the requirement
that the IATA packing instruction rather than the ADR one reaches the declaration. The
required-field set for the Shipper's Declaration is the strictest of the five.

**The significant limitation:**

- **The Q value still depends on user-supplied n and M.** EMCargo does not hold IATA's
  quantity tables, so the net quantity and maximum permitted net quantity for the
  applicable packing instruction must be entered manually. Since v1.30.0 the result makes
  this explicit: the API and compliance panel report `checked`, `incomplete`, `exceeded`
  or `not_checked`, and warn when an all-packed-in-one check may apply but the required
  values are absent. This prevents a skipped calculation from looking like approval, but
  it does not replace the missing IATA quantity tables. **[verify: IATA DGR 5.0.2.11 and
  table 4.2]**

**Also absent:**

- **Every automatic quantity limit.** Net per package, per aircraft type, passenger versus
  cargo aircraft. Without the tables EMCargo cannot derive M or compare the shipment
  automatically.
- **State and operator variations.** Not held at all. In practice these decide a great deal
  of what actually flies, and an airline's variation can be stricter than the DGR.
- **Section I versus Section II** for lithium batteries, and the whole of the excepted
  quantity and limited quantity apparatus for air.
- **Overpack declarations, dry ice, radioactive material** beyond what the classification
  supplies.

**Assessment:** the segregation and the declaration are sound. Missing Q input is now
visible, but the quantity side remains incomplete because EMCargo cannot derive the
per-package limits from IATA Table 4.2.

## Gaps ranked by what they cost

Ordered by how much harm someone could take before noticing, not by effort.

| # | Gap | Why it ranks here |
|---|---|---|
| 1 | **IATA quantity limits absent; Q depends on user-entered M** | EMCargo warns when the Q check did not run — since v1.33.0 on the document as well as the screen — but it cannot derive the applicable passenger/cargo-aircraft limit or verify the entered M against Table 4.2. **[verify]** |
| 2 | **The ADN tank vessel regime: the substance is answered, the vessel is not** | Closed for the substance side. Table C is read from three books since v1.80.0 — the UNECE English and French editions and the printed Dutch one — and 677 of its 678 rows are settled on every cell. The application answers the vessel *type* of column (6) and the signals of column (19), admits or refuses the carriage on column (8), and since v1.83.0 hands over the checklist of 8.6.3. What is still absent is the vessel itself: design, tank type, equipment, opening pressure and filling degree are shown as conditions to verify, and the 7.2 operational regime and chapter 9.3 construction are a different discipline. |
| 3 | **Route data absent: which tunnels, and in which category** | Closed for the part that is EMCargo's since v1.50.0 — 8.6.3.2, 8.6.3.3 and the table of 8.6.4 are applied and the load's code reaches the export. What is left is the route itself, which 1.9.5 puts with the carrier, and the tanks/bulk branch of five codes. |
| 4 | **Mixed loading for ADN answered with ADR's 7.5.2** | Closed, and since v1.119.0 closed completely. v1.38.0 read RID's 7.5.2.1 and found it identical to ADR's, footnotes included; v1.41.0 gave rail its own table and its own protective distance. v1.59.0 gave inland waterway ADN 7.1.4.3 — how many metres, not whether — v1.61.0 read column (12) for the cone provisions, v1.64.0 applied the class 1 hold table of 7.1.4.3.4. v1.119.0 read the rest of the chapter: 7.1.4.2 (bulk class 5.1 excludes everything else), 7.1.4.10 (the foodstuffs precaution on special provision 802, in place of the borrowed CV28) and the container exceptions of 7.1.4.4/7.1.4.5 — and the ADR table no longer runs for an inland-only selection at all. |
| 5 | **LQ/EQ conditions not checked** | The arithmetic of 3.4/3.5 is verified correct and 3.5.1.3/3.5.1.4 are applied since v1.50.0, but the mark, the packagings and the 3.5.3 tests are declarations the application cannot see. A line "within the limits" is a candidate, not an exemption — and the panel says so. |
| 6 | **IMDG stowage category shown, not enforced** | Lower because on-deck/under-deck is usually the carrier's call, not the consignor's. **[verify]** |
| 7 | **No marking or placarding checks outside the road mode** | Closed for ADR in v1.57.0 (5.3.1.5, 5.3.2.1 and 5.3.6.1 for packages; the equipment half in v1.53.0), extended to tanks and put on paper in v1.83.0. Closed for inland waterway in v1.120.0: ADN 5.3 is derived per kind of cargo transport unit — the kind the application cannot see, and the kind decides everything (a container placards for any class, a road vehicle only for 1 and 7 except before a sea voyage, a wagon for the goods carried) — and reaches paper as the ADN placarding sheet. Closed for rail in v1.121.0: RID 5.3 is derived under its own rules — package wagons placard for every class, orange plates only via column (20), the orange band of 5.3.5 from the classification code, the shunting marking of 5.3.4 as a named condition — and reaches paper as the RID placarding sheet. Closed for sea in v1.150.0: IMDG 5.3 was read out of the amendment resolution — which replaces the complete text of the Code — and is derived under its own rules, which are not the road's renumbered: a container is placarded on all four sides, the proper shipping name is marked on the unit itself, the UN number rides in the placard or on a panel beside it in the five cases of 5.3.2.1.1 and never for class 1, class 9 is placarded as model 9 where table A gives 9A, and the marine pollutant mark has no land counterpart. It reaches paper as the IMDG placarding sheet. **Air alone still has nothing**, and its chapter is IATA's rather than a UN model's. |
| 8 | ~~The tank hierarchy declines on three of eighteen codes~~ | Closed in v1.94.0. The French volume II — the treaty's other authentic language — was read verbatim on the three cells no two of the first three readings agreed on: it sided with the Dutch on L10BH's group (18 codes), with the German on L10DH's inheritance (the chain runs through L10CH), and with everyone on S10AH's nine codes — the strays of the other readings spell the inheritance sentence (S, G, A, V is SGAV leaking into the cell). **All eighteen codes are settled on every cell.** |

Two of the top gaps from earlier versions of this table are gone, and it is worth being
precise about why. "RID and ADN answered with ADR tables" ranked second for three releases;
it is closed for the exemption calculation, because the texts turned out to be free and
reading them showed that RID prescribes the same arithmetic while ADN prescribes something
else entirely. "The Q check silently not running" ranked first; it now reaches the export.

The pattern that remains is the original one: **the application knows or shows a value but
cannot always act on it.** A displayed value must never be mistaken for a completed
verification.

## What should and should not be built

**Shipped in v1.30.0:**

- **Say when the IATA Q check did not run.** The compliance response and panel expose
  `not_checked` and `incomplete` instead of silently omitting the result.

**Shipped in v1.31.0:**

- **Apply LQ and EQ.** The entered net per inner packaging against column 7a and the E code
  of column 7b, with the 30 kg gross limit of 3.4.2, the 20 kg tray note of 3.4.3, the inner
  and outer limits of table 3.5.1.2 and the 1,000-package cap of 3.5.5. Qualifying is
  reported, never granted.

**Shipped in v1.32.0:**

- **Close the specialist findings from the v1.31.0 review.** Division 2.3 air prohibition;
  Q participation only when M is entered; packing-group row selection with a multi-PG note;
  class 1 net explosive mass; the 8-tonne LQ mark of 3.4.13/14; IMDG 7.2.6.5 beside the
  acid × alkali pair; forbidden substances out of points and document lines; hints filtered
  to active modalities; the inner-packaging field hidden when LQ is 0 and EQ is E0.

**Shipped in v1.49.0 and v1.50.0 — the Dutch ADR read out:**

- **The Dutch proper shipping names.** Column (2) of Table A in the official Dutch edition,
  2,345 UN numbers, read twice from two independently typeset documents and cross-checked
  against each other. There is no open source for that column.
- **ADR 8.6.3, the tunnel restriction code for the whole load**, with 8.6.3.3 leaving
  goods carried under 1.1.3 out of the determination and the table of 8.6.4 turning the
  code into the categories that are barred.
- **ADR 3.5.1.3 and 3.5.1.4**, the two excepted-quantity provisions that can only be seen
  across lines.
- **The eleven rows ADR 2025 added.** UN 0514 and UN 3551–3560 reached the app through the
  IMDG 42-24 layer, and therefore with sea data only — no transport category, no tunnel
  code, no hazard identification number. Copied by hand from the Dutch edition, each row
  read twice.
- **The silent Table A row choice.** Fifteen UN numbers had several rows that the old
  packing-group check could not see, because their rows share one packing group or have
  none. UN 1950 aerosols is twelve rows apart on transport category, tunnel code and
  labels; UN 2037 gas cartridges is nine.
- **Entries with no usable English proper shipping name.** Fourteen empty and one
  truncated in the export; the German name was substituted without a word.
- **The edition the classification table actually is.** Reading the book showed it to be an
  ADR 2023 export while the manifest reported 2025; UN 0514 and UN 3551–3560 are missing
  from it and UN 1499 and 1999 are still in it. The manifest said so from v1.49.0, and
  v1.56.0 closed it: the table is now ADR 2025, read out of the book itself.

**Shipped in v1.33.0 — the land regulations read rather than recalled:**

- **`scripts/read_land_regulations.py`** fetches ADR, RID and ADN from UNECE and OTIF on a
  runner and quotes the provisions the application implements. The premise that these texts
  were unreachable was simply false.
- **Note (a) to 1.1.3.6.3**: the nine UN numbers that count × 20, not × 50.
- **ADN 1.1.3.6.1**: its own exemption, on gross mass with a per-class figure, reported
  separately from the ADR points.
- **RID 1.1.3.6.3/1.1.3.6.4 cited** instead of hedged.
- **The Q status moved into `check_compliance`**, so the export sees it; and a position
  holding two or more substances with no Q input is reported as not checked instead of
  being skipped.

**Shipped in v1.88.0 — 5.4.1.1.1 read in three books at once:**

- **The label models of (c), all of them.** The provision asks for the numbers of column (5)
  with the ones after the first in brackets, and the application printed only the first: a
  separator, `6.1+3` in the 2023 export against `6.1, 3` in the Dutch 2025 edition, left the
  whole cell as one token. 718 of the 3,158 rows carry more than one label model and every
  one of them reached the paper a label short.
- **RID (j)**, the hazard identification number, with 5.3.2.1.1 deciding when.
- **ADN (j)**, the confirmation of stabilisation ST01 asks for.
- **RID 7.5.2.4**, limited quantities beside explosives.
- **One description-line builder** where there were two, and `RID 7.5.2.1` under its own name.

**Worth building next, in this order:**

1. ~~The ADN tank vessel description line (5.4.1.1.2)~~ — shipped in v1.91.0, with the
   column (20) remarks of (h) named beside it.
2. ~~ADN's own stowage regime, the part of 7.5.2 still borrowed~~ — shipped in v1.119.0:
   7.1.4.2, 7.1.4.4/7.1.4.5 and 7.1.4.10 join the 7.1.4.3 that was already applied, and the
   borrowed ADR table no longer runs for an inland-only selection. Rail was already done:
   7.5.2.1, 7.5.2.2, 7.5.2.4 and 7.5.3 are cited to RID.
3. **The rail shunting provisions**, the last thing on this list that is genuinely
   rail-specific and has no counterpart anywhere else in the application. RID 5.3 (wagon
   placarding and the shunting marking of 5.3.4) belongs with it — gap 7's rail half.

**Off the list, checked rather than assumed:** ADR/RID/ADN 5.4.1.1.1 (c) for batteries. The
three texts name UN 3090, 3091, 3480, 3481, 3551 and 3552 and the battery-powered vehicles
3556 to 3558 as entries whose description carries the class number "9" rather than the label
model. All nine are in the 2025 table with class 9 and label model 9A, and the composed line
gives the class — so the provision was already satisfied, which is worth recording as a
reading and not as a coincidence.

**Not worth building, or not buildable here:**

- **IATA quantity tables.** Table 4.2 is copyrighted and is not available as open data.
  EMCargo can accept n and M, do the arithmetic and state clearly when input is missing;
  it cannot safely manufacture the source limits.
- ~~**The IMDG Code's own text.**~~ This entry was wrong, and it is worth saying how.
  The consolidated Code is indeed sold by the IMO — but resolution MSC.556(108), which
  is freely distributed, states that "the complete text of the IMDG Code is replaced by
  the following" and then prints it. So the Code *is* readable, through the instrument
  that adopts it, and has been all along: the Dangerous Goods List was extracted from it
  in v1.48.0 and chapter 5.3 in v1.150.0. What remains unavailable is the consolidated
  publication as a book, which is a different thing from the text.
- **State and operator variations.** These change per airline and per country and would be
  stale within months of shipping.
- **Anything about the vehicle, vessel or aircraft.** Outside what a document preparation
  tool can responsibly claim.

---

*This assessment is maintained up to EMCargo v1.152.0. Between v1.129.0 and
v1.149.0 the work was outside the regulatory checks — the UN-card pipeline, the ZIP
export, in-app updating, user administration, the mail server, password reset,
two-factor authentication and the four-language mail templates — with two exceptions
that are recorded above: v1.149.0 registered the December 2025 corrigenda to IMDG
Amendment 42-24 and verified that none of its eleven corrections touches an extracted
value, v1.150.0 closed the sea half of gap 7, and v1.152.0 took sea off the modality lock. The sections above name the release
each finding shipped in. v1.42.0 to v1.48.0 touched the goods
catalogue, the interface language, the settings, the documentation and the error messages,
not a single regulatory check; v1.49.0 and v1.50.0 changed the ADR side, from the Dutch
edition of the book. It is guidance for development, not a compliance statement. Every document the application produces is a draft; see
[DISCLAIMER.md](../DISCLAIMER.md).*
