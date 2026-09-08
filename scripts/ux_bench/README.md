# The usability bench

The instrument behind [The usability plan](../../docs/ux-plan.md): the ten tasks of the
plan, driven through the real interface in a real browser, counting what the person
doing them would have to do. Every release of the plan reruns the tasks it touches and
compares against [the baseline](../../docs/ux-baseline.md), so "faster" is a measurement
and not an estimate.

## What it counts

| Counter | What it means |
|---|---|
| Actions | Clicks, values typed into a field, keys pressed to move on |
| Windows | Modal dialogs that opened |
| Steps | Moves between the wizard's main steps |
| Forms | Forms crossed *inside* the shipment-details step, which the step counter cannot see |
| Back-steps | Moves to an earlier step |
| Repeated | The same value typed into more than one field within one task |
| Completed | Whether the task could be finished at all |

Each task also leaves notes — what it found rather than what it counted — and
screenshots, and where a task produces a document its content is kept for comparison.

**What it does not measure:** how long a person takes to think. The seconds it records
are the harness's own, useful only for spotting a task that got slower to drive. A task
the harness cannot complete is reported as not completed, never as zero.

## Running it

The application has to be running with its built frontend served from `backend/static`,
and reachable at the URL below. Then:

```bash
pip install playwright requests && playwright install chromium
cd scripts/ux_bench
EMCARGO_BENCH_OUT=../../bench-out python tasks.py        # all ten tasks
EMCARGO_BENCH_OUT=../../bench-out python one.py task_3   # one of them
```

It writes `baseline.json` and `baseline.md` next to the screenshots in the output
directory.

| Variable | Default |
|---|---|
| `EMCARGO_BENCH_URL` | `http://127.0.0.1:8765` |
| `EMCARGO_BENCH_OUT` | `bench-out` |
| `EMCARGO_BENCH_USER` / `EMCARGO_BENCH_PASSWORD` | `root` / `Root-pass-123` |
| `EMCARGO_BENCH_CHROME` | Playwright's own browser |

**Not at the same time as the backend suite.** The run copies the built frontend into
`backend/static` so the application it drives serves the interface. While that directory
exists, FastAPI has a catch-all route for the single-page app, and a handful of tests
that expect a 404 from an unmounted address get a 405 instead. Run one, then the other.

The tasks drive the Dutch interface, because that is the language the labels are
matched on. They need an installation with the shipment history switched on; the run
switches it on itself and seeds a handful of earlier shipments for the tasks that reuse
one. Point it at a scratch installation, never at one holding real consignments.
