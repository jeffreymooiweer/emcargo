# The regulatory database

Every dangerous-goods answer EMCargo gives was read out of a book. This page
describes the machinery that keeps that honest: where the books live, how facts
get out of them, and what to do when a new edition appears.

## The shape of it

```
publishers (UNECE, OTIF, IMO, Rijksoverheid, mindef.nl)
        │  download or operator-supplied file
        ▼
document store          /data/regulations (outside git; EMCARGO_REGULATIONS_DIR
        │               overrides; a temporary regulations cache is the CI cache twin)
        │  scripts/regulations_store.py — status / fetch / add / verify
        ▼
register                backend/seed/dg/sources.json (in git: editions, URLs,
        │               pinned sha256 per document — metadata, never text)
        │  scripts/extract_*.py, scripts/read_land_regulations.py
        ▼
derived facts           backend/seed/dg/*.json + backend/app/config/dg_compliance.json
        │               (in git: every value carries its provision and source)
        ▼
the application         backend/app/services/dg — loads seeds, computes, and
                        reports which editions it runs on (regulatory_manifest)
```

Two rules carry the whole design, and neither is negotiable:

1. **Regulatory text never enters the repository.** The books are not ours to
   redistribute, and `docs/data-sources.md` promises it. The repository holds
   derived facts — thresholds, codes, table rows — each with the provision it
   came from, and the register holds hashes so a future reading can prove it
   read the same book. The language guards enforce the spirit of this: even a
   quoted Dutch sentence in a docstring fails the build.

2. **A regulatory table gets two independent readings or none.** One reading is
   an anecdote; the seed records both (`readings`, `cross_check` fields) and a
   table with only one stays out — which is why ADN table C is registered,
   present in the store, and still not in the seeds.

## The store

`/data/regulations` is a volume, not a directory in the container image: it
survives the container. On an installation it is the same `/data` the database
lives on. The CI workflows keep a twin under a temporary regulations cache via
`actions/cache`, and `read_land_regulations.py` looks in the store first.

```
python scripts/regulations_store.py status    # what is present, what is missing
python scripts/regulations_store.py fetch     # download everything fetchable
python scripts/regulations_store.py add adr_nl_complete ~/Downloads/ADR-2025-NL.pdf
python scripts/regulations_store.py verify    # exit non-zero on any hash mismatch
```

The publishers are hostile to scripts in ways that change by the day — UNECE
answers 403 to anything that does not look like a browser, the web archive
rate-limits by mood. `fetch` climbs the same ladder the reader uses (browser
headers, then the archive) and gives up loudly, not silently. When the
development container cannot reach a publisher at all, the
**Fetch regulations into the store** workflow does the same work on a runner
and leaves the volumes in the Actions cache; the printed sha256 in its log is
what gets pinned into the register afterwards.

Two of the sources cannot be re-downloaded at all — the Dutch ADR PDFs and the
Dutch ADN HTML index were supplied by the operator. Their hashes are pinned;
if the store copy is ever lost, the operator's original is the way back, and
`status` will name exactly which file is owed.

## When a new edition appears

ADR, RID and ADN revise every two years (2027 next, transition to 30 June);
the IMDG Code every two years with a transitional year; the IATA DGR yearly.
The procedure is the same each time:

1. **Register the new edition** in `sources.json` — a new entry (or updated
   URLs and a cleared hash) with the new edition string. A changed publisher
   file is a manifest change, never a silent swap: `add` and `fetch` refuse a
   file that contradicts a pinned hash.
2. **Fetch it into the store**, locally or via the workflow, and pin the hash.
3. **Re-run the extractors** (`extract_adr_table_a.py`, `extract_adn_table_a.py`,
   `extract_imdg_dgl.py`, …) against the new files, with both readings.
4. **Diff the seeds.** The diff *is* the review: every changed row is a change
   the new edition made, and rows that changed unexpectedly are the reason the
   two-readings rule exists.
5. **Update the validity dates** in
   `backend/app/services/regulatory_manifest.py`, whose `expired_rule_sets()`
   is what tells a running installation its data has aged out.

## What the register holds today

Twenty-two source documents: the free land-mode texts (ADR volumes I and II in
English and French, RID, ADN in English and French), the operator-supplied
editions the first readings came from and the ones that closed gaps no free
publisher could — the German ADR in two volumes, the ADN in Dutch and in
German, a printed Dutch ADR 2025, the RID in German and French — the IMDG 42-24
amendment resolution and three ADN session documents. `status` is the live answer; the register file is the
durable one.

Beside them stand entries of a second kind — the **models of 5.4.3**, the
instructions in writing, one per regime and language (twelve since the RID
joined in v1.124.0), plus the ADN 8.6.3 checklist in four. They are not sources: they
are pages the application serves back out of a source, because ADR and ADN
5.4.3.4 require the document the crew carries to correspond in form and content
to a four-page model the book prints. Such an entry carries `model_of` (regime,
language) and, where an edition in the store prints that model, `cut_from` with
the page range and the tool that measured it:

    python scripts/find_instructions_pages.py /data/regulations/adn.pdf

reports where the model sits, and the range goes in the register. The
application (`app/services/regulations.py`) cuts those pages on request and
keeps the result in `<store>/derived/`, named after the edition and the range
it came from so that a register pointing somewhere new never gets yesterday's
pages. Measuring and cutting use the same library on purpose: pypdf counts one
page more from the front of the ADN volumes than PyMuPDF does, and a range
measured with one and cut with the other put 5.4.3.5 on the driver's first
sheet. Whether a cut is the model and nothing else is checked, not assumed —

    python scripts/check_instruction_models.py

cuts every registered model and prints, page by page, whether it carries the
model's title and whether a neighbouring section leaked in. It runs on a runner
(`fetch-regulations`, input `verify_instructions`), where the store holds the
editions.

Since v1.130.0 the cuts themselves ship with the application: the **Extract
model documents** workflow runs `scripts/cut_model_documents.py` on a runner,
which verifies every source book against the register's SHA-256, cuts the
pinned ranges, and commits the results with their provenance to
`backend/seed/models/`. The lookup order is deliberate — the operator's store
first, the bundled cut second — so an installation that collects its own
editions is served from those, and a fresh installation still hands the crew
the paper. Should a model be in neither place, the application reports it as
missing and names the document that would produce it; it is never filled in
from a neighbouring language, because instructions in a language the crew
cannot read are what 5.4.3.2 exists to prevent.
