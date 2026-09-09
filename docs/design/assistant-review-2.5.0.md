# Shipment assistant review — 2.5.0

Reviewed on 2026-09-09 against the owner's requirement: a guided assistant that
uses EMCargo's own requirements, understands supplied facts and asks for
clarification when it cannot, with an honest self-assessment of at least 8/10.

## Iterations

The starting implementation scored **4/10**. Reproduced failures included saving
“ik weet het niet” as a sender, reading “4 pallets totaal 800 kg” as 4 kg,
turning -20 kg into 20 kg, accepting an invalid calendar date and reading
“geen tank” as tank transport. Optional document fields also prolonged the
interview without a clear decision from the user.

The first replacement scored **7/10**. It had the focused question and summary
layout, but review still found omitted counts becoming one item, DG answers
being discarded on the wizard handoff, incomplete undo, a focus race in address
entry and model runtime libraries that could not load. These were fixed before
assigning the final score. A later real-model test exposed a 26.66-second choice
timeout; a smaller choice prompt and output budget reduced that same check to
3.30 seconds, returning clarification without writing a guessed carriage mode.

## Final assessment: 8.2/10

This is an engineering self-assessment, not an independent usability study.
Scores cover the available evidence and explicitly limit visual confidence.

| Criterion | Weight | Score | Evidence and remaining limits |
| --- | ---: | ---: | --- |
| Answer integrity | 30% | 8.5 | Unknown, negative, ambiguous and ungrounded answers stay open. Weight basis, corrections and multiple facts are tested. Names still rely on user-supplied truth. |
| Questions driven by the application | 25% | 8.5 | The calculation, DG preparation and document definitions determine pending questions. Required answers cannot be skipped; optional document details are a separate choice. |
| User control and recovery | 20% | 8.5 | Inspectable summary, editable facts, complete Previous snapshots, preserved text on clarification, reopening and wizard handoff are covered by interaction tests. DG details can also be reviewed in the normal wizard. |
| Runtime and reliability | 15% | 8.5 | Real pinned local-model tests, repaired SONAME links, explicit container libraries, bounded extraction, deterministic fallback and stale-response protection. Rich prose remains dependent on local CPU performance. |
| Visual confirmation | 10% | 5.0 | New compass, motion, dark/light styles, responsive layout and reduced-motion support are implemented. Browser policy blocked a rendered review; this score is an evidence cap, not a claim that the layout was visually approved. |

The weighted score is 8.15, rounded to **8.2**. A higher score would require
observing the rendered desktop/mobile interface and users completing realistic
shipments, plus a broader corpus of real-model answers in all four languages.

## Verification record

- Backend assistant regression suite: 119 passing tests before publication,
  including real calculation and DG services, malicious/stale question metadata,
  model hallucinations, ambiguous weights, counts, date validity and corrections.
  A final review added five passing portable-tank cases across the four languages:
  a specific tank mode must not collapse to the generic word "tank". All 14
  affected tank, package and unrelated-compound cases passed after that fix.
- Full frontend suite: 420 passing tests; after the last confirmation and manual
  DG-decision fixes, the three affected suites passed all 42 tests. TypeScript
  and production builds passed. The full final tree is checked again by CI.
- The full backend run initially had 2,756 passes, three skips and five release
  metadata failures because the 2.5.0 changelog was still absent. After adding it,
  all 18 version/changelog tests passed. CI must pass the full final tree before
  merge; the earlier run is not represented as an all-green run.
- Real Qwen3-1.7B Q8_0, installed from the SHA-256-pinned sources: two pallets
  from spoken Dutch took 0.38 s without model inference. Rich Dutch prose about
  1,000 jerricans, sender, street address, receiver, route, carrier and order was
  separated in 12.32 s including startup. An unprovided receiver street address
  and shipment reference were not filled from the city and order number.
- With the actual runtime installed, explicit separate packages were understood
  in 0.04 s. An ambiguous reservoir paraphrase remained unrecorded; selecting
  the actual option then populated the DG product. Mocked model choices also
  verify that a proposal requires an explicit user selection, in both API and UI.
- The pinned server installed into a clean temporary directory and ran
  `--version`. The PR Docker gate repeats this inside the built image, exercising
  the production installer and its system libraries without downloading weights.
- DOM interaction tests cover options, free-text clarification, preserved input,
  address suggestions, keyboard focus, duplicate requests, late responses,
  reopening, full undo, missing counts and DG answer transfer into the wizard.
- Authentication, DG Specialist release, document validation and DGSA permissions
  stay with their existing application services. Assistant completion hands a
  draft to the wizard; it does not create a regulatory release.

## Explicit limitations

The Cloud Browser rejected the preview URL under its URL policy. No alternate
browser or indirect preview was used. There are no claimed screenshots, browser
layout checks or mobile visual approval for this release. DOM tests validate
interaction and state behavior, not pixel layout or animation quality.

The local model is deliberately conservative and does not understand every
paraphrase. Unsupported answers receive clarification and retain the user's text.
Model-only option interpretations require confirmation. The shipped application
rules remain authoritative; the model cannot invent regulatory facts or release
a dangerous goods shipment.
