"""The measuring harness for the usability plan.

Every task is driven through the real interface in a real browser and counts
what the person doing it would have to do: an action is a click, a value typed
into a field, or a key pressed to move on. A window is a modal opening. A step
change is a move between the wizard's main steps, and a back-step is one that
goes to an earlier one. Repeated entry is the same value typed into more than
one field inside one task.

What this cannot measure is said so: it does not know how long somebody thinks,
and a task the harness could not complete is reported as not completed rather
than as zero.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

import requests

#: Where the application under measurement is answering, and where the run
#: writes its numbers and screenshots. Both can be pointed elsewhere.
BASE = os.environ.get("EMCARGO_BENCH_URL", "http://127.0.0.1:8765")
OUT = Path(os.environ.get("EMCARGO_BENCH_OUT", "bench-out"))
#: Playwright finds its own browser unless one is named here.
CHROME = os.environ.get("EMCARGO_BENCH_CHROME") or None


@dataclass
class Measurement:
    task: str
    title: str
    actions: int = 0
    windows: int = 0
    step_changes: int = 0
    back_steps: int = 0
    repeated_entry: int = 0
    #: Forms crossed inside the document-fields step, which the main step
    #: counter cannot see. It was the shared fields and then one form per
    #: document; since v1.197.0 the step is one page of question groups, so a
    #: task that crosses it once counts one.
    sub_steps: int = 0
    seconds: float = 0.0
    completed: bool = True
    #: What the run showed beyond the counters — the finding, in one line each.
    notes: list[str] = field(default_factory=list)
    #: What came out, when the task produces something: file names, contents.
    output: dict = field(default_factory=dict)


class Bench:
    """One task's run, with the counting built into the interaction."""

    def __init__(self, page, task: str, title: str):
        self.page = page
        self.m = Measurement(task=task, title=title)
        self._typed: list[str] = []
        self._step = ""
        self._started = time.time()

    # --- the counted interactions ---------------------------------------------

    def click(self, locator, note: str = "") -> None:
        try:
            locator.click(timeout=8000)
        except Exception:
            # A standing snackbar sits over the bottom right of every screen and
            # takes the pointer. A person moves it aside or scrolls; the harness
            # clicks through, and counts the click once either way.
            locator.click(force=True, timeout=8000)
            self.m.notes.append("a standing snackbar covered the action and had to be clicked through")
        self.m.actions += 1
        self._settle()

    def fill(self, locator, value: str) -> None:
        locator.fill(value)
        self.m.actions += 1
        text = value.strip()
        if text and text in self._typed:
            self.m.repeated_entry += 1
        if text:
            self._typed.append(text)
        self._settle()

    def press(self, key: str) -> None:
        self.page.keyboard.press(key)
        self.m.actions += 1
        self._settle()

    def note(self, text: str) -> None:
        self.m.notes.append(text)

    # --- the observations ------------------------------------------------------

    def _settle(self, ms: int = 350) -> None:
        self.page.wait_for_timeout(ms)
        self.observe()

    def observe(self) -> None:
        """Record a window that opened and a step that changed."""
        dialogs = self.page.locator("[role=dialog], [role=alertdialog]")
        if dialogs.count() and dialogs.first.is_visible():
            if not getattr(self, "_dialog_open", False):
                self.m.windows += 1
                self._dialog_open = True
        else:
            self._dialog_open = False

        step = self.current_step()
        if step and step != self._step:
            if self._step:
                self.m.step_changes += 1
                if STEP_ORDER.get(step, 99) < STEP_ORDER.get(self._step, 0):
                    self.m.back_steps += 1
            self._step = step

    def current_step(self) -> str:
        """Which main step the wizard shows as active, by its own pill.

        On a narrow screen the pills are icons, so there is no visible text to
        read — the name is on the element as its accessible label instead, and
        that is what a screen reader is given. Reading only the text made every
        phone measurement report "unknown" and mark two tasks unfinished that
        had in fact finished."""
        try:
            active = self.page.locator("li[aria-current=step]")
            if not active.count():
                return ""
            text = active.first.inner_text().strip()
            if not text:
                labelled = active.first.locator("[aria-label]")
                if labelled.count():
                    text = (labelled.first.get_attribute("aria-label") or "").strip()
            for label in STEP_ORDER:
                if label in text:
                    return label
            return text.split("\n")[-1]
        except Exception:
            pass
        return ""

    def sub_step(self) -> str:
        """Which form of the document-fields step is showing, by its heading."""
        try:
            heading = self.page.locator("h3, h2").first
            return heading.inner_text().strip() if heading.count() else ""
        except Exception:
            return ""

    def shot(self, name: str) -> None:
        self.page.screenshot(path=str(OUT / f"{self.m.task}-{name}.png"), full_page=False)

    def done(self, completed: bool = True) -> Measurement:
        self.m.seconds = round(time.time() - self._started, 1)
        self.m.completed = completed
        return self.m


#: The wizard's main steps, in order, by the label their pill carries.
STEP_ORDER = {"Goederen": 0, "Gevaarlijke stoffen": 1, "Zendinggegevens": 2, "Export": 3}


def sign_in() -> requests.Session:
    session = requests.Session()
    answer = session.post(f"{BASE}/api/auth/login", json={
        "username": os.environ.get("EMCARGO_BENCH_USER", "root"),
        "password": os.environ.get("EMCARGO_BENCH_PASSWORD", "Root-pass-123")})
    assert answer.status_code == 200, answer.text
    return session


def history(session: requests.Session, on: bool) -> None:
    current = session.get(f"{BASE}/api/settings/instance").json()
    session.put(f"{BASE}/api/settings/instance", json={**current, "history_enabled": on})


def browser(playwright, session: requests.Session, width: int = 1440, height: int = 900):
    engine = (playwright.chromium.launch(executable_path=CHROME) if CHROME
              else playwright.chromium.launch())
    context = engine.new_context(viewport={"width": width, "height": height},
                                 accept_downloads=True, locale="nl-NL")
    context.add_cookies([{"name": c.name, "value": c.value, "domain": "127.0.0.1", "path": "/"}
                         for c in session.cookies])
    return engine, context


def dismiss_toasts(page) -> None:
    """Clear whatever is standing before a task starts, so its own count is its own."""
    closers = page.locator(".fixed.inset-x-0.bottom-0 button[aria-label]")
    for _ in range(closers.count()):
        try:
            closers.nth(0).click()
            page.wait_for_timeout(150)
        except Exception:
            break


def write(measurements: list[Measurement], name: str = "baseline") -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.json").write_text(
        json.dumps([asdict(m) for m in measurements], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")
    rows = ["| Task | Actions | Windows | Steps | Forms | Back-steps | Repeated | Completed |",
            "|---|---|---|---|---|---|---|---|"]
    for m in measurements:
        rows.append(f"| {m.task} {m.title} | {m.actions} | {m.windows} | {m.step_changes} "
                    f"| {m.sub_steps} | {m.back_steps} | {m.repeated_entry} "
                    f"| {'yes' if m.completed else 'no'} |")
    (OUT / f"{name}.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
    print("\n".join(rows))
    for m in measurements:
        for line in m.notes:
            print(f"  [{m.task}] {line}")
