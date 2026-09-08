# EMCargo 2.1.0 design and functional review

Review date: 8 September 2026. Scope: the 2.1.0 candidate on
`agent/release-v2.1.0`, based on main commit
`c94bf69563b69f9e5d9cdb8fe318a72439d39c0f`.

An independent review agent inspected the implementation and actual browser
screenshots, reported defects to the implementation agents, and reviewed their
corrections. It did not author the application changes. This is an automated
expert assessment, not a user study or an accessibility certification.

## Assessment

**8.1/10: the reviewed candidate meets the design review threshold.** The
unrounded weighted score is 8.065. Acceptance requires at least 8 overall, no
criterion below 7, reliability of at least 8, and no unresolved blocker found
within this review's scope.

| Criterion | Weight | Score | Assessment |
| --- | ---: | ---: | --- |
| Visual coherence | 25% | 8.2 | Consistent charcoal surfaces, restrained blue accents, clear spacing and aligned goods fields. The interface is calmer and more legible. Some older detail panels retain denser nesting, and the icon treatment is not entirely uniform. |
| Task ease | 25% | 8.1 | Four usable transport choices, direct paste entry, visible draft recovery, persistent wizard actions, document readiness and searchable navigation shorten common paths. Long form explanations and some duplicate summary information remain. |
| Responsive layout and accessibility | 20% | 7.8 | The corrected phone goods form and tablet chooser fit their viewports. Mobile users can reach the shipment summary. Labels, visible focus, native dialog semantics and practical control sizes improve access. Physical device, screen reader and comprehensive contrast testing were outside this review. |
| Motion | 10% | 7.5 | Short page, row, drawer and dialog transitions have a clear purpose; reduced-motion preferences disable them. This score is supported by code inspection, not frame timing measurements or a recorded animation review. |
| Reliability | 20% | 8.4 | Broad regression coverage, an actual browser calculation/export flow and targeted privacy, query, date and quantity checks support confidence. Download artifact capture and production deployment were not verified in this review environment. |

The score is specific to the inspected candidate and evidence below. It does
not imply that every administration screen or every regulatory scenario has
been exercised in a browser.

## Review loop and corrections

The first iteration was not accepted. The desktop direction was sound, but
responsive defects and a subsequently discovered parser defect required
correction. A late browser resume check reopened the review when it exposed a
restoration defect. The final pass below follows its correction, independent
code and regression-test inspection, and two successful browser restoration
checks. No blocker found in this review remains unresolved.

| Finding | Correction and verification |
| --- | --- |
| The chooser's privacy copy claimed no server history while history was enabled. | Copy now follows the installation's history setting. |
| Goods columns did not align consistently with their labels. | Explicit grid classes replaced fragile positional styling; the final desktop screenshot shows aligned description, quantity, unit and weight fields. |
| CSS specificity reduced the phone quantity field to a 24px column; the unit field could extend beyond its column. | Corrected container rules give the fields predictable widths. The quantity column was subsequently enlarged to 72px for multi-digit values. |
| The phone goods screen scrolled horizontally and cut off an import action. | The import wrapper now has a bounded width, allowing its existing wrapping toolbar to work. The replacement screenshot has no horizontal scrollbar. |
| The tablet chooser retained a 270px side panel beside a constrained mode list. | The import panel stacks below the mode list at this width. A real 768px application viewport confirms the resulting layout. |
| Enter in the command dialog could reopen it after focus returned to its trigger. | The selection handler prevents Enter's default action; the keyboard regression test covers the interaction. |
| New pages could retain the scroll position of a previous long form. | Layout resets scroll on pathname changes, without resetting it for in-page field edits. A regression test covers the route boundary. |
| A colleague or administrator could access another person's private draft through its id. | Draft access now requires its author on detail, update, export, document and delete routes. Kept shipments retain their normal department sharing rules. |
| Completing a private draft after changing departments initially shared it with the former department and locked its author out. | Only the first draft-to-kept transition takes the author's current department. Tests cover the author, old and new colleagues, a move to no department, and unchanged scope for previously kept shipments. |
| The new combined quantity regex backtracked over overlapping whitespace groups. A 1KB invalid field took about one second in the review reproduction. | Number and unit parsing are separated, and raw text is bounded at 256 characters before scanning. Independent rechecks rejected 100, 1,000 and 10,000 spaces in approximately 0.013, 0.0025 and 0.0018ms respectively. These are diagnostic observations, not performance guarantees. |
| A late resume check opened an empty wizard despite a stored draft. Effect cleanup cancelled the response after its ref had already marked restoration as completed; registry loading could also cancel kept-shipment restoration. | One restoration lifecycle now waits for preferences and the registry, marks completion only after applying a valid response, and blocks editing, calculation and autosave while pending. Failed reads offer retry instead of treating an unseen draft as empty. Seven integration regressions cover StrictMode, deferred registry/shipment responses, slow or failed reads with prefill, retries, transport-mode changes and history-disabled operation. Two real browser restore checks preserved five pieces and 196.25kg. |

Additional reviewed backend work includes proof of the existing second factor
before replacing recovery codes, rate limits on sensitive two-factor actions,
explicit proxy trust, safer CORS defaults, metadata-only shipment/trip lists and
UTC-normalized calendar filters. List-query regressions assert two SELECTs
without loading document payloads, while detail reads retain their contents.
Date tests cover the final microsecond and 23/25-hour daylight-saving days.

## Visual evidence

The images are actual application captures using synthetic data. The phone
and tablet captures include the review harness around the application; their
390px and 768px iframes are real CSS layout viewports, not device photographs
or native mobile browser emulation. Screenshots can represent separate review
sessions: the six-piece desktop example and five-piece phone example are not
the same saved calculation.

| Evidence | What it demonstrates |
| --- | --- |
| [Desktop chooser](2.1.0/emcargo21-chooser.jpg) | Four explicit transport choices, short introductory copy and a direct import path; privacy copy reflects enabled history. |
| [Phone chooser](2.1.0/emcargo21-mobile-chooser.jpg) | All four transport choices remain readable in the first viewport after shortening the introduction. |
| [Desktop goods](2.1.0/emcargo21-goods.jpg) | Aligned inputs, six pieces at 39.25kg each, 235.5kg total, draft feedback, document readiness and the primary next action. |
| [Phone goods](2.1.0/emcargo21-mobile-goods.jpg) | Wrapping import actions and a usable 72px quantity field beside the unit and weight; five pieces produce 196.25kg. |
| [Phone shipment summary](2.1.0/emcargo21-mobile-summary.jpg) | The expanded summary exposes 196.25kg, 0.025m³ and the CMR's nine unanswered fields above the goods form. |
| [Tablet chooser](2.1.0/emcargo21-tablet-chooser.jpg) | The 768px layout keeps all four usable modes readable and stacks the import panel below them. |
| [Phone overview](2.1.0/emcargo21-mobile-overview.jpg) | Draft recovery and recent shipments adapt to a narrow viewport; reference, route, document state and actions remain visible. |
| [Empty overview](2.1.0/emcargo21-empty-overview.jpg) | Honest zero counts, an explicit empty state and a useful new-shipment action. The shortened two-factor reminder does not dominate the page. |
| [Command dialog](2.1.0/emcargo21-command.jpg) | Restrained navigation search with legible choices and clear focus. |
| [Export result](2.1.0/emcargo21-export.jpg) | Ready CMR status, saved shipment feedback and the client-side successful-download message after the bundle request completed. |
| [Login](2.1.0/emcargo21-login.jpg) | A restrained sign-in form with explicit labels, clear field boundaries and one primary action. This screenshot establishes presentation, not completed browser authentication. |

Core dark-theme contrast calculations are 16.15:1 for body text, 7.38:1 for
the muted text token, 7.12:1 for the accent on a panel, and 4.84:1 for white on
the primary button. These token checks do not cover every rendered state;
some older `dark:text-slate-500` secondary text has approximately 3.81:1
contrast on the panel background and remains a polish item.

The phone document's measured `clientWidth` and `scrollWidth` were both 375px,
with the shipment summary closed and expanded. The surrounding iframe is
390px wide, with its native vertical scrollbar accounting for the difference.
The lower edge visible in the summary capture is not horizontal page overflow.

## Functional evidence and test status

The browser used an opt-in development transport to an isolated, real FastAPI
TestClient with a temporary database. Calculations and exports were produced
by application routes; the transport did not substitute fake result bodies.
The synthetic session does not establish browser login or production cookie
behavior. Authentication and authorization evidence also comes from the
backend and frontend regression suites.

| Check | Result available at review time |
| --- | --- |
| Full backend suite before the final scoped fixes | 2,707 passed, 3 skipped. |
| History, department and query suite after the draft publication correction | 53 passed. |
| Quantity, API validation, IFTDGN and DG/trip checks after the parser correction | 144 passed, 2 existing skips. |
| Full frontend suite after the restoration correction | 48 test files, 362 passed. |
| Targeted restoration, wizard shell, draft and snapshot checks | 29 passed, including seven new restoration integration regressions. |
| Production frontend build and version check | Passed; the production build was repeated successfully after the restoration correction. |
| Browser calculation | Six steel plates produced 235.5kg; changing the phone example to five produced 196.25kg. |
| Browser save and export requests | Shipment update and bundle export returned HTTP 200; the UI displayed saved and successful-download feedback. |
| Browser restoration after the lifecycle correction | Initial reopening and a second Save and close → Overview → Continue loop both restored the steel-plate description, quantity 5 and 196.25kg without re-entry. |

The browser's native download-event wait timed out after three seconds before
the backend export completed. The later HTTP 200 and UI feedback were observed,
but the browser-downloaded archive bytes were not collected and inspected.
Archive behavior is also covered by automated export tests. The report therefore
does not claim a fully verified browser download artifact.

## Release boundary and remaining work

At review time, the final CI run, merge, GitHub release and GHCR publication
were still pending. A passing design score does not replace those release
gates. This document records the candidate review, not a claim that publication
has completed.

Remaining non-blocking polish includes localized numeric display in some Dutch
screens, reducing prose in dense detail forms, and aligning the remaining
older panels and icons with the new workspace. Physical mobile devices,
screen readers, a complete light-theme review, browser coverage of every
language and production-scale performance were not exercised here.
