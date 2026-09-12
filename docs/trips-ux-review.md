# Trips workspace review — 2.8.0

The previous workflow split selecting a load, assessing it, saving it and reopening it across Groupage and Trips. This change brings those operations into one workspace at `/trips`.

## Review and corrections

The first implementation scored **7.2/10** on a code-based UX review. It removed navigation overhead but needed stronger protection against misleading assessment states and lost work.

The second pass fixes these concrete findings:

- Results are bound to the exact assessment inputs. Editing the load immediately removes the old result; late network responses cannot restore it.
- A fresh calculation is not labelled as saved until the server returns the persisted assessment.
- Forbidden products, mixed-loading errors, incomplete quantities, unfinished LQ checks and profiles outside ADR do not receive a positive overall finding.
- Missing vehicle mass is exposed where the LQ result requires it. Decimal commas are accepted; invalid or negative masses cannot be silently treated as unknown.
- Failed saves retain the draft and provide a retry. Switching trips asks before discarding edits; a page unload also warns about unsaved work.
- History selection prevents duplicate ids; duplicate exports are rejected. Failed or malformed imports identify the files that were not included.
- Saved trips reopen directly, including during React StrictMode, and retain the historical assessment and regulation editions until recalculated.
- Ordinary freight and a single shipment can start a trip. Empty trips cannot be persisted.

## Assessment

**Provisional score: 8.2/10 for the implemented interaction and information design.** This is a self-review, not a user study or a completed screenshot review.

| Criterion | Score | Evidence and limits |
| --- | ---: | --- |
| Task efficiency | 9 | One workspace, immediate shipment selection, automatic checks, one save action; no separate assessment or detail page. |
| Information hierarchy | 8 | Primary load editor, secondary saved-trip list, collapsed filters and calculation details; critical findings stay expanded. Assessed from the layout implementation. |
| Feedback and error recovery | 8.5 | Input-bound results, server-confirmed saves, explicit incomplete states, retry paths and retained edits covered by tests. |
| Accessibility and presentation | 7.5 | Labelled controls, keyboard actions, 44px controls, light/dark styles and reduced-motion handling. Rendered spacing, contrast and mobile interaction remain unverified. |

The mean is 8.25, reported conservatively as 8.2. Visual approval is **not claimed**: the provided browser returned `ERR_BLOCKED_BY_CLIENT` for both local preview addresses. No screenshots of this change were obtained.

## Verification

- Full frontend suite: 455 tests passed before the final two regression cases; those two and the affected component tests also pass.
- Production TypeScript/Vite build passed.
- Full backend suite: 2,901 passed, 3 skipped, one new Dutch interface-register failure. Its wording was corrected to the application's existing formal register and the relevant gates were rerun.
- Tests cover single-shipment storage, empty-trip rejection, ordinary freight, persisted source profiles, departmental visibility and retention.
- No new packages, database columns or changes to the regulatory calculations.

## Boundaries

This remains an assessment of selected goods on one transport unit. It does not perform route optimisation, capacity planning or load changes between stops. A saved result is not DG release. Source shipment edits are not automatically copied into saved trips; the dated snapshot message states that explicitly. Unsaved work is held in the current page only, including when retention is disabled.
