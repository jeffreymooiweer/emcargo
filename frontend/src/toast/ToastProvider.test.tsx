/**
 * The toast lifetimes are the contract, so the tests pin them: a success
 * leaves on its own, an error never does, and an undoable delete really is
 * deferred — the API call fires when the window closes and never fires when
 * the undo is taken. Those last two are the difference between "undo" as a
 * UI flourish and undo as a promise.
 */
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { INLINE_ACTION_MAX_CHARS, INLINE_ACTION_MAX_LABEL, ToastProvider, useToast, type ToastApi } from "./ToastProvider";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "nl" },
  }),
}));

/** Hands the api out of the tree so a test can drive it directly. */
function Grab({ onApi }: { onApi: (api: ToastApi) => void }) {
  onApi(useToast());
  return null;
}

function setup() {
  let api: ToastApi | null = null;
  render(
    <ToastProvider>
      <Grab onApi={(a) => (api = a)} />
    </ToastProvider>,
  );
  return () => {
    if (!api) throw new Error("ToastApi not captured");
    return api;
  };
}

/** Every icon on screen must take its colour from the toast around it and its
 *  size from the interface — both fail invisibly until the theme flips. */
function expectIconsInherit() {
  const icons = document.querySelectorAll("svg");
  expect(icons.length).toBeGreaterThan(0);
  icons.forEach((icon) => {
    expect(icon.getAttribute("stroke")).toBe("currentColor");
    expect(icon.hasAttribute("width")).toBe(false);
    expect(icon.hasAttribute("height")).toBe(false);
    expect(icon).toHaveAttribute("aria-hidden");
  });
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
});

afterEach(() => {
  vi.useRealTimers();
});

describe("ToastProvider", () => {
  it("a success dismisses itself after four seconds", async () => {
    const api = setup();
    act(() => void api().success("saved"));
    expect(screen.getByText("saved")).toBeInTheDocument();
    act(() => void vi.advanceTimersByTime(4100));
    await waitFor(() => expect(screen.queryByText("saved")).not.toBeInTheDocument());
  });

  it("an error stays until it is closed by hand", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const api = setup();
    act(() => void api().error("boom"));
    act(() => void vi.advanceTimersByTime(60000));
    expect(screen.getByRole("alert")).toHaveTextContent("boom");
    await user.click(screen.getByRole("button", { name: "toast.dismiss" }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("a loading toast follows its action: progress, then the outcome", async () => {
    const api = setup();
    let handle!: ReturnType<ToastApi["loading"]>;
    act(() => {
      handle = api().loading("working");
    });
    // No timer closes it.
    act(() => void vi.advanceTimersByTime(60000));
    expect(screen.getByText("working")).toBeInTheDocument();
    // And it carries no dismiss button: only its outcome may close it.
    expect(screen.queryByRole("button", { name: "toast.dismiss" })).not.toBeInTheDocument();
    act(() => handle.progress("still working"));
    expect(screen.getByText("still working")).toBeInTheDocument();
    act(() => handle.success("done"));
    expect(screen.getByText("done")).toBeInTheDocument();
    act(() => void vi.advanceTimersByTime(4100));
    await waitFor(() => expect(screen.queryByText("done")).not.toBeInTheDocument());
  });

  it("a loading outcome stays paused when the pointer was already over its progress", () => {
    // Loading notices have no expiry, but dropping their hover state would
    // let the final result disappear while somebody is still reading it.
    const api = setup();
    let handle!: ReturnType<ToastApi["loading"]>;
    act(() => { handle = api().loading("working"); });
    const notice = screen.getByText("working").closest("[data-kind]")!;
    fireEvent.pointerEnter(notice);
    act(() => handle.progress("almost done"));
    act(() => handle.success("finished"));
    act(() => void vi.advanceTimersByTime(10000));
    expect(screen.getByText("finished")).toBeInTheDocument();
    fireEvent.pointerLeave(notice);
    act(() => void vi.advanceTimersByTime(4100));
    expect(screen.queryByText("finished")).not.toBeInTheDocument();
  });

  it("an undoable delete fires the deferred call when the window closes", async () => {
    const api = setup();
    const execute = vi.fn();
    const restore = vi.fn();
    act(() => void api().undoable("deleted", { execute, restore }));
    expect(execute).not.toHaveBeenCalled();
    act(() => void vi.advanceTimersByTime(6100));
    expect(execute).toHaveBeenCalledTimes(1);
    expect(restore).not.toHaveBeenCalled();
  });

  it("undo means the deferred call never happens", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const api = setup();
    const execute = vi.fn();
    const restore = vi.fn();
    act(() => void api().undoable("deleted", { execute, restore }));
    await user.click(screen.getByRole("button", { name: "toast.undo" }));
    expect(restore).toHaveBeenCalledTimes(1);
    // Even after the window would have closed: nothing fires.
    act(() => void vi.advanceTimersByTime(10000));
    expect(execute).not.toHaveBeenCalled();
  });

  it("dismissing an undoable toast is 'I don't need the undo': it fires now", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const api = setup();
    const execute = vi.fn();
    act(() => void api().undoable("deleted", { execute, restore: vi.fn() }));
    await user.click(screen.getByRole("button", { name: "toast.dismiss" }));
    expect(execute).toHaveBeenCalledTimes(1);
    // And only once, even when its timer would fire later.
    act(() => void vi.advanceTimersByTime(10000));
    expect(execute).toHaveBeenCalledTimes(1);
  });

  it("being pushed out by a full stack still fires the deferred call", () => {
    const api = setup();
    const execute = vi.fn();
    act(() => void api().undoable("deleted", { execute, restore: vi.fn() }));
    // Five more toasts arrive; the stack holds five, so the oldest is evicted.
    act(() => {
      for (let i = 0; i < 5; i += 1) api().info(`note ${i}`);
    });
    expect(screen.queryByText("deleted")).not.toBeInTheDocument();
    expect(execute).toHaveBeenCalledTimes(1);
  });

  it("a sticky info toast never times out, and only the × counts as dismissed", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const api = setup();
    const onDismiss = vi.fn();
    act(() => void api().info("update available", { sticky: true, onDismiss }));
    act(() => void vi.advanceTimersByTime(60000));
    expect(screen.getByText("update available")).toBeInTheDocument();
    expect(onDismiss).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "toast.dismiss" }));
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it("a stack under pressure drops the passing notes, not the ones that stay", () => {
    const api = setup();
    act(() => void api().info("update available", { sticky: true }));
    act(() => {
      for (let i = 0; i < 5; i += 1) api().success(`saved ${i}`);
    });
    // The sticky notice is the whole reason anything is on screen; "saved" is
    // gone in four seconds anyway, so it is what gives way.
    expect(screen.getByText("update available")).toBeInTheDocument();
    expect(screen.queryByText("saved 0")).not.toBeInTheDocument();
  });

  it("eviction does not count as the user dismissing a sticky notice", () => {
    const api = setup();
    const onDismiss = vi.fn();
    act(() => void api().info("update available", { sticky: true, onDismiss }));
    // Only sticky toasts competing: now the oldest does have to give way, and
    // that still is not the user saying they read it.
    act(() => {
      for (let i = 0; i < 5; i += 1) api().info(`note ${i}`, { sticky: true });
    });
    expect(screen.queryByText("update available")).not.toBeInTheDocument();
    expect(onDismiss).not.toHaveBeenCalled();
  });

  it("a question stays put and carries its answers", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const api = setup();
    const first = vi.fn();
    const second = vi.fn();
    const onDismiss = vi.fn();
    act(() =>
      void api().ask("which substance?", {
        actions: [
          { label: "UN 1830", run: first },
          { label: "UN 2796", run: second },
        ],
        onDismiss,
      }),
    );
    // Four seconds is not an answer.
    act(() => void vi.advanceTimersByTime(60000));
    expect(screen.getByText("which substance?")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "UN 2796" }));
    expect(second).toHaveBeenCalledTimes(1);
    expect(first).not.toHaveBeenCalled();
    expect(onDismiss).not.toHaveBeenCalled();
  });

  it("one short action sits beside the message, one long message puts it underneath", () => {
    // "Deleted. Undo" is a row; five lines of text with a button floating
    // top-right beside them, squeezing them narrower still, is a layout
    // accident. The threshold is a character count so the first paint and
    // this test see the same thing.
    const api = setup();
    act(() => void api().info("Deleted.", { actions: [{ label: "Undo", run: vi.fn() }] }));
    expect(screen.queryByTestId("toast-actions")).toBeNull();
    expect(screen.getByRole("button", { name: "Undo" })).toBeInTheDocument();

    const long = "Your account has no second factor yet. A password alone is one leaked reuse away from somebody else acting in your name.";
    expect(long.length).toBeGreaterThan(INLINE_ACTION_MAX_CHARS);
    act(() => void api().info(long, { sticky: true, actions: [{ label: "Set it up", run: vi.fn() }] }));
    const row = screen.getByTestId("toast-actions");
    expect(row).toContainElement(screen.getByRole("button", { name: "Set it up" }));
    // And underneath means inside the message column, not beside it.
    expect(row.previousElementSibling).toHaveTextContent(long);
  });

  it("a long action goes under a short message too", () => {
    // The rule looked at the message and forgot the action. An inline action
    // does not wrap — it takes the width its words need and the message gets
    // the rest — so beside "Bekijk de release-opmerkingen" on a phone the
    // rest was about 135px, and the notice broke mid-word four characters to
    // a line. Both have to be short for the action to sit alongside.
    const api = setup();
    const short = "EMCargo 1.206.0 is beschikbaar.";
    const wordy = "Bekijk de release-opmerkingen";
    expect(short.length).toBeLessThanOrEqual(INLINE_ACTION_MAX_CHARS);
    expect(wordy.length).toBeGreaterThan(INLINE_ACTION_MAX_LABEL);
    act(() => void api().info(short, { sticky: true, actions: [{ label: wordy, run: vi.fn() }] }));
    const row = screen.getByTestId("toast-actions");
    expect(row).toContainElement(screen.getByRole("button", { name: wordy }));
    expect(row.previousElementSibling).toHaveTextContent(short);
  });

  it("closing a question is itself an answer", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const api = setup();
    const onDismiss = vi.fn();
    act(() => void api().ask("take UN 1203?", { actions: [{ label: "yes", run: vi.fn() }], onDismiss }));
    await user.click(screen.getByRole("button", { name: "toast.dismiss" }));
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it("every kind draws an icon that takes the toast's own colour", () => {
    // In two batches, because the stack holds five: pushing all six at once
    // would quietly be testing eviction instead of icons.
    const api = setup();
    const first: number[] = [];
    act(() => {
      first.push(api().success("saved"), api().error("boom"), api().info("note"));
    });
    expectIconsInherit();
    // Cleared by the ids they were given, not by guessed ones: the counter is
    // module-level and keeps running across tests.
    act(() => {
      first.forEach((id) => api().dismiss(id));
      api().loading("working");
      api().ask("which one?", { actions: [{ label: "this one", run: vi.fn() }] });
      api().warn("watch out");
    });
    expectIconsInherit();
  });

  it("the loading icon is the one that spins", () => {
    const api = setup();
    act(() => void api().loading("working"));
    expect(document.querySelector("svg.animate-spin")).not.toBeNull();
  });

  it("a warning stays until it is closed, and carries its action", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const api = setup();
    const run = vi.fn();
    const onDismiss = vi.fn();
    act(() => void api().warn("policy not met", { actions: [{ label: "fix it", run }], onDismiss }));
    // Nothing wrong stays wrong quietly for four seconds and then vanishes.
    act(() => void vi.advanceTimersByTime(60000));
    expect(screen.getByText("policy not met")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "fix it" }));
    expect(run).toHaveBeenCalledTimes(1);
    expect(onDismiss).not.toHaveBeenCalled();
  });

  it("errors announce assertively, the rest politely", () => {
    const api = setup();
    act(() => {
      api().error("bad");
      api().success("good");
    });
    expect(screen.getByRole("alert")).toHaveAttribute("aria-live", "assertive");
    expect(screen.getByRole("status")).toHaveAttribute("aria-live", "polite");
  });
});


it("pauses undo for both pointer and keyboard focus, resuming only after both leave", () => {
  const api = setup();
  const execute = vi.fn();
  act(() => void api().undoable("deleted", { execute, restore: vi.fn() }));
  act(() => void vi.advanceTimersByTime(2000));
  const toast = screen.getByRole("status");
  fireEvent.pointerEnter(toast);
  fireEvent.focus(screen.getByRole("button", { name: "toast.undo" }));
  act(() => void vi.advanceTimersByTime(8000));
  fireEvent.pointerLeave(toast);
  act(() => void vi.advanceTimersByTime(8000));
  expect(execute).not.toHaveBeenCalled();
  fireEvent.blur(screen.getByRole("button", { name: "toast.undo" }), { relatedTarget: document.body });
  act(() => void vi.advanceTimersByTime(4100));
  expect(execute).toHaveBeenCalledTimes(1);
});
