# The shell: one screen instead of four steps of furniture

> Historical design/research notes. For the current interface and setup, use the
> [user guide](user-guide.md), [configuration](configuration.md) and
> [design verification notes](design/README.md).

*A second plan, after [the usability plan](ux-plan.md) was measured to its end. That one
made the work cheaper — 83 actions became 53 and the two impossible tasks became possible.
This one is about where the work **sits**: the frame around it, which is still the frame of
2024 with eleven releases bolted onto it.*

## Where it comes from

A set of mockups, drawn from scratch rather than from the existing screens. They are not
adopted as a design — the colours, the button shapes and the exact wording stay EMCargo's
— but as a **layout**, and the layout is right in four ways this application is not yet.

## What is already built, and only badly placed

Most of it. This matters, because it decides how much of the plan is risk and how much is
rearrangement:

| In the mockup | In EMCargo today |
|---|---|
| *Concept • automatisch bewaard* under the title | v1.199.0 — kept as a draft, with an honest saved/saving/failed |
| **Plakken uit Excel** / **Bestand kiezen** on the goods panel | v1.194.0 — the same two, in the panel body |
| A status per goods line (*Gereed* / *Te controleren*) | v1.193.0 — the same two words, in a table column |
| The substance question on the line, with two named answers | v1.195.0 — the same question, three answers |
| Third step called **Controleren** rather than *Export* | v1.199.0 — the export step opens with check-your-answers |
| *1 aandachtspunt* counted where the user can act on it | v1.194.0 — counted above the goods list |
| Shipments with a state and an action per row | v1.200.0 — draft / still to complete / ready, with three actions |

## What is genuinely new

1. **A shell that carries the shipment.** Title, draft status, the three steps and the
   transport mode in one header instead of four stacked strips; a rail with icons; a fixed
   action bar at the foot that never covers a field or an error. Release 118 promised that
   bar and did not build it.
2. **A goods line that opens.** The row carries description, quantity, weight and state; it
   *expands* into everything that is now behind **Details** and, for a dangerous line, into
   the UN number, the proper shipping name and the packing group. The mockup's stepper has
   three steps because the substance is answered where the substance is.
3. **A panel that keeps count.** Lines, weight, attention points and *the documents we are
   preparing*, standing beside the work rather than waiting at the end of it.
4. **A place to come back to.** *Verder waar je gebleven was*, today's counts, a quick start,
   and the recent shipments — the first screen for somebody who is continuing rather than
   starting.

## What is deliberately not taken

**The percentage.** The mockup says *Herkenning 96%*. There is no 96% to print: the
recogniser ranks candidates (an exact UN number, a name the entry starts with, a word that
starts with the text, a substring) and that rank is an order, not a probability. Printing a
number that looks measured and is not is the one thing this project does not do. The banner
stays; it says what matched, not how confident a machine feels.

**The colours and the components.** They stay EMCargo's, in both themes.

## Two decisions, and why

**The dangerous-goods step stays — and usually will not appear.** The substance's identity
(UN, name, packing group, packing) moves onto the line, where the mockup puts it. What
cannot live on a line stays a step of its own: the compliance assessment, the tunnel
restriction, mixed loading, the equipment list, the 1.1.3.6 exemption calculation. That step
appears when there is something to assess and not otherwise, so the common shipment is the
mockup's three steps and a difficult one is honest about being four.

> **Corrected while building it (v1.203.0).** The second half of that promise was already
> kept and the first half cannot be. The step has appeared only for a shipment with
> dangerous goods since long before this plan, so a shipment without them is three steps
> today. And for a shipment *with* them there is always something to assess — the
> compliance check, the tunnel code, the transport category, mixed loading — so a rule
> that hid the step would hide work that has to be done. What 120 actually changes is that
> the step no longer asks the identity a second time: the UN number, the proper shipping
> name, the packing group and the packaging are answered on the line and seeded into the
> step's product.

**The overview gets its own address, and nothing is moved out of the way for it.**
[The usability plan](ux-plan.md) says in as many words: recent shipments as templates
*without sending somebody with a default mode through a dashboard first*. Putting the
overview on `/` would do exactly that — today `/` is the transport-mode chooser, and it
already sends somebody with a preferred mode straight into the wizard without a stop. So:

- **`/` keeps doing what it does.** The chooser with its transport-mode tiles stays, images
  and all, including the ones an installation replaced with its own (v1.172.0), and
  including the redirect that skips it for somebody who always ships the same way.
  **Andere modaliteit kiezen** (`/?choose=1`) still brings the tiles back.
- **The overview lives at `/overzicht`**, first in the rail, for whoever wants to start the
  day there. Nobody is sent through it.
- The transport mode in the wizard's header is a *switcher*, not the chooser: it changes
  the mode of the shipment you are already entering. Choosing where to begin, and changing
  your mind halfway, are two different acts and keep two different places.

## The releases

| # | Release | What it changes |
|---|---|---|
| 119 | The shell — **built, v1.202.0** | One header (title, draft state, steps, mode switcher), an icon rail that folds to 56px instead of to nothing, one action bar at the foot; the same on a phone |
| 120 | A line that opens — **built, v1.203.0** | Row expands into details and, for a dangerous line, the substance itself; the dangerous-goods step keeps the assessment and stops asking the identity twice |
| 121 | The panel that counts — **built, v1.204.0** | Lines, weight, volume, attention and the documents being prepared, beside the work on every step |
| 122 | Somewhere to come back to — **built, v1.205.0** | The overview at `/overzicht`: continue where you left off, today's counts, quick start, recent shipments. Nothing else moved |
| 123 | Measured and trimmed — **done, v1.206.0** | The ten tasks again, two more that reach what the shell changed, and the phone measurement the first plan left open |

### What 119 turned out to be, once measured

Two things the plan said were not quite true, and both were found by looking at
the screen rather than at the code.

**"A fixed action bar that never covers a field or an error" cannot be had for
free.** The bar is `sticky bottom-0`, which is the right choice and does the
thing that matters: it stays in the layout, takes its own height at the end of
the page, and therefore leaves nothing permanently underneath it — which is
exactly what a `fixed` bar does to the last row of a long form and to the error
standing beside it. What it does not do is never overlap at all. Measured at
390×844 on the goods step, the bar floats over the panel while you are scrolled
above its resting place, the way every bar of this kind does. That overlap is
one scroll away; the other one has no scroll position that reveals it. The
code, the test and this line all say that now, instead of the stronger claim.

**One header meant two rows, not one.** A single wrapping row put the title in
a flex line with the draft state and the mode switcher, and on a phone that
left the title twenty pixels: a shipment called *N…*. The title now has a row
of its own at every width.

### What 120 turned up

**Two things on the open panel disagreed with the row above it.** The
calculation marks a line dangerous when it reads a UN number in the
description, and the row says so — but the panel's dangerous-goods tick read
only what the user had set, so it stood empty next to a row saying the
opposite. It follows the calculation now until somebody sets it themselves.
And the UN number the recogniser had already found was not in the UN field:
it stands there as the placeholder, because it is what the next step will
start from and it is not something anybody has stated yet.

### What 121 had to decide

**Where a panel can stand without taking width off the goods list.** The rail's
own comment records that the lines table wants 1,620px, which is why the rail
folds when the wizard opens — so an 18rem column beside it looks like a
contradiction. It is not, because since v1.193.0 the list is a row of fields
that *wraps* rather than a table with fixed columns: 1,620px is what it uses
happily, not what it needs. Measured at 1440 with the panel beside it, the row
is still one line. So the panel is a sticky right-hand column from `xl` up, and
below that it goes back to being what the four counts always were — a card
above the list.

**One count in one place at a time.** The action bar's attention count and the
panel's are the same number. From `xl` the panel is on the screen and carries
it and the bar's is hidden; below that there is no panel beside the work and
the bar says it. Two live counts of the same thing on one screen is two things
to reconcile.

### What 122 kept as it was

**`/` is untouched, and that was checked rather than assumed.** The chooser
still has its six tiles with their pictures, the two locked ones with their
reasons, and the redirect that takes somebody with a preferred mode straight
into the wizard. The overview is at `/overzicht`, first in the rail for
whoever wants to start their day there, and nobody is sent through it.

**It is honest about an installation that stores nothing.** Where the history
is off there is no draft, no count and no recent shipment, so the page says so
in one sentence and shows the quick start alone — rather than four empty boxes
— and asks the server for nothing. The rail leaves the link out entirely
there, the way it already does for the shipments page.

**Today is counted by the server.** Two queries with a date filter, read for
their totals, rather than a page of results counted in the browser: a total is
a total, and a number assembled out of the first fifty rows would quietly stop
being one at the fifty-first.

## How it is judged

The same way as the first plan, with the same harness: [`scripts/ux_bench`](../scripts/ux_bench/README.md)
against the same ten tasks, reported in [the baseline](ux-baseline.md), plus — this time —
a phone-sized viewport, which the first plan recorded as not run. A release that makes a
screen prettier and a task no cheaper is a release that has to say so.

## Where the second plan ended

Run the same way as the first, and reported in [the baseline](ux-baseline.md).

**The ten tasks cost exactly what they cost before it: 53 actions, no windows, all
finished.** For four releases that moved nearly every piece of furniture on the screen,
that is the outcome worth having — nothing got cheaper and, more to the point, nothing got
dearer.

What the shell *did* change needed two tasks the first plan never had, because none of its
ten opens a goods line's details or comes back to an interrupted entry from outside the
wizard. Both were run against the v1.202.0 build as well as this one:

- **Filling in one measurement on a goods line: 6 actions and a window became 5 and none.**
  The window was worth an action all by itself — with the dialog open, the list underneath
  could not be reached until it was dismissed.
- **Getting back into an interrupted entry: the same four presses, and the count is not the
  point.** The chooser offers four modes and marks none of them as yours; the overview
  names the one your entry is in. That is the whole change and it does not appear in an
  action count at all.

**And the phone was run**, which the first plan recorded as not run: every task finishes at
390×844, at the same cost as on a laptop, except getting back into an entry — one press
more, because the rail is behind the hamburger.

The run found one defect in the application: on a phone the shipments list offered five
identical *Select* boxes, because only the table's checkbox carried its shipment's
reference as its name and a phone shows the cards. Both carry it now. It also found the
harness measuring less than it claimed — it could not read the step pills on a phone, where
they are icons with an accessible label and no text, and it looked for the selection inside
a `<table>` that a phone does not have.
