# Shipment assistant review — 2.5.1

Reviewed on 2026-09-12 following the owner's request to continue towards 10/10.

## Reproduced defects and resulting behavior

| Reproduced behavior in 2.5.0 | Behavior after the correction |
| --- | --- |
| The API and interface offered an assistant without installing its local model. | Both require the installed model. The interface explains installation and provides manual continuation. |
| `120 x 80 x 100 cm, totaal 800 kg` discarded the stated weight and calculated 1536 kg. | Both measurements survive; the four pallets total 800 kg. An unstated weight basis remains a question. |
| Spoken `acht` was refused; German/French pallet plurals were not recognized as units. | Count answers accept supported number words and the same package units as intake. A different unit requires clarification. |
| `Het zijn acht pallets` became the consignor's name. | It corrects the sole matching goods line. Multiple matching lines require clarification. |
| `2 of 3 pallets` became two pieces of goods. | Alternative quantities remain unrecorded. Calendar dates are not mistaken for quantity ranges. |
| A labelled city-only address bypassed follow-up validation. | Initial labelled addresses and follow-up addresses use the same completeness check. |
| Completed dimensions/weight were difficult to revise without undoing later work. | The summary opens a correction for the selected goods line; subsequent party and document answers survive. |
| A local-model timeout could store the complete narrative as one goods line. | The failed read is atomic and explicit. The original text stays available for retry; no narrative is silently accepted as interpreted goods. |

The interface also uses plain questions for parties and routing, opens the
application's own explanation when the user does not know an answer, and has
larger secondary text and controls. Closed disclosures and hidden summaries are
excluded from the dialog's keyboard focus loop.

## Verification

- The full backend run initially returned 2786 passes, 3 skips and 21 failed/error
  cases caused by a missing `socksio` dependency in this environment, including
  downstream catalog tests. Installing that environment dependency and rerunning
  the affected cases produced **21 passes**. No application dependency or proxy
  policy was changed to obtain that result.
- The final affected backend set passed **290 tests**, covering assistant behavior,
  runtime constraints, API prerequisites, units and all four language/error bundles.
- The full frontend checkpoint passed **427 tests**. After the final summary-edit
  and focus changes, the affected component passed **26 tests**. The production
  build, TypeScript checks and version consistency check passed.
- The actual SHA-256-pinned Qwen3-1.7B Q8_0 weights and llama.cpp binary installed
  successfully in an isolated directory. The measured final startup took 1.09 s.
  This was a real local runtime, not a mocked inference endpoint.

## Real-model iteration

Four synthetic prose descriptions named four pallets, a sender, a receiver, a
carrier, a route and purchase order ABC123. The initial model returned only
`Kade 1` as the sender address and sometimes copied the purchase order into
unrelated reference fields. Existing reference guards rejected those guesses;
the address guard and prompt were tightened after observing the incomplete address.

A subsequent run while regression tests used the same CPU hit the 25-second
inference timeout. This exposed the narrative-as-goods fallback described above.
The final schema omits unstated fields, and failed rich-text reads now explicitly
preserve the original draft. The same four scenarios were then run serially:

| Language | Final elapsed time | Result |
| --- | ---: | --- |
| Dutch | 12.28 s | Correct goods/count/unit, parties, carrier and order; partial address remains open. |
| English | 9.38 s | Correct facts including the source-grounded sender street and town. |
| German | 8.94 s | Correct goods/count/unit, parties, carrier and order; partial address remains open. |
| French | 9.00 s | Correct goods/count/unit, parties, carrier and order; partial address remains open. |

All four kept the unprovided receiver street address and unrelated references
empty. These are individual synthetic samples, not a latency percentile or a
claim to understand every paraphrase. English `machine parts` still produces
conservative machinery UN suggestions from the existing catalog, requiring an
explicit user decision; the model does not confirm a classification.

## Assessment: 8.5/10

This is an engineering self-assessment. The reproduced data-integrity and
model-availability defects are fixed, and the real model now has evidence in all
four languages. Partial interpretations and unavailable inference remain explicit.

A 10/10 is not established: the browser refused the preview with
`net::ERR_BLOCKED_BY_CLIENT`, so there are no new rendered desktop/mobile
screenshots or visual approval. No alternate route was used to bypass that
restriction. A broader real-user corpus, including long mixed shipments and
repeated corrections under load, remains necessary for a higher overall score.

Ordinary document checks and DG Specialist release remain authoritative. These
changes neither classify goods independently nor grant transport release.
