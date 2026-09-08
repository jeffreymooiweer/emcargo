# The usability plan

> Historical design/research notes. For the current interface and setup, use the
> [user guide](user-guide.md), [configuration](configuration.md) and
> [design verification notes](design/README.md).

*Twelve releases that make the daily work measurably simpler, in the order the work
has to happen. Written against v1.191.0 from an external UX review of v1.189.0,
checked claim by claim against the code before a line of it was accepted.*

## What this is for

The measure is the time to a correct document set, with the checking intact. Fewer
keystrokes is not the goal on its own: an extra step somebody understands beats an
automatic decision they cannot see. Nothing here removes a regulatory check to reach
a click target.

The shipment is the working object. The user says what is carried and where to;
EMCargo reuses what it already knows, asks only what is still missing, explains the
document choice, and produces a complete package.

## What stays

Recalculating after every change, the conditional dangerous goods step, shared document
fields, the address and article lookups, a kept shipment as the basis for a new one, the
document advice, the bundle download, and the assistant. These work; the plan connects
them. A new button for something that already happens by itself is not an improvement.

Two shapes are deliberately not coming back or being invented:

- **The thirteen-column table.** The wide goods table was removed on purpose. Inline
  editing means a small set of core fields, with the same validation as the cards.
- **A planner.** The groupage check is about dangerous goods. Selecting shipments into a
  trip is not permission to build route optimisation.

## The twelve releases

| # | Release | What it does |
|---|---|---|
| 107 | The baseline | The ten tasks measured in a browser before anything changes |
| 108 | Goods, edited where they are | Description, quantity and unit inline on a laptop; focus on a new line |
| 109 | Import as an entrance | Paste from Excel and Choose file on the goods step itself |
| 110 | Substance questions at their line | Explicit answers instead of a toast whose close button decides |
| 111 | From the problem to the field | One action from "2 details still needed" to the field that needs them |
| 112 | Questions grouped by meaning | Parties, route, additions — not one form per document |
| 113 | The document advice, in time | What is being prepared, and why, before the fields are filled in |
| 114 | The export step as a check-your-answers | One summary, one finishing action |
| 115 | Drafts | Resuming after a reload, where the installation's policy allows it |
| 116 | Reuse from the list | Edit, download again and use as basis without the detail page |
| 117 | A trip from a selection | Five shipments into one trip in one action |
| 118 | Quiet navigation and accessibility | Menu groups, units, focus, mobile |

Releases 108 to 111 come first and are finished before the wider structures of 112 to
117 begin: they take away recurring work without a rebuild, so a later structural change
lands on a screen that already behaves.

## What each release changes

### 107 — The baseline

The ten tasks from the assignment, driven in a real browser against the unchanged
application, recorded in [The usability baseline](ux-baseline.md): actions, extra
windows, back-steps, repeated entry, and the content of the produced PDF, JSON and EDI.
No product change. Every release after this repeats the tasks it touches and reports the
difference — measured, never estimated.

### 108 — Goods, edited where they are

On a laptop the goods lines carry description, quantity, unit, total weight and status
as fields, not as a card that opens a dialog. Dimensions, source and exceptions stay in
the detail dialog. A new line puts the cursor in its description; Enter makes the next
one. On a phone the cards stay, with the quantity editable in place.

The description drives the weight recognition, so it commits when the field is left, not
on every keystroke, and the line says *to be rechecked* until the recalculation has run.

### 109 — Import as an entrance

**Paste from Excel** and **Choose file** on the goods step, dragging optional. The same
parser and column recognition; a column question only where there is real doubt. An
empty shipment does not ask whether to add or replace. Replacing existing lines is
explicit and undoable. Refused rows are shown with their reason.

### 110 — Substance questions at their line

The recognition question moves from a floating `toast.ask` to the line it belongs to,
and to a **To assess** overview. Three answers: confirm the UN number, choose another
substance, or reject the suggestion. Closing or collapsing decides nothing — until
v1.191.0 the close button set `dg_dismissed`, which made "not now" mean "not dangerous".
Rejecting one candidate is not a finding that the goods are harmless. Undecided
questions stay visible into the document check.

### 111 — From the problem to the field

Field identity from the document registry becomes a navigation target. Visited main
steps become reachable from the progress bar. Each missing detail gets one action that
opens its step, its sub-step and its field, focuses it, and returns to the overview
afterwards. Concrete errors appear on **Next**, not while somebody is halfway through
typing a number. Server validation stays the authority.

### 112 — Questions grouped by meaning

Shipment details become **Parties**, **Route** and **Additions**, built from the same
registry sections as today. A document without questions of its own adds no step.
Completed groups collapse to a summary with **Change**.

### 113 — The document advice, in time

Once there is enough context: *these are the documents we are preparing*, with a short
reason each, from the advice that already decides the preselection. JSON and IFTDGN move
to a recognisable **Integration** group. Choosing an extra document leads to its new
questions and nothing else. No legal rule is invented for a label.

### 114 — The export step as a check-your-answers

A summary of the shipment, the document language, the assessments and the exact package
contents, then one primary action that finishes the job — with one document as with
five. Separate downloads, preview, mail and the integration formats are secondary. A
partial package is called partial and says what is missing. Having a document is not
having sent it.

### 115 — Drafts

A draft is not a checked shipment. Where the history is on, the running entry is kept as
a draft with an honest *Saved* / *Saving* / *Could not save*, and a reload returns the
user to the shipment and the step they were on. In the open application and with the
history off nothing is stored: there the user is warned before leaving, and can download
the draft as a file. This is the one release with a schema step and backend work.

### 116 — Reuse from the list

**Edit**, **Download again** and **Use as basis** directly on the shipments list, with
draft / needs information / ready distinguishable. A copy gets a new identity and drops
what belongs to the old shipment: its reference, its date, its signature and its
dangerous goods confirmations. Recent shipments as templates on the first wizard step —
without sending somebody with a default mode through a dashboard first.

### 117 — A trip from a selection

Multiple selection on the shipments list with **Add to trip**, opening the groupage
check with that selection filled in. Authorisation stays server-side per shipment, and
the same shipment cannot be added twice. File import stays as the alternative.

### 118 — Quiet navigation and accessibility

Menu groups — work, libraries, administration, account — with every existing URL still
working. Available transport modes first. Words on the buttons that matter. One notation
for per-package values, totals and units, with derived, hand-changed and to-be-rechecked
distinguishable. Focus order, real labels, dialog focus and its return, and a fixed
action bar that never covers the field or the error. Accessibility is not saved up for
here: it is part of 108 to 117 as they are built.

## Where it ended

All twelve releases are built and published: 107 (the baseline) through 118, in v1.192.0 to
v1.200.0. The closing measurement is at the foot of [the baseline](ux-baseline.md): across
the ten tasks, 83 actions became 53, eleven extra windows became none, and the two tasks
this plan started out unable to complete — a substance suggestion revisited, and a reload
during entry — now complete.

What this plan deliberately did not do is listed where it belongs rather than here: the
mobile measurements beyond release 108, and the accessibility work that release 118 says is
part of every release rather than a release of its own, are carried in the baseline's
*What was not run*.

## How each release is judged

Every release repeats the baseline tasks it touches and reports what actually changed —
actions, windows, back-steps, repeated entry — and compares the *content* of the produced
files, not their hashes: the same quantities, units, weights, UN data, references and
attachments. A timestamp differs on every run; that is not a difference in the shipment.

What a script cannot measure is said as much. It counts actions and windows; it does not
know how long a person takes to think. Source reading is not observed behaviour, and a
task that was not run in a browser is reported as not run.

## The conditions that do not move

The confirmed fixes of v1.190.0 — the department's trips, the quantities, the IFTDGN
content, the second factor, the export download — and the upgrade of v1.191.0 are
release conditions, not things to be traded against a smoother screen. The privacy
promise of the open application and of the history switch holds throughout: no silent
browser or server storage is added anywhere in this plan.
