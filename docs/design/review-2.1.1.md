# EMCargo 2.1.1 mobile goods review

Review date: 8 September 2026. Scope: the goods-entry follow-up on
`agent/release-v2.1.1`, based on commit
`1875478f88c2d92dea33d77e07b3955886e15326`.

The user rejected the density of the 2.1.0 mobile goods screen. Their petrol
example exposed a weakness in the previous review: ordinary steel goods did
not exercise the additional substance-decision information. This review uses
the confirmed and unanswered `Benzine 25L` case as primary evidence.

An independent review agent inspected the application diff, regression tests
and actual browser screenshots. It did not implement the application changes.
The score is an expert assessment of this goods-entry surface, not a user
study, accessibility certification or a new score for the entire application.

## Assessment

**8.3/10 for the reviewed goods-entry experience: accepted.** The first visual
pass was reopened when a desktop restoration check exposed a calculation
precision defect. The final assessment follows its correction, regression
inspection and successful browser restoration. No unresolved blocker found in
this review remains. The surrounding wizard and expanded detail forms are
outside this focused score and have not been reassessed as a whole.

| Criterion | Weight | Score | Basis |
| --- | ---: | ---: | --- |
| Visual hierarchy | 35% | 8.5 | Flat separated rows replace nested cards. A confirmed petrol line shows one total and one UN identity, with no repeated success badge or per-piece weight. Import is one secondary entry beside the heading. |
| Task ease | 25% | 8.1 | Quantity and unit remain directly editable. Details has a visible text label. Import retains named file, paste and template options; append/replace choices remain explicit. Opening import and revising an answered substance now each cost an additional disclosure action. |
| Narrow-screen usability | 20% | 8.0 | The 355px and 390px layouts retain readable controls and fit without horizontal page overflow. All unanswered substance choices can be brought above the footer. The surrounding wizard header remains tall, and expanded details remain lengthy. |
| Exceptions and decision handling | 20% | 8.5 | Unanswered substance questions, stale results and actionable errors remain visible without opening Details. Candidate rejection keeps its original meaning. Multiple UN candidates include their names for touch users. Cancellation invalidates late import responses. |

## Changes and review corrections

The default row presents the description, quantity, unit and total weight.
Ordinary derived facts, dimensions and manual corrections are available through
Details. A confirmed UN number remains visible on the collapsed row; Details
contains the original answer and the action to revise it. Removing the green
`OK` badge also avoids placing an unexplained success signal beside a dangerous
substance.

Only an exception or an unanswered substance question adds explanatory text to
the collapsed row. The three substance answers are preserved: accept the UN
candidate, identify a different substance, or reject the suggestion. Rejection
does not declare the goods non-dangerous. Where there are several candidates,
their names are visible rather than available only through a hover tooltip.

The main goods surface has one Import action. Its native modal dialog keeps
file selection, pasted text, the template and mapping decisions together.
Recognized files can still populate an empty shipment directly. A populated
shipment retains the choice between appending and replacing its lines.

| Review finding | Resolution and evidence |
| --- | --- |
| The first unanswered screenshot did not show all answer choices above the sticky footer. | A second 355px capture shows all three choices and the rejection explanation after scrolling. The report uses that complete state as evidence. |
| A dropped file initially parsed while the list remained editable and no modal progress was visible. An empty-list request could therefore finish after new manual entry and replace it. | File parsing now opens the modal immediately, including on drop. Busy state prevents parallel editing. A deferred-response regression checks that cancellation prevents the late result from applying. |
| Long wizard step labels forced excess width on the narrow layout. | Mobile labels are shortened in all four languages and the header grid permits its children to shrink. The measured document widths match their scroll widths. |
| Multiple UN candidates previously exposed their names only in a tooltip. | Each candidate now includes visible supporting name text. A regression checks both distinct substance names. |
| Restoring a two-package petrol shipment changed its total from 37.25kg to 37.24kg. Calculated per-piece and total weights were both sent back as overrides; the backend multiplied the rounded 18.62kg per-piece value. | Recalculation now sends the saved total alone when available, with a per-piece-only fallback. This preserves historical manual totals without guessing whether a stored result was computed or entered. Three restoration/request regressions cover computed petrol, a manual 41.13kg total and a per-piece-only value. A real browser restore retained two packages, UN 1203 and 37.25kg. |
| Long DG document names collided with their status text in the desktop shipment summary. | The document name and status now occupy separate grid rows. Refreshed desktop screenshots show both remaining readable. |

The simplification deliberately trades one additional import-entry tap for a
quieter everyday screen. Revising a completed substance answer uses
Details → Change answer. Frequent quantity edits still require no dialog, and
unanswered safety questions remain directly actionable.

## Visual evidence

These are actual application screenshots using synthetic goods and a real
development backend. The surrounding gray area and controls belong to the
responsive review harness. Its iframe provides a CSS layout viewport; it is
not a physical phone or native mobile-browser emulation. The earlier
`emcargo211-petrol-390.jpg` capture retains a 355px harness caption after switching
width; the document measurements below establish its actual layout width. The
harness now updates its caption when selecting a width.

| Evidence | Observation |
| --- | --- |
| [Confirmed petrol, 355px](2.1.1/emcargo211-petrol-355.jpg) | One `18,62 kg` total, one `UN 1203` identity, direct quantity/unit fields, text Details action and compact footer. |
| [Confirmed petrol, 390px](2.1.1/emcargo211-petrol-390.jpg) | The same hierarchy remains usable in the wider phone viewport. |
| [Unanswered petrol, 355px](2.1.1/emcargo211-unanswered-355.jpg) | All three decisions and the warning about rejection are visible above the footer after scrolling. |
| [Expanded details, 390px](2.1.1/emcargo211-details-390.jpg) | Manual weights and substance fields remain available with the confirmed UN identity retained. The detail form is still dense and scrolls. |
| [Import dialog, 390px](2.1.1/emcargo211-import-390.jpg) | Named file and paste paths, template link, and distinct replace/append actions fit in the modal. Empty input leaves import actions disabled. |
| [Multiple goods, 390px](2.1.1/emcargo211-multiple-390.jpg) | Stable row numbering, repeated column positions and simple separators support scanning mixed goods. This capture shows part of the five-row list. |
| [Attention filter, 390px](2.1.1/emcargo211-attention-390.jpg) | The filter isolates the fifth row and displays the missing-weight/dimensions explanation without opening Details. |
| [Desktop after restoration](2.1.1/emcargo211-restored-desktop.jpg) | Two petrol packages retain 37.25kg and UN 1203 after reopening. The five-line shipment total remains 319.75kg, and long document names no longer overlap their statuses. |

The browser measurements reported for the 355px iframe were document
`clientWidth = 340` and `scrollWidth = 340`. At 390px they were both 375px.
The 15px difference comes from the iframe's native scrollbar. These checks
establish the absence of horizontal document overflow in the exercised states;
they do not establish every possible content length or text-zoom setting.

## Functional evidence

The following browser actions were reported by the implementation agent and
are consistent with the reviewed code and screenshots. The independent
reviewer inspected the screenshots and code; it did not separately repeat the
interactive browser sequence.

| Check | Result available at review time |
| --- | --- |
| Full frontend regression suite | 370 tests passed across 48 files. |
| Production frontend build | Passed. |
| Direct petrol quantity correction | Changing quantity from one to two produced `37,25 kg` and preserved `UN 1203`. The displayed one-package `18,62 kg` value is rounded; the backend calculation retains greater precision. |
| Browser restoration after the precision correction | Reopening `/wizard/road` retained quantity two, UN 1203, 37.25kg for petrol and a 319.75kg shipment total. |
| Saved-weight restoration regressions | Recalculation sends only the authoritative total for both computed 37.25kg and manually corrected 41.13kg results. A 12.5kg per-piece-only result retains its fallback. |
| Import append | Four imported rows were appended to the existing petrol line, producing five rows without losing its confirmed UN identity. |
| Attention filter | Five rows reduced to the one requiring attention; its actionable error remained visible outside Details. |
| Import keyboard cancellation | Escape closed the native dialog and returned focus to its Import trigger. |
| Import cancellation regression | Cancelling a selected or dropped file prevents a late parse response from changing the goods. |
| Goods regression checks | Direct editing, derived fields behind Details, single confirmed-UN presentation, revisable decisions, visible errors, stale results and named multiple candidates are covered. |

The backend was not changed by this focused UI follow-up. This review does not
claim a new full backend suite run, regulatory certification or complete export
validation. The prior release's broader backend evidence is recorded
separately in [the 2.1.0 review](review-2.1.0.md).

## Limits and release boundary

The tall shipment header and dense expanded detail fields remain opportunities
for a later flow redesign. The repeated quantity/unit labels help narrow-screen
reading but still add vertical height in a long list. Neither tradeoff is hidden
by the score.

Physical Android/iOS devices, software-keyboard layout, screen-reader behavior,
large text zoom, every language and every import-file mapping variant were not
all exercised in this browser review. Existing regression coverage remains
useful but is not a substitute for those checks.

At the time of this review, final remote CI, merging, the GitHub release and
GHCR publication had not yet been verified. This document records acceptance
of the local candidate and must not be read as evidence that publication has
completed.
