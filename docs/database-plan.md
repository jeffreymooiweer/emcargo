# The database, and what the roadmap asks of it

> Historical design/research notes. For the current interface and setup, use the
> [user guide](user-guide.md), [configuration](configuration.md) and
> [design verification notes](design/README.md).

*Groundwork for a decision, not a licence to start building. The question was whether
SQLite still suffices given what the [roadmap](../ROADMAP.md) plans. Everything under
"What is there today" was measured in this repository in August 2026 — no value here
comes from memory. The stages at the end are a proposal; none of them has been built.*

---

## What is there today

| Measured | Value |
|---|---|
| Engine | the existing SQLite file in `/data` (override with `DATABASE_URL` only for a deliberate database migration), a single setting (`app/core/config.py`) |
| SQLite references in application code | **two**, both in `app/core/database.py` — everything else goes through SQLAlchemy |
| Tables | 12; roughly six carry real data |
| `journal_mode` | `delete` — the rollback journal, not WAL |
| `busy_timeout` | 5000 ms, inherited from Python's `sqlite3` default rather than chosen |
| Connection pool | `QueuePool`, size 5, overflow 10 |
| Endpoints | 92 synchronous, 3 asynchronous — the synchronous ones run in the threadpool |
| Processes | one uvicorn, no `--workers` (`backend/entrypoint.sh`) |
| Migrations | none; `Base.metadata.create_all` plus one hand-written `ALTER TABLE` in `startup.migrate_equipment_columns` |
| Alembic | `alembic==1.14.0` is shipped in `requirements-runtime.txt`; `backend/alembic/env.py` is a one-line placeholder and there is no `alembic.ini` |
| Test fixtures | 24 test files build their own engine, hard-coding `sqlite:///` 27 times; there is no `conftest.py` |
| Database contents | materials, profiles, reference items, equipment, users, settings — together well under a few megabytes |
| Deliberately outside the database | the dangerous goods data (12 MB) and the locations (1.9 MB) are JSON files under `backend/seed/` |
| `Job` | the model exists, `purge_sensitive_data` empties the table on every start, and nothing ever writes to it |

**Portability is not the obstacle.** Every column type in `app/models/` is engine
neutral: `String`, `Text`, `Integer`, `Boolean`, `DateTime(timezone=True)`, `ForeignKey`,
`func.now()`. The two constructions worth suspecting were compiled against both
dialects to check rather than assumed:

| Construction | SQLite | PostgreSQL |
|---|---|---|
| `Material.active.is_(True)` (11 uses) | `materials.active IS 1` | `materials.active IS true` |
| `Equipment.specifications.ilike(…)` | `lower(…) LIKE lower(?)` | `… ILIKE %(param)s` |

Both are valid on both. There is no SQLite-only SQL in the application. A
`DATABASE_URL` pointing at PostgreSQL is, on the schema side, already possible today.

## SQLite is not the throughput problem

A company of the size this application is aimed at does not come close to SQLite's
write ceiling. Two hundred shipments a day at roughly fifty writes each is ten thousand
writes a day — about 0.35 writes per second across an eight-hour working day. Two hundred
employees do not all draw up consignments at once, so the real figure is lower still. The
signal that is generally given for outgrowing SQLite is *sustained* write traffic orders
of magnitude above that, or several machines writing the same file over a shared volume.
Neither is in sight; both are picked apart below.

What *is* worth fixing about SQLite today is cheaper than a migration. Under
`journal_mode=delete` a writer blocks every reader for the duration of the write. With
92 synchronous endpoints running in a threadpool, that is exactly where a future
"database is locked" will come from. Write-ahead logging removes it, and it is a handful
of lines.

## What actually changes

The constraint is not the engine. It is this, from `docs/development.md`:

> `init_app` calls `Base.metadata.create_all`. That creates **missing tables** and never
> adds a column to a table that already exists.

The escape route documented there — settings as a single JSON document, so the schema
never changes — works for preferences. It does not work for a shipments page with
filters, an address book, an articles library or a DGSA report: those want real columns,
indexes and `GROUP BY` over date ranges. The moment the shipment history lands, "there
is no migration runner" stops being deliberate simplicity and becomes a blockage.

Per roadmap item:

| Roadmap item | What it asks of the database |
|---|---|
| Shipment history, shipments page, departments | The first genuine persistent write load, and the first that filters. Needs migrations and indexes. Does not need a different engine. |
| Address book, templates, own articles library | More tables, more schema changes. Same answer. |
| DGSA annual report (ADR 1.8.3) | Aggregation across the history. Fine on either engine — it needs the history to exist, and a retention period. |
| Audit log | The only item that writes continuously and grows without a natural bound. Still within SQLite; the first to need pruning. |
| Kubernetes, one pod | Nothing. A chart, a pod and a persistent volume; SQLite underneath is fine. Only high availability across replicas would force the engine, and that is not a goal — see below. |
| Native installation without Docker | Argues *for* SQLite: no second service to install and keep running. |
| Plugins and a community hub | Once third parties touch schemas, a documented migration path becomes a compatibility contract rather than a convenience. |
| eFTI/JSON export, EDI, QR code, branding | Read-side or JSON. No pressure on the database. |

### How large the database actually becomes

Storing shipments is what turns a two-megabyte file into an operational one, and the
size depends entirely on a design choice that has not been made yet: whether a stored
shipment keeps its **computed answer** or only its **input**.

Measured through the API the wizard calls (`/api/dg/compliance`, three dangerous goods
lines):

| Stored | Measured size |
|---|---|
| Consignment fields (consignor, consignee, route, reference, …) | 489 bytes |
| Parsed and calculated goods, three lines | 2.9 kB |
| Compliance answer, three lines, one profile (ADR) | 11.4 kB |
| Compliance answer, three lines, four profiles (ADR/RID/ADN/IMDG) | 28.6 kB |

At five-year retention and the top of the stated installation size — say 200 shipments
per working day, 250 working days, five years, so 250 000 shipments — that is roughly
**1 GB** if only the input is kept and recomputed on open, and roughly **8 GB** if the
computed answer is kept alongside it.

Both are far inside what SQLite handles. But eight gigabytes in a single file changes
the operational picture rather than the performance one: backups, `VACUUM`, and the fact
that everything lives or dies as one file.

There is a real tension in that choice, and it is regulatory rather than technical.
Recomputing on open is smaller and always current — but a document that was issued under
ADR 2025 must stay reproducible after ADR 2027 lands, and a shipments page that silently
answers differently than the paper that was signed is worse than one that stores more.
The likely answer is to store the input *and* the answer, with the editions the answer
was computed against, which the compliance response already names. That is a decision
for the privacy-levels plan, not for this one — but it is the decision that sets the
size.

### Concurrent users are not what SQLite struggles with

This is worth stating plainly, because it is the usual reason people reach for a
client/server database and it does not apply here. What matters to SQLite is not how many
people are using the application but **how many processes write the file**. Today that is
exactly one: the single uvicorn server. Whether three or two hundred people are on it,
one process serialises the writes internally, which is the case SQLite is good at.

The load ceiling for a company of fifty to two hundred employees is not the database
either. The 28.6 kB compliance answer measured above is **computed**, not fetched, and so
are the PDFs. Twenty people pressing "check" at the same time spend CPU in the compliance
engine and the document exporters. No database engine changes that.

### What breaks first when you scale up

Not the database. The likely first step towards more capacity is more worker processes in
the same container (`--workers`), and three pieces of process-local mutable state break
there before SQLite does — each worker would serve a different answer:

- `app/api/routes/updates.py` — `_cache`, the update-check result
- `app/services/catalog_sync/service.py` — `_status`, the sync progress
- `app/services/assistant/runtime.py` — `_download`, the model download progress

A user starting a model download on worker 1 and asking for its progress on worker 3 is
told nothing is running. Sessions are the one thing already fine: they are stateless JWTs.

SQLite itself survives that step, provided the file is on a **local** filesystem — that is
what its locking is for. Where it genuinely cannot go is a *network* filesystem shared
between machines, because the locking there is not reliable. So the rule is: several
processes on one host is fine, several hosts sharing one volume is not.

## Decisions taken

Four questions were put and answered before this plan was written:

| Question | Answer |
|---|---|
| Kubernetes with multiple replicas, or does one pod suffice? | **One pod. Runnable on Kubernetes, not highly available** |
| PostgreSQL as an option beside SQLite, or a replacement? | **An option beside SQLite** |
| Largest realistic installation | **A company of 50–200 employees** |
| Retention for stored shipments | **Five years**, matching DGSA practice |

The goal behind those answers is that EMCargo should install easily on the common
platforms and be **manageable** by a company of that size. That is the honest argument for
PostgreSQL here, and it is worth separating from the one usually given: not that SQLite
cannot keep up — it can, by three orders of magnitude — but that an IT department already
running PostgreSQL has backup, monitoring, restore and retention in place, `pg_dump` is a
known quantity, and eight gigabytes in a single file is one thing that lives or dies
whole. Capacity is not the reason. Operability is.

Which is why PostgreSQL becomes the **recommended** choice at that size, and SQLite stays
the default: the Unraid, home-server and native-installation audiences should not gain a
second service for a problem they do not have — and a database that has to be installed
first is the opposite of installing easily on the common platforms.

## The plan

### Stage A — the foundation, engine independent

This is the work that has to happen whatever engine an installation runs, and nothing
else on this page should start before it.

1. **Adopt Alembic properly.** An `alembic.ini`, an `env.py` that reads
   `settings.database_url` and `Base.metadata`, and a baseline revision describing the
   twelve tables as they stand. Existing installations are `stamp`ed at the baseline on
   first start; new ones run `upgrade head`. `create_all` and `migrate_equipment_columns`
   are only removed once the baseline demonstrably produces the same schema, tested in
   both directions.
2. **Replace `docs/development.md#the-schema-runner` (done in v1.173.0)** with how to write a
   migration. The JSON-document trick for settings stays — it is still right for
   preferences — but it stops being the only answer.
3. **One `conftest.py` with a single database fixture.** As long as 24 test files
   hard-code their own `sqlite:///` engine, the suite can never be pointed at a second
   engine, and stage C is impossible.
4. **Backup and restore.** A documented, consistent copy — `VACUUM INTO` for SQLite,
   not a file copy of a live database. This is missing entirely today, and with stored
   shipments and a five-year retention it stops being optional.

### Stage B — configure SQLite properly

Enable WAL and set `busy_timeout` explicitly on connect. Small, self-contained, and it
buys the whole privacy-levels phase without touching the engine choice. Worth pairing
with a startup log line that names the journal mode, so an installation's behaviour is
visible rather than inferred.

### Stage C — PostgreSQL as a supported choice

Add `psycopg`, run the test suite in CI against a PostgreSQL service *as well as*
SQLite, ship a compose profile and document the switch. The value is not that anyone has
to move: it is that every schema change from here on is proven on both, so moving is
never a rebuild. This is the stage that makes PostgreSQL the recommended engine for a
company-sized installation. Two things to watch as the matrix goes green:

- `DateTime(timezone=True)` is a genuine behavioural difference — SQLite stores what it
  is given, PostgreSQL stores `timestamptz`. Anything comparing timestamps needs a test
  that runs on both.
- The `Text`-with-JSON columns work on both, but PostgreSQL would want `JSONB` if those
  fields ever need to be filtered rather than read whole. Decide that when a filter
  actually needs it, not in advance.

### Stage D — moving between engines, and scaling within one pod

Not a cluster track. High availability across several replicas is explicitly **not** a
goal: one pod on Kubernetes is the target, and a rolling update taking the service away
for a few seconds is acceptable for a documentation tool. Two things remain:

1. **A migration path between engines** — export and import, verified by round-tripping a
   real database rather than by asserting that it should work. Worth building even for
   installations that never move: an export that is exercised on every release is also the
   honest answer to "how do I get my data out", which a self-hosted application owes its
   users.
2. **The three process-local caches**, moved to shared state or made per-request. This is
   the prerequisite for running more than one worker process in the pod, which is the
   realistic next step for capacity — and it is needed before anyone reaches for
   `--workers`, because those caches break there while SQLite does not.

If high availability ever does become a goal, it needs PostgreSQL, item 2 above, `/data`
split into what must be shared and what may be per-pod, and an update route that is not
the Docker socket. That is a different plan, and this one does not assume it.

## Still open

- Whether a stored shipment keeps its computed answer, its input, or both — the
  decision that sets the database size, and one for the privacy-levels plan.
- Whether the five-year retention is enforced by a pruning task, offered as an archive
  export first, or both.
- Whether the audit log shares the database or gets its own store; it is the only
  append-only, unbounded writer in the plan.

## One thing found along the way

`backend/alembic/env.py` carries a **Dutch** docstring and escapes both language guards:
`test_source_language.py` does not include `alembic/` in its scopes. If Alembic comes
into real use under stage A, that directory has to join `SOURCES` and the docstring has
to be rewritten in English.
