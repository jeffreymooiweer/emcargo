# PR #13: local browser follow-up

Reviewed on 2026-09-12 from `2b1c83c34b1036166dfbbc1d179106801f9e0577`.
The real FastAPI backend and Vite frontend ran on Windows x86-64 with a separate
SQLite development database. Browser interaction and screenshots used
`npx --yes @playwright/cli`. No assistant responses were mocked in browser QA.

## Defects repaired

- Vite rendered a blank page because a lazy component declaration preceded the
  React import after development transformation. Move it below that import.
- The installer offered a Linux executable on Windows. Select pins by OS and
  architecture, install the native Windows CPU archive, preserve the process
  environment and launch without a console window. Unsupported hosts stay gated.
- Existing paths alone counted as an installation. Require a nonempty executable
  and the expected model size and GGUF header. Downloads retain SHA-256 verification.
- Model removal during an interview left conversation controls active. Disable
  them after the API rejects the turn, retain the answer and recheck installation
  without resetting the interview or automatically submitting the answer.
- The real-model scenario stored `Trans Janssen en het` as the carrier because
  the labelled-fact reader missed the article before `ordernummer`. Preserve
  company conjunctions while separating the next labelled field.
- The quantity editor rejected `toch 5 pallets`. Accept explicit single-count
  corrections while continuing to reject uncertainty, multiple counts and
  incompatible units.
- The summary displayed `prepaid` instead of the translated option, and revision
  placed that code in the text box. Display the label and select the recorded radio.
- Mobile errors and recovery actions fell below the fixed footer. Scroll the new
  error into view without moving keyboard focus. At 320 px, wrap the progress
  stages into two columns; measured dialog scroll width now equals its width.

## Browser verification

- No installed model: no conversation input; direct authenticated step request
  returns HTTP 409 with `assistant.model_required`.
- The official Windows b10452 CPU archive was downloaded and verified against
  SHA-256 `ab30399cddbc7c7d7b69626ace6d4217491f4d29f473d9dd84bc0e3a57d36eae`.
  The unchanged Qwen3-1.7B Q8_0 model was downloaded and verified against its
  existing repository pin. A real inference returned in 8.840 seconds with
  `running: true`, four pallets of machine parts, the stated parties and route,
  carrier `Trans Janssen` and purchase order `4711`. This is one observation,
  not a latency guarantee.
- Completed a Dutch road-shipment interview through the ready screen. Combined
  `120 x 80 x 100 cm, 800 kg per pallet` preserved both measurements and produced
  3,200 kg for four pallets. Correcting to five pallets produced 4,000 kg.
- Revised weight to 1,000 kg total and dimensions to 100 x 80 x 90 cm; weight,
  quantity, parties, addresses and later document answers stayed intact.
- `ik weet het niet` opened question-specific help and retained the answer.
- Stopped the model, temporarily renamed its file, and submitted `Franco`.
  The API rejected it and the controls became disabled. Rechecking while absent
  stayed blocked. Restoring the file and rechecking retained `Franco`, which could
  then be submitted successfully. The installed model was restored afterward.
- Checked dark/light desktop rendering, 390 x 844 mobile, 667 x 375 landscape,
  and 320 x 640 mobile. Screenshots were visually inspected.

## Automated verification and limits

- All assistant tests plus language and error-message checks: **283 passed**.
- Full frontend suite after the broader review: **433 passed** in 54 files, including 27 assistant tests.
- TypeScript/production build, version consistency (2.5.1), changed Python-file
  static checks and `git diff --check` passed.
- The first backend subset ran before its database was initialized; a Linux
  symlink test also needed permissions unavailable in the restricted shell.
  Both environment issues were corrected before the passing runs above.
- The build retains the existing warning about a bundle exceeding 500 kB.
- Full backend suite: **2,836 passed, 4 skipped**. After the UTC timestamp fix,
  the affected history, trip, date and source-language checks passed (**58 tests**,
  including two new timestamp regressions). Docker build and native
  Linux/ARM model inference were not exercised. Platform-selection regressions cover those
  selection branches; the real runtime exercise here used Windows x86-64.
- Changes are local to this checkout and have not been pushed to GitHub.

## Broader functional review

- Logged in through the visible in-app browser. Playwright CLI checked 16 main
  routes and all 12 settings tabs: no page exceptions or HTTP 5xx responses.
- Created, edited, searched, exported and reimported a synthetic article through
  the interface. The spreadsheet round trip updated the existing article.
- Live API checks created, updated, read and deleted test equipment, shipments,
  trips and a user. A regular user could not manage equipment; deactivation
  revoked access. No invitation email was sent.
- A two-consignment trip returned 1,200 ADR points and loss of the exemption.
- Browser import uncovered headings being imported as goods and recognised
  columns being used in their original order. Clipboard data now uses the same
  mapping flow as files, and recognised headers apply that mapping immediately.
- A manual 1,000 kg line weight was lost when dimensions changed. Manual weights
  now live in the draft and survive recalculation. The browser confirmed a
  1,100 kg shipment after changing dimensions, exporting and reopening it.
- Saved and resumed a draft, filled document fields, downloaded an individual
  CMR and a ZIP document bundle, and reopened the automatically kept shipment.
  The CMR was rendered and visually inspected.
- UTC database timestamps previously appeared two hours early in the Berlin
  browser. Shipment/trip responses now include their UTC offset.
- The complete backend run exposed Windows-only test setup problems: unclosed
  PDF readers, default text encoding, an incomplete subprocess environment,
  the WSL Bash placeholder and drive-letter separators in fake socket paths.
  The POSIX mode-bit test is explicitly skipped on Windows; this is not a
  verification of Windows ACLs. Production permission rules were not weakened.
- SMTP delivery, actual Docker updates, external SSO/connector handshakes and
  real regulatory release were not executed. Their applicable local automated
  checks ran. Sea, air and multimodal entry are currently unavailable by design.

## Novice chairs scenario follow-up

The visible in-app browser reproduced a six-chair Breda–Antwerp shipment,
corrected to eight chairs, with unknown weight. Intake now keeps certain facts
when a separate sentence asks for help; route parsing stops at sentence boundaries.
Count corrections accept the current goods noun. Explicit payer paraphrases
produce a deterministic proposal requiring confirmation, rather than a model guess.

Unweighed included lines now remain in totals. CMR/AVC readiness and HTTP export
require goods descriptions, positive quantities and positive weights. Existing
bundle and review fixtures now contain complete cargo instead of empty lines.
Outer package dimensions produce volume even without material recognition, and
dimensions no longer suppress a missing-weight follow-up.

Visible verification: missing weight disabled download; adding 120 kg total and
60 × 60 × 100 cm per chair yielded eight chairs, one line, 120 kg and 2.88 m³,
then enabled export. The export action stored the test shipment in history.
All 433 frontend tests and the build passed, followed by 21 focused tests after
the final API-message adjustment. The full backend run passed 2823 tests with
four skips; its 23 failures were traced to incomplete legacy export fixtures
and Windows selecting WSL Bash. All 114 affected follow-up tests passed after
fixture completion and selecting Git Bash. The final 17 bundle tests also pass,
including three new HTTP refusal cases for empty/unweighed cargo.

## Mixed-goods novice follow-up — 12 September

Counted nouns now form separate goods rows, including one-word descriptions
and a separate route line. Unknown noun units normalize to pieces only when
grounded in the description. Model party proposals must be grounded as an
explicit party or company; counted goods and route towns cannot become names.
An explicit split request can repair the previous merged row or reclaim goods
misclassified as consignor. Existing measurements and DG details require
clarification instead of an automatic allocation across new rows.

Visible in-app verification passed for the original novice sentence and the
three-line input: two desks, four office chairs, Eindhoven to Gent, no invented
parties. The previous explicit correction also restored the old draft.
Validation: 255 assistant/backend and language tests, 27 AssistantModal tests,
and the frontend build passed. The local-model availability guard is unchanged.

## Iterative novice acceptance, 12 September 2026

Completed two visible in-app browser flows with the installed local Qwen model:
two desks and four office chairs from Eindhoven to Gent (final weights 64 and
56 kg), and three boxes of books from Utrecht to Leuven (60 kg, 0.09 m³).
Both were saved and exported. The books shipment was reopened from history.
PDF text and rendered pages were inspected using the saved shipment data.

The iterations fixed combined named dimensions and mass, consistent total/unit
mass parsing, explicit corrections targeting an earlier goods row, preservation
of pending ambiguous mass when an old confirmed mass exists, and clarification
of inconsistent total/unit masses. Optional conversational deferral now keeps
the separate weight question, and subsequent answers clear deferred reminders.
Grounded local-model extraction reads company names from conversational answers
without accepting invented names or full conversational sentences. Plain road
cities remain cities unless an explicit facility kind is supplied.

Assistant changes invalidate stale calculation results and refresh outside the
goods step. Partial known volume is not presented as a complete shipment total.
Payment/date/place questions use plain wording in all four UI languages, and
the known-weight warning distinguishes missing transport dimensions. CMR goods
rows preserve package units, including “3 dozen boeken” on all four copies;
localized package-label regressions cover NL, EN, DE and FR.

Validation: full backend suite 2,878 passed / 4 skipped; after the final route,
deferred-reminder and CMR fixes, 211 relevant backend tests passed. Full frontend
suite 434 passed across 54 files; production build passed. Existing no-local-
model guards remain intact. Changes are local, not pushed.

Self-assessment: 8/10 for the tested ordinary road-shipment workflow. Weighted
equally: data preservation/export 9, natural-language understanding 7.5,
correction/ambiguity handling 8, completion workflow 8, wording/usability 7.5.
This is not an independent novice-user study or renewed end-to-end acceptance
of dangerous goods, rail or inland waterway flows. Complex references and some
generic clarification/catalogue messages still leave room for improvement.
