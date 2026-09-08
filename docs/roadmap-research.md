# Roadmap research

> Historical design/research notes. For the current interface and setup, use the
> [user guide](user-guide.md), [configuration](configuration.md) and
> [design verification notes](design/README.md).

*Groundwork for the items on the [roadmap](../ROADMAP.md) — deliberately not a plan.
Each section records what was found out about a subject before anyone commits to
building it: what the market does, what the regulation says (measured where it could
be), what already exists in this repository, and which questions a future plan has to
answer. Verified facts are cited; anything not yet verified says so.*

*Researched August 2026. Market claims age; regulation quotes carry their source.*

---

## Package marks and labels (new)

**The idea.** EMCargo refuses to print placards, and rightly — a laser print is not
a placard. The marks and labels **on the package** of chapter 5.2 are different: they
are routinely printed on A4 sticker sheets in practice, and the application already
knows per substance which label models and marks apply. This is the clearest gap
against the commercial tools (Labelmaster, DGOffice and Brady all sell label printing).

**Measured from ADR 2025** (`read_land_regulations.py`, volume II pages 237–252 and
volume I page 664):

| Mark | Provision | Measured requirement |
|---|---|---|
| Class/division label | 5.2.2.2.1.1 | Diamond 100 × 100 mm minimum, inner line ~5 mm from the edge; reducible proportionally if the package size so requires; cylinders per ISO 7225 |
| Limited quantities mark | 3.4.7 | Diamond 100 × 100 mm, line 2 mm; reducible to 50 × 50 mm with a 1 mm line |
| Environmentally hazardous mark | 5.2.1.8.3 | Diamond 100 × 100 mm, line 2 mm, fish-and-tree black on white; reducible if the package so requires |
| Battery mark | 5.2.1.9 | Rectangle 100 × 100 mm minimum with 5 mm red hatched edging, UN number(s) under the symbol |
| Orientation arrows | 5.2.1.10 | Two opposite vertical sides, arrows per the figure or ISO 780:1997; a measured list of exemptions (pressure receptacles, inners ≤ 120 ml with absorbent, hermetic inners ≤ 500 ml, …) |

**Still to measure at build time:** 5.2.1.1 (the UN number and PSN marking on the
package, including the character-height rule tied to package size) — the quote run
missed it and nothing here should be built from memory. The IMDG and RID/ADN
counterparts of each mark must be read as well; the sea chapter is readable since
v1.150.0.

**What a plan must settle:** true-size rendering on A4 (two 100 × 100 diamonds per
sheet with cut marks, or standard die-cut sticker formats); whether the sheet prints
labels *only* where the check says they apply (it should — a sheet of unneeded labels
invites mislabelling); and the same honesty note the placarding sheet carries, since
5.2.2.1.6 also has visibility/durability demands paper cannot promise.

## Structured export, eCMR and eFTI (new)

**The regulatory wave, verified against multiple sources:** the EU
[eFTI Regulation](https://transport.ec.europa.eu/transport-themes/logistics-and-multimodal-transport/efti-regulation_en)
applies in full from **9 July 2027** — from then, authorities must accept freight
information electronically via certified eFTI platforms. The certification framework
is being finalised through 2026, [Spain mandates digital consignment notes from
October 2026](https://trans.info/en/ecmr-in-2026-434860), and
[39 countries have acceded to the eCMR protocol](https://www.transbook.onl/Transbook/Digitalization)
while under 1 % of European road shipments actually use it yet. Paper remains legal —
consignors are not obliged to switch.

**The technical anchor:** the eFTI data set is built on the **UN/CEFACT Multi-Modal
Transport reference data model (MMT-RDM)**, and eCMR is being aligned to it
([eFTI4ALL](https://efti4all.eu/odette-2025-ecmr-efti-fit-together/)). That is the
model to map EMCargo's fields against — once, in a document, before any code.

**What EMCargo should and should not become:** not an eFTI platform (that is a
certification regime for platform providers), but a system whose every shipment can
leave as structured data so that a certified platform, or a plugin talking to one, can
take it from there. The per-party signature flow (consignor, carrier, consignee — the
application already stores one signature per user) is the second half; qualified
electronic signatures are a legal-weight question for the plan.

**First concrete step when planned:** a versioned JSON export of a complete shipment
(values + lines + dangerous goods + derived findings), documented as an API response.
Everything else — MMT-RDM mapping, eCMR pilots, platform connectors — builds on that.

**Shipped:** the export in v1.161.0; the mapping in v1.185.0, read from the Annex of
Commission Delegated Regulation (EU) 2024/2024 (the eFTI common data set and the subsets
per provision, supplied as the Official Journal PDF in the reference folder) rather than
from the MMT-RDM itself — the regulation adopted a profile of that model, and the profile
is what a platform speaks. See [The eFTI mapping](efti-mapping.md) for the numbers: the
dangerous goods subsets are answered for the substance data and the derived findings,
the road subset is not answered for the address elements, because the application holds
an address as one block of text.

## DGSA annual report (new)

ADR 1.8.3 obliges every undertaking that consigns or carries dangerous goods to
appoint a safety adviser, and 1.8.3.3 obliges that adviser to produce an **annual
report**, kept five years ([overview](https://app.croneri.co.uk/feature-articles/dangerous-goods-safety-adviser-dgsa-requirements),
[EASA template](https://www.badgp.org/dgsa-annual-report)). The report's statistical
half — what was shipped, which classes, which quantities, which incidents — is exactly
what a shipments store can aggregate.

**Dependency, hard:** this requires the shipments page and therefore the history.
Without stored shipments there is nothing to report. **Shipped in v1.177.0** on that
basis: the counts EMCargo can prove (shipments per month, mode, regulation,
department, class and UN number, kilograms and litres apart, the 1.1.3.6 outcome per
shipment, the documents issued) as a page and a workbook, and the adviser's duties of
1.8.3.3 — read in the official Dutch edition — as headings with nothing filled in. The
BADGP and UNECE sites were not reachable from the build environment when it was made,
so v1.177.0 followed the paragraph itself. **v1.179.0** then took the DVSA's own
template (*DGSA Annual Report for the Carriage of Dangerous Goods*, December 2025,
supplied by the project owner) as the outline: its sections and question wording are
reused under the Open Government Licence, the UK-specific bodies are written as "the
competent authority", the counted parts (transport table in tonnage bands, method of
carriage, high consequence goods, tonnage) are proposed from the history and never
asserted, and the adviser's answers are kept per year. A generated opinion would still
be worse than a blank, and the blank is still the deliberate part.

## Own articles library (new)

DGOffice links a company's own article codes to UN numbers so one code fills the whole
document. EMCargo holds the pieces already: the goods catalogue (1,093 goods), the
equipment library, and per-substance classification. The missing layer is
*"our article X = UN 1263, PG II, technical name Y, default packaging Z"* — entered
once, reused every shipment. Same restriction-level gating as the address book, and
worth designing together with it: both are "master data the office reuses".

## EDI and the port call (new)

[Hazcheck](https://hazcheck.com/product/hazcheck-workstation/) produces a Dangerous
Goods Note and attaches an EDI message so the shipping line re-keys nothing. The
message standard is **UN/EDIFACT IFTDGN** (dangerous goods notification), publicly
specified by [UNECE](https://service.unece.org/trade/untdid/d16a/trmd/iftdgn_c.htm)
and used by port community systems. Far off, and only worth doing against a real
counterparty — but the structured export above is deliberately its first half, and
the IFTDGN spec is free, so nothing blocks reading it early.

## Groupage, returns, QR (new, smaller)

- **Groupage** (shipped v1.169.0). Everything did exist per consignment; the missing
  thing was the level above, and building it needed no new regulatory logic — the three
  provisions were always measuring "what is on the transport unit", so they are handed
  the union of the entries and answer correctly. The open design question (trip as
  entity or transient calculation) was not a matter of taste: an installation without a
  shipment history stores nothing about shipments, so a stored trip would break that
  promise for the sake of a screen. It is transient today, and a test asserts the
  service touches no database. An installation *with* a history reopens the question,
  and the roadmap records it as open for that phase rather than settled.

  **What the research missed, and the reading found.** ADR 3.4.13/3.4.14 carry *three*
  quantities and the consignment-level check had run two of them together:

  | value | what it is | what it does |
  |---|---|---|
  | 12 t | maximum mass of the **transport unit** | triggers the requirement (3.4.13) |
  | 8 t | gross mass of the **LQ packages** | allows it to be dispensed with (3.4.14) |
  | orange plates (5.3.2) | a property of the **whole load** | an exception in its own right |

  The check compared the LQ mass to 8 t and called that the 3.4.13 requirement, which
  attributes the dispensation's threshold to the requirement and drops the orange-plate
  exception entirely. In groupage that exception is the common case: add one full-ADR
  consignment and the unit carries plates anyway, and then the LQ mark is not required.
  Read from ADR 2025 Volume I page 665 (workflow run 32826513665) rather than assumed.
- **Return shipments** (shipped v1.167.0). This note said "no research needed", which
  was true of the description — `empty_uncleaned` and 5.4.1.1.6.1 have been built since
  v1.90.0 — and was not true of the points. ADR **1.1.3.6.1** reassigns an empty
  uncleaned packaging to transport category 4, whose factor is 0, and the check was
  reading the substance's own category: one empty drum of a packing group II liquid came
  to 900 of the 1000. Fixed in v1.166.0 before the button was built on top of it. The
  lesson worth keeping: "no research needed" is a claim about one half of a feature, and
  the half it is not about is where the regulation hides.
- **QR code on documents** (shipped v1.168.0). Self-contained, no third party, as
  expected. The open question — link lifetime on an installation that deliberately
  stores nothing — dissolved rather than being answered: it assumed the link would
  address a *shipment*. It addresses UN numbers, which is what makes the page safe to
  serve without a sign-in and is also why nothing about it expires. The regulation does
  not go stale the way a stored job would.

  What did need deciding was smaller and more physical. A QR is read by its module, the
  single square, and one UN number encodes to a 33-module symbol while thirty need 57 —
  so a fixed printed size makes the squares shrink exactly on the documents that carry
  the most substances, which are the ones somebody most needs to scan. The module size
  is fixed instead (0.62 mm) and the printed size follows from the encoded module count,
  measured across the full range one link can carry: 25 mm for one UN number, 40 mm for
  thirty, with the modules holding at 0.62 mm throughout. Error correction sits at level
  M rather than the library's default L: a code that lives in a cab and a warehouse
  should survive being smudged.

  **Not assessed:** the published minimum module size for a printed symbol. GS1's
  General Specifications are the obvious source and every GS1 domain is unreachable from
  the build environment, so 0.62 mm is a chosen number — roughly fifteen dots across a
  module on a 600 dpi laser — and not a measured one. It is one constant
  (`CARD_QR_MODULE_MM`) if a real specification is ever read.

## Route planner (existing item, deepened)

Self-hostable open-source engines exist with dangerous-goods awareness:
[openrouteservice](https://github.com/giscience/openrouteservice) evaluates **tunnel
categories B–E** through a `hazmat` flag on its HGV profile, and
[GraphHopper's custom models](https://www.graphhopper.com/blog/2020/05/31/examples-for-customizable-routing/)
can exclude `hazmat=no` roads and `hazmat_tunnel` categories. Both run from
OpenStreetMap data.

**The honest caveat, from the same sources:** hazmat tagging in OSM — especially
`hazmat_tunnel` — is sparse. A route that *silently* misses an untagged tunnel is the
half-right-document problem in map form. A plan must treat OSM coverage measurement
(for the operator's actual region) as step one, and the module's output as advisory
with the tunnel code of the load printed beside it — the code EMCargo already
derives. ADR 1.9.5 keeps route choice with the carrier; the module plans, it does not
authorise.

## Container handling in 3D (existing item, deepened)

Open-source foundations exist: [xflp](https://github.com/hschneid/xflp) (Java) solves
truck loading with real-world constraints **including permissible axle load**;
[3DContainerPacking](https://github.com/davidmchapman/3DContainerPacking) (C#)
implements the EB-AFIT algorithm; Python implementations exist but are thinner. The
commercial benchmark ([EasyCargo](https://www.easycargo3d.com/en/),
[3DPACK.ING](https://3dpack.ing/)) draws the **centre of gravity live** and accounts
for weight in placement.

**What nobody in that market has:** segregation. EMCargo derives IMDG/ADR
segregation per pair of substances; drawing it spatially (these two drums may not
share this container, that one must be 2.4 m away) is the differentiator. **When
planned:** decide build-vs-wrap (a TS/WebGL front over an own solver, versus porting
xflp's constraint model), and take axle load and CoG in from day one — they pair with
the VGM the application already computes.

## Container fleet management (existing item, deepened)

The depot/M&R world ([MRI Intermodal](https://www.mriintermodal.com/solutions/depot-management-software/),
[WHIZTEC](https://www.whiztec.com/container-depot-software/)) is built around:
gate-in/gate-out with **EIR** (equipment interchange receipt, photos, damage remarks),
damage estimates against customer tariffs, M&R workflow (estimate → approval → work
order → QC → billing), stack/yard planning, and **CODECO** EDI reporting to lines.
For a park owner rather than a depot operator the useful core is smaller: which box,
where, in what condition, inspection dates (CSC plate), and hand-over evidence.
**Open question for the plan:** who is the user — own park, or depot service for
third parties? The second pulls in tariffs and billing, which is a different product.

## Vessel design (existing item, noted)

The thinnest-researched module, deliberately: naval architecture tooling (hydrostatics,
stability) is a specialist field with certification implications, and nothing in the
documentation-tool DNA transfers. If it proceeds, scope it first to *data* the other
modules need (hold dimensions, tank layouts as input to stowage) rather than to design
calculations that would carry liability.

## Military module MOD-NL (existing item, boundary noted)

Kept out of the public core and off the public hub, as the roadmap says. Groundwork
consists of exactly one public observation: cross-border military movements use forms
that are themselves standardised (e.g. the EU/NATO customs **Form 302**), so the
module's shape — official forms, filled — matches the civilian core's. Anything beyond
that is not for this repository.

## Two modes, the shipment history and the shipments page (existing item, internal groundwork)

No web research applies; the groundwork is in this repository. A `Job` table already
exists in the schema and is **deliberately purged at startup** (`purge_sensitive_data`
in `backend/app/core/startup.py`) — the stateless promise of
[Privacy](privacy.md) is enforced in code, not just described. That is the switch the
history feature would flip. Order of operations is fixed by principle: mode first,
storage second, page third — there must never exist a version that stores without the
control. Departments imply a user–department relation and per-department visibility
filters; both belong in the same design round.

**The shape is settled** (see [the roadmap](../ROADMAP.md)): two modes, Open and
Organisation, and within Organisation one feature, the shipment history. It was first
written as three "privacy levels" on one ladder and restated in v1.170.2, because the
ladder made a history sound like a step down in privacy when it is a function an
organisation switches on for itself. What follows is what each piece costs to build.

*Two axes, not one.* Authentication (none / required) and retention (nothing /
shipments) give four combinations, of which three are offered and the fourth —
anonymous with a history — is refused, because it records what was shipped without
recording who entered it.

*Open removes rather than adds.* No accounts means the auth router, the user page, the
password-reset flow, the second factor and the welcome mail are not merely hidden but
absent, and the tests must assert their absence rather than a redirect. Three further
consequences, each traceable to a file already in the tree:

- Per-user settings move to `localStorage`, including the signature — today the only
  image the server holds (`docs/privacy.md`). The settings screen needs a second copy
  that says where the data is, in four languages.
- The equipment library goes: it is imported by an administrator, and there is none.
- The update check already runs only for a signed-in administrator, and the assistant's
  model download is already an administrator's click — so both become environment
  variables at Open rather than losing a feature.

*Mail does not exist at Open.* An earlier version of this note kept mail at Open behind
a second setting — "may a stranger make this installation send" — with per-recipient
caps and a single recipient per send, all of it to keep a public installation from
becoming a spam relay. v1.170.2 removed the feature instead of guarding it: a visitor
who can download the documents does not need the installation to send them, and
without the send action there is no mail server to configure and nothing to cap. The
`SMTP_*` environment settings of v1.141.0 stay what they are, for Organisation
installations that would rather configure mail in the environment than in the screen.

*Rate limiting is half-built, and the existing half is the wrong half.* `slowapi` is a
dependency and `app.state.limiter` is wired up in `main.py`, but all six
`@limiter.limit` decorators are on authentication routes (`api/routes/auth.py`) — the
routes Open deletes. The endpoints that cost real money at Open are unprotected
today precisely because a login stands in front of them: document generation, the
assistant's inference, and the Photon proxy.

*The live defect underneath it was fixed in v1.163.4* and no longer waits on the modes.
`slowapi.util.get_remote_address` returned `request.client.host` and never consulted
`X-Forwarded-For`, so behind any reverse proxy all callers collapsed into one bucket —
an organisation of fifteen people sharing ten sign-in attempts a minute. `client_address`
in `app/core/ratelimit.py` now counts one entry from the right per proxy in
`TRUSTED_PROXY_COUNT`, because a proxy appends and everything further left is the
caller's own writing.

*And the trap that fix walked into is worth keeping in mind for the rest of this work.*
There were **two** `Limiter` instances: one in `main.py` on `app.state`, and one in
`api/routes/auth.py` carrying all six decorators. Only the second enforced anything, so
re-keying the first was a no-op — and a unit test of the key function passes either way.
It was caught by driving a real request through the stack and reading the key back out
of slowapi's own warning line. There is one limiter now, in `app/core/ratelimit.py`, and
a test that sweeps the source for a second one. When the limits are extended to document
generation, the assistant and the Photon proxy, they go on that limiter.

*The downgrade tension is real and has one honest answer.* The level is a deploy-time
variable, so 3 → 2 cannot ask for confirmation on a screen. Startup refusal is the
resolution: report the count of stored shipments, name the second variable that
authorises discarding them, and exit non-zero. Loud, non-destructive by default, and it
cannot be reached by accident.

## Toasts and snackbars (existing item, options)

Current mix: inline notices, banners and cards. The React ecosystem's mature options
are `sonner` and `react-hot-toast` (both small, both a11y-conscious); either fits the
stack. The real work is not the library but the sweep: one inventory of every current
notice with a decision — toast, inline (validation belongs at the field), or gone.
Low risk, high visible payoff, no dependencies on anything else.

## Branding (existing item, small design note)

Logo, name, and the transport-mode images as admin uploads. Two things the plan must
not forget: the **mail templates** embed the logo as CID attachment
(`backend/app/services/mail_templates.py`) and must pick up the custom one; and
uploaded images are user content — size caps and format checks at the upload edge,
plus a "reset to default". The four-language interface strings stay; branding does
not mean re-wording.

## Plugins, licence, community hub (existing items, model found)

The pattern to copy is **[HACS](https://hacs.xyz/)** (Home Assistant Community
Store): community code lives in the authors' own GitHub repositories, the store
indexes them, the app installs from the index, and the curated core stays separate.
That model gives EMCargo: a hub website that is an *index*, not a file host;
admin-only install (already the stated intent); and a natural quality boundary
(regulatory checks stay in core — a plugin must not be able to silently alter what a
document claims, which should be written down as a hard rule in the plugin API design).

**Licence:** Apache 2.0 already permits writing, sharing and installing plugins
freely. The switch to MIT is presentational; the one substantive difference is that
Apache 2.0 carries an explicit patent grant that MIT lacks — worth knowing before
giving it up. No blocker either way.

**Technical shape to evaluate in the plan:** backend plugins as Python entry points
with a declared, versioned API surface; frontend extension points (a route + a menu
slot) rather than arbitrary code injection; a manifest per plugin (name, version,
permissions, core-version compatibility) mirroring HACS.

## Installing without Docker (existing item, routes)

Three routes, in order of reach: a **systemd service** installed by script or native
package (nfpm/fpm build `.deb`/`.rpm` from one spec — to be verified when planned), a
**Helm chart** for Kubernetes, and Docker unchanged. Groundwork observations from
this repository: the backend is a single uvicorn process with `/data` as its one
stateful path, which makes a unit file trivial — but the **in-app updater and the
entrypoint's socket handling are Docker-specific**, and the settings screen must show
the update route that matches the installation method (it already does this for
socket-less Docker). The Python version pin (image ships 3.12) becomes the distro
compatibility question.

## Air, and the one legitimate road to it (existing item, new finding)

The IATA DGR remains unreadable as text. But IATA now sells the *service* rather than
only the book: [DG AutoCheck](https://www.iata.org/en/services/compliance/dg-autocheck)
validates a Shipper's Declaration against the DGR, and its
[Connect API](https://www.iata.org/en/services/compliance/dg-autocheck/dg-autocheck-connect-api/)
exists precisely to let other systems submit and retrieve checks;
[DG Digital](https://www.iata.org/en/pressroom/2026-releases/2026-03-12-01/) (launched
March 2026) digitalises the DGD end-to-end. **This reframes the air unlock:** instead
of needing Table 4.2 as data, EMCargo could hand the declaration to IATA's own
checker through a paid, operator-supplied API key — the measured-source principle kept,
because the source is IATA itself. To investigate when air is planned: licensing
terms, cost, offline behaviour (an air-gapped installation cannot call out — the
existing outbound-connections switch already models this).

## NHM codes (unblocked, shipped in v1.184.0)

The source turned out to be the UIC's own correspondence table between the NHM 2025 and
Eurostat's NST 2007, supplied by the project owner as a workbook: every NHM 2025 position
with its English and French label and the NST group it maps to. `scripts/build_nhm_seed.py`
cuts it to one entry per six-digit code — 5,612 Harmonized System subheadings and 28
railway-specific positions of chapter 99 — and box 24 of the CIM is picked from that list
by code prefix or by a word of either label. Labels exist in the two languages the UIC
publishes; the interface says so rather than translating them. `scripts/probe_nhm_sources.py`
stays as the measuring tool for a next edition.

---

*Nothing in this document commits to building anything. When an item is picked up, its
section here is the starting brief; the first act of any plan is to re-verify the
external claims, which carry their dates and sources for exactly that reason.*
