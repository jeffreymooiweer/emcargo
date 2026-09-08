<!--
EMCargo is a personal project. Please open an issue and agree the shape of a change
before writing it — see CONTRIBUTING.md. A pull request that arrives without one may be
closed unmerged, which is a waste of your time rather than a judgement on your code.
-->

## What this changes

<!-- One or two sentences. The diff already says what; say why. -->

Closes #

## Why

<!--
What was wrong or missing, and what a user notices now that they did not before.
If this corrects data, name the source and the edition — ADR 2025 Table A 3.2.1,
IMDG Amendment 42-24 chapter 7.2.8, EmS Guide MSC.1/Circ.1588/Rev.3, IATA DGR 2026.
-->

## How it was checked

<!-- Delete what does not apply. -->

- [ ] `cd backend && DATABASE_URL=sqlite:////abs/path/test.db DATA_DIR=/abs/path python -m pytest`
- [ ] `cd frontend && npm run build` (typecheck)
- [ ] Tried it in the running application
- [ ] A test covers the behaviour that changed

<!-- Paste the test summary line if anything failed or was skipped. -->

## Checklist

- [ ] `CHANGELOG.md` updated under the version this bumps to
- [ ] `VERSION`, `backend/VERSION` and `frontend/package.json` agree
      (patch for fixes and docs, minor for new functionality, major only for breaking
      changes — when in doubt take the smaller bump)
- [ ] Documentation in `docs/` updated where behaviour changed
- [ ] `frontend/src/i18n/nl.json`, `en.json` **and** `de.json` updated for any new
      interface string, and any new `{nl, en}` block in the config or seed data carries a
      `de` as well — `backend/tests/test_languages.py` fails otherwise
- [ ] **No regulatory text added.** The repository holds factual data only — a UN number
      mapped to a code, a material mapped to a density. ADR, the IMDG Code and the IATA
      DGR are copyrighted and must not be committed, and neither must the PDFs they came
      from
- [ ] **No real shipment data** in code, tests, fixtures or screenshots — no company
      names, addresses, reference numbers or consignee details
- [ ] Any new data source is recorded in `docs/data-sources.md`

## Notes for review

<!-- Anything you are unsure about, deliberately left out, or want a second opinion on. -->
