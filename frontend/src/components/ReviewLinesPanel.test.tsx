/**
 * The goods step: a line you edit where it stands, a dialog for the rest, and
 * a snackbar that asks.
 *
 * What is pinned here is the trade this step makes. The four things a
 * consignment is made of — description, quantity, unit, and the outcome — are
 * on the line, and changing a quantity is one keystroke rather than open, type,
 * close. Everything else, the thirteen fields the old table died of, stays in
 * the detail dialog and is not creeping back onto the row.
 *
 * Then the two rules that keep the numbers honest: a figure is never shown for
 * input it was not computed from, and a line whose own text has not moved keeps
 * its figures, marked as not yet rechecked, rather than blinking away on every
 * keystroke.
 *
 * And the substance recognition, which is the one thing on a line that asks the
 * user a *question* — asked under the line it is about, with its three answers
 * spelled out. Rejecting a candidate says only that this substance is not it;
 * an answer can be found again and changed; and nothing is decided by closing
 * anything, because there is nothing to close.
 */
import { render, screen, within } from "@testing-library/react";
import { useState } from "react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import ReviewLinesPanel, { DraftLine, openQuestions } from "./ReviewLinesPanel";
import { ToastProvider } from "../toast/ToastProvider";
import { LineItem } from "../api/client";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      options && "number" in options ? `${key}:${options.number}` : key,
    i18n: { language: "nl" },
  }),
}));

const draft: DraftLine = { id: 1, description: "20 vaten benzine", quantity: 20, unit: "vaten" };

function resultLine(candidates: LineItem["dg_name_candidates"], over: Partial<LineItem> = {}): LineItem {
  return {
    line_id: 1,
    raw: "20 vaten benzine",
    description: "20 vaten benzine",
    output_description: "20 vaten benzine",
    quantity: 20,
    unit: "vaten",
    material: null,
    product_type: null,
    weight_each_kg: null,
    weight_total_kg: null,
    material_volume_m3: null,
    transport_volume_m3: null,
    length_cm: null,
    width_cm: null,
    height_cm: null,
    status: "ok",
    messages: [],
    include: true,
    dangerous_goods: false,
    dg_name_candidates: candidates,
    ...over,
  } as unknown as LineItem;
}

function renderPanel(lines: DraftLine[], result?: LineItem[], extra: Record<string, unknown> = {}) {
  const onDraftChange = (extra.onDraftChange as ReturnType<typeof vi.fn>) ?? vi.fn();
  render(
    <ToastProvider>
      <ReviewLinesPanel
        draftLines={lines}
        resultLines={result}
        onDraftChange={onDraftChange}
        onRemoveLine={vi.fn()}
        onDuplicateLine={vi.fn()}
        onAddLine={vi.fn()}
        translateMessage={(m) => m}
        {...extra}
      />
    </ToastProvider>,
  );
  return onDraftChange;
}

/** The panel is controlled, so typing only behaves like typing when something
 *  actually holds the lines. The wizard does; a bare spy does not, and the
 *  field would keep re-rendering its old value under the keystrokes. */
function StatefulPanel({ lines, result, onChange, replaceWith, onAddLine, clearResultOnEdit }: {
  lines: DraftLine[];
  result?: LineItem[];
  onChange: (lines: DraftLine[]) => void;
  /** Swapped in without remounting, the way an import replaces the lines. */
  replaceWith?: DraftLine[];
  onAddLine?: () => void;
  /** What the wizard does: a changed line clears the calculated result. */
  clearResultOnEdit?: boolean;
}) {
  const [current, setCurrent] = useState(lines);
  const [computed, setComputed] = useState(result);
  return (
    <ToastProvider>
      {replaceWith && (
        <button type="button" onClick={() => setCurrent(replaceWith)}>
          simulate import
        </button>
      )}
      <ReviewLinesPanel
        draftLines={current}
        resultLines={computed}
        onDraftChange={(next) => {
          setCurrent(next);
          if (clearResultOnEdit) setComputed(undefined);
          onChange(next);
        }}
        onRemoveLine={vi.fn()}
        onDuplicateLine={vi.fn()}
        onAddLine={onAddLine ?? (() => {
          setCurrent((lines_) => [...lines_, {
            id: Math.max(...lines_.map((l) => l.id)) + 1, description: "", quantity: 1, unit: "stuks",
          }]);
        })}
        translateMessage={(m) => m}
      />
    </ToastProvider>
  );
}

const petrol = [{ un: "1203", name: "BENZINE (MOTOR SPIRIT)", class: "3" }];

describe("editing a line where it stands", () => {
  it("the description, the quantity and the unit are on the row itself", () => {
    renderPanel([draft], [resultLine([])]);
    expect(screen.getByLabelText("review.descriptionOfLine:1")).toHaveValue("20 vaten benzine");
    expect(screen.getByLabelText("review.quantityOfLine:1")).toHaveValue(20);
    expect(screen.getByLabelText("review.unitOfLine:1")).toBeInTheDocument();
  });

  it("changing a quantity costs the keystroke and nothing else", async () => {
    const onChange = vi.fn();
    render(<StatefulPanel lines={[draft]} result={[resultLine([])]} onChange={onChange} />);
    const quantity = screen.getByLabelText("review.quantityOfLine:1");
    await userEvent.clear(quantity);
    await userEvent.type(quantity, "35");
    const updated = onChange.mock.calls[onChange.mock.calls.length - 1][0] as DraftLine[];
    expect(updated[0].quantity).toBe(35);
    // No window opened for it: that is the whole point of the row.
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("keeps dimensions one Details action away from the compact row", async () => {
    renderPanel([{ ...draft, length_cm: 200, width_cm: 80, height_cm: 40 }], [resultLine([])]);
    expect(screen.queryByText(/200 × 80 × 40 cm/)).toBeNull();
    expect(screen.queryByLabelText("review.length_cm")).toBeNull();
    expect(screen.queryByLabelText("review.wallThickness")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "review.lineDetails" }));
    expect(screen.getByLabelText("review.length_cm")).toHaveValue(200);
  });

  it("the arrow opens the rest of the fields under the row, not over it", async () => {
    renderPanel([draft], [resultLine([])]);
    const toggle = screen.getByRole("button", { name: "review.lineDetails" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByLabelText("review.length_cm")).toBeNull();

    await userEvent.click(toggle);
    expect(screen.getByLabelText("review.length_cm")).toBeInTheDocument();
    // No window: the list is still there, and so is the row above it.
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByLabelText("review.descriptionOfLine:1")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "review.closeDetails" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
  });

  it("closes one line when another opens, so the list stays a list", async () => {
    const second: DraftLine = { id: 2, description: "10 pallets", quantity: 10, unit: "pallets" };
    renderPanel([draft, second], [resultLine([]), resultLine([])]);
    const toggles = () => screen.getAllByRole("button", { name: /review\.(lineDetails|closeDetails)/ });
    await userEvent.click(toggles()[0]);
    expect(screen.getAllByLabelText("review.length_cm")).toHaveLength(1);

    await userEvent.click(toggles()[1]);
    expect(screen.getAllByLabelText("review.length_cm")).toHaveLength(1);
    expect(toggles()[0]).toHaveAttribute("aria-expanded", "false");
    expect(toggles()[1]).toHaveAttribute("aria-expanded", "true");
  });

  it("asks for the substance on the line that carries it", async () => {
    // The identity used to be asked one step later, after the goods step had
    // already recognised the substance and put its UN number on the line.
    const dg: DraftLine = { ...draft, dangerous_goods: true, confirmed_un: "1203" };
    renderPanel([dg], [resultLine([])]);
    await userEvent.click(screen.getByRole("button", { name: "review.lineDetailsDg" }));
    expect(screen.getByLabelText("review.unNumber")).toHaveValue("1203");
    expect(screen.getByLabelText("review.properShippingName")).toBeInTheDocument();
    expect(screen.getByLabelText("review.packingGroup")).toBeInTheDocument();
  });

  it("keeps the substance away from a line that does not carry one", async () => {
    renderPanel([draft], [resultLine([])]);
    await userEvent.click(screen.getByRole("button", { name: "review.lineDetails" }));
    expect(screen.queryByLabelText("review.unNumber")).toBeNull();
  });

  it("declares the line dangerous when a UN number is typed on it", async () => {
    const onChange = vi.fn();
    render(
      <StatefulPanel
        lines={[{ ...draft, dangerous_goods: true }]}
        result={[resultLine([])]}
        onChange={onChange}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "review.lineDetailsDg" }));
    await userEvent.type(screen.getByLabelText("review.unNumber"), "1203");
    const updated = onChange.mock.calls[onChange.mock.calls.length - 1][0] as DraftLine[];
    expect(updated[0].confirmed_un).toBe("1203");
    expect(updated[0].dangerous_goods).toBe(true);
  });

  it("a new line gets the cursor in its description", async () => {
    render(<StatefulPanel lines={[draft]} onChange={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "review.addLine" }));
    expect(screen.getByLabelText("review.descriptionOfLine:2")).toHaveFocus();
  });

  it("Enter on the last line makes the next one", async () => {
    const onAddLine = vi.fn();
    render(<StatefulPanel lines={[draft]} onChange={vi.fn()} onAddLine={onAddLine} />);
    await userEvent.click(screen.getByLabelText("review.quantityOfLine:1"));
    await userEvent.keyboard("{Enter}");
    expect(onAddLine).toHaveBeenCalled();
  });

  it("Enter on an earlier line moves to the next one instead of adding", async () => {
    const onAddLine = vi.fn();
    const second: DraftLine = { id: 2, description: "10 pallets", quantity: 10, unit: "pallets" };
    render(<StatefulPanel lines={[draft, second]} onChange={vi.fn()} onAddLine={onAddLine} />);
    await userEvent.click(screen.getByLabelText("review.quantityOfLine:1"));
    await userEvent.keyboard("{Enter}");
    expect(onAddLine).not.toHaveBeenCalled();
    expect(screen.getByLabelText("review.descriptionOfLine:2")).toHaveFocus();
  });
});

describe("figures while the calculation runs", () => {
  it("a line that did not change keeps its figures, marked as not yet rechecked", async () => {
    const first = { ...draft, id: 1 };
    const second: DraftLine = { id: 2, description: "10 pallets", quantity: 10, unit: "pallets" };
    render(
      <StatefulPanel
        lines={[first, second]}
        result={[resultLine([], { weight_total_kg: 880 }), resultLine([], { line_id: 2, weight_total_kg: 120 })]}
        onChange={vi.fn()}
        clearResultOnEdit
      />,
    );
    expect(screen.getByText("880")).toBeInTheDocument();

    // Typing in line 2 clears the whole result, as the wizard does.
    await userEvent.type(screen.getByLabelText("review.descriptionOfLine:2"), "x");

    // Line 1 keeps its weight and says it is waiting to be rechecked.
    expect(screen.getByText("880")).toBeInTheDocument();
    expect(screen.getAllByText("review.toBeRechecked").length).toBe(2);
    // Line 2's weight is gone: it belonged to the previous description.
    expect(screen.queryByText("120")).toBeNull();
  });

  it("without a result there are no figures at all", () => {
    renderPanel([draft]);
    expect(screen.getByText("review.toBeRechecked")).toBeInTheDocument();
    expect(screen.queryByText("status.ok")).toBeNull();
  });
});

describe("what the import left behind", () => {
  const settled = (id: number, description: string) =>
    ({ id, description, quantity: 1, unit: "stuks" }) as DraftLine;

  it("says how many lines want attention, and narrows to them", async () => {
    const lines = [settled(1, "Stalen plaat"), settled(2, "Diverse onderdelen"), settled(3, "Stalen buis")];
    const results = [
      resultLine([], { line_id: 1, weight_total_kg: 100 }),
      resultLine([], { line_id: 2, status: "needs_review", messages: ["no_dimensions"] }),
      resultLine([], { line_id: 3, weight_total_kg: 50 }),
    ];
    renderPanel(lines, results);
    expect(screen.getByText("review.attentionSummary")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "review.onlyAttention" }));
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
    expect(screen.getByLabelText("review.descriptionOfLine:2")).toHaveValue("Diverse onderdelen");

    await userEvent.click(screen.getByRole("button", { name: "review.showAllLines" }));
    expect(screen.getAllByRole("listitem")).toHaveLength(3);
  });

  it("says nothing when every line came out settled", () => {
    renderPanel([draft], [resultLine([], { weight_total_kg: 100 })]);
    expect(screen.queryByText("review.attentionSummary")).toBeNull();
    expect(screen.queryByRole("button", { name: "review.onlyAttention" })).toBeNull();
  });
});

describe("the substance question, answered on its line", () => {
  it("asks under the line it is about, not in a floating snackbar", async () => {
    renderPanel([draft], [resultLine(petrol)]);
    const row = screen.getAllByRole("listitem")[0];
    expect(within(row).getByText("review.dgAskOne")).toBeInTheDocument();
    // Nothing is asked at the bottom-right of the screen any more.
    expect(screen.queryByRole("button", { name: "toast.dismiss" })).toBeNull();
  });

  it("taking the number ticks the line and carries it", async () => {
    const onDraftChange = renderPanel([draft], [resultLine(petrol)]);
    await userEvent.click(screen.getByRole("button", { name: "review.dgTake" }));
    const updated = onDraftChange.mock.calls[onDraftChange.mock.calls.length - 1][0] as DraftLine[];
    expect(updated[0].dangerous_goods).toBe(true);
    expect(updated[0].confirmed_un).toBe("1203");
    expect(updated[0].dg_decision).toBe("confirmed");
  });

  it("a different substance ticks the line and leaves the number to the DG step", async () => {
    const onDraftChange = renderPanel([draft], [resultLine(petrol)]);
    await userEvent.click(screen.getByRole("button", { name: "review.dgOther" }));
    const updated = onDraftChange.mock.calls[onDraftChange.mock.calls.length - 1][0] as DraftLine[];
    expect(updated[0].dangerous_goods).toBe(true);
    expect(updated[0].confirmed_un).toBeUndefined();
    expect(updated[0].dg_decision).toBe("other");
  });

  it("rejecting the suggestion says nothing about the goods being safe", async () => {
    const onDraftChange = renderPanel([{ ...draft, dangerous_goods: true }], [resultLine(petrol)]);
    await userEvent.click(screen.getByRole("button", { name: "review.dgWrong" }));
    const updated = onDraftChange.mock.calls[onDraftChange.mock.calls.length - 1][0] as DraftLine[];
    expect(updated[0].dg_decision).toBe("rejected");
    // The tick the user set is theirs; a rejected candidate does not clear it.
    expect(updated[0].dangerous_goods).toBe(true);
    expect(updated[0].confirmed_un).toBeUndefined();
  });

  it("an answered line says what was answered, and lets it be changed", async () => {
    const onChange = vi.fn();
    render(
      <StatefulPanel
        lines={[{ ...draft, dg_decision: "rejected", dg_dismissed: true }]}
        result={[resultLine(petrol)]}
        onChange={onChange}
      />,
    );
    expect(screen.getByText("review.dgCandidateRejected")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "review.lineDetails" }));
    expect(screen.getByText("review.dgAnsweredRejected")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "review.dgChangeAnswer" }));
    // The question is back, and nothing was decided on the user's behalf.
    expect(screen.getByText("review.dgAskOne")).toBeInTheDocument();
  });

  it("several candidates become a button per UN number, none pre-chosen", async () => {
    const acids = [
      { un: "1830", name: "ZWAVELZUUR met meer dan 51% zuur", class: "8" },
      { un: "2796", name: "ZWAVELZUUR met ten hoogste 51% zuur", class: "8" },
    ];
    const onDraftChange = renderPanel([draft], [resultLine(acids)]);
    expect(screen.getByText("review.dgAskMany")).toBeInTheDocument();
    const takes = screen.getAllByRole("button", { name: /review.dgTake/ });
    expect(takes[0]).toHaveTextContent(acids[0].name);
    expect(takes[1]).toHaveTextContent(acids[1].name);
    expect(takes).toHaveLength(2);
    await userEvent.click(takes[1]);
    const updated = onDraftChange.mock.calls[onDraftChange.mock.calls.length - 1][0] as DraftLine[];
    expect(updated[0].confirmed_un).toBe("2796");
  });

  it("an answer from before v1.195.0 is read as one", () => {
    // Only the old fields, as a shipment saved by an earlier release has them.
    renderPanel([{ ...draft, confirmed_un: "1203" }], [resultLine(petrol)]);
    expect(screen.getByText("UN 1203")).toBeInTheDocument();
    expect(screen.queryByText("review.dgAnsweredConfirmed")).toBeNull();
    expect(screen.queryByText("review.dgAskOne")).toBeNull();
  });

  it("without candidates nothing is asked", () => {
    renderPanel([draft], [resultLine([])]);
    expect(screen.queryByText("review.dgAskOne")).toBeNull();
    expect(screen.queryByText("review.dgAskMany")).toBeNull();
  });

  it("an unanswered question counts as something that wants the user", () => {
    renderPanel([draft], [resultLine(petrol)]);
    expect(screen.getByText("review.dgAskOne")).toBeInTheDocument();
    // A single row carries its question directly; a second summary adds noise.
    expect(screen.queryByText(/review.unansweredSummary/)).toBeNull();
  });
});

describe("what openQuestions reports to the rest of the wizard", () => {
  it("counts the lines that were asked and not answered", () => {
    const lines = [draft, { ...draft, id: 2, confirmed_un: "1203" }, { ...draft, id: 3 }];
    const results = [resultLine(petrol), resultLine(petrol), resultLine([])];
    expect(openQuestions(lines, results)).toBe(1);
  });

  it("counts nothing without a calculation to ask about", () => {
    expect(openQuestions([draft], undefined)).toBe(0);
  });
});

it("shows a confirmed petrol result once and keeps its answer revisable", async () => {
  renderPanel([{ ...draft, description: "Benzine 25L", quantity: 1, dangerous_goods: true, confirmed_un: "1203" }],
    [resultLine(petrol, { weight_total_kg: 18.62, weight_each_kg: 18.62 })]);
  expect(screen.getByText("18,62")).toBeInTheDocument();
  expect(screen.getAllByText("UN 1203")).toHaveLength(1);
  expect(screen.queryByText("status.ok")).toBeNull();
  expect(screen.queryByText(/kg\/review.each/)).toBeNull();
  await userEvent.click(screen.getByRole("button", { name: "review.lineDetailsDg" }));
  expect(screen.getByRole("button", { name: "review.dgChangeAnswer" })).toBeInTheDocument();
});

it("keeps errors visible when detail fields are closed", () => {
  renderPanel([draft], [resultLine([], {status: "error", messages: ["Missing dimensions"]})]);
  expect(screen.getByText("Missing dimensions")).toBeInTheDocument();
  expect(screen.queryByLabelText("review.length_cm")).toBeNull();
});
