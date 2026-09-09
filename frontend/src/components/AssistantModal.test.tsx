/**
 * The assistant as a survey in a modal.
 *
 * One question per screen, options as selectable answers, and a previous
 * button that really goes back: the server is stateless, so history is a
 * client-side stack of snapshots, and going back restores the wizard state
 * taken before that answer was applied. These tests pin that mechanism, the
 * value/label split of the answers, and that a misunderstood answer neither
 * advances the survey nor grows the history.
 */
import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AssistantModal from "./AssistantModal";
import { ToastProvider } from "../toast/ToastProvider";
import { api } from "../api/client";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, vars?: Record<string, unknown>) =>
      vars ? `${key} ${JSON.stringify(vars)}` : key,
    i18n: { language: "nl" },
  }),
}));

vi.mock("../api/client", () => ({
  api: { assistantStep: vi.fn(), geoLocations: vi.fn(), geoAddress: vi.fn() },
}));

const stepMock = api.assistantStep as ReturnType<typeof vi.fn>;
const geoLocationsMock = api.geoLocations as ReturnType<typeof vi.fn>;
const geoAddressMock = api.geoAddress as ReturnType<typeof vi.fn>;

const QUESTION = {
  state: { modality: "road", draft_lines: [{ id: 1 }] },
  events: [{ kind: "lines_added", count: 1 }],
  pending: {
    scope: "dg_question",
    field: "carriage_mode",
    required: true,
    label: { nl: "Vervoerswijze" },
    reason: "carriage_mode_decides",
    options: ["packages", "tank"],
    option_labels: { packages: { nl: "Colli" }, tank: { nl: "Tank" } },
  },
};

function renderModal(onApplyState = vi.fn(), onClose = vi.fn(), modality = "road") {
  render(
    <ToastProvider>
      <AssistantModal
        open
        onClose={onClose}
        buildState={() => ({ modality: "road", draft_lines: [] })}
        onApplyState={onApplyState}
        modality={modality}
      />
    </ToastProvider>,
  );
  return { onApplyState, onClose };
}

async function reachQuestion(onApplyState = vi.fn()) {
  stepMock.mockResolvedValueOnce(QUESTION);
  renderModal(onApplyState);
  await userEvent.type(
    screen.getByLabelText("assistant.describeLabel"),
    "1000 jerrycans diesel",
  );
  await userEvent.click(screen.getByRole("button", { name: "assistant.start" }));
  await screen.findByText(/Vervoerswijze/);
  return onApplyState;
}

beforeEach(() => {
  stepMock.mockReset();
  geoLocationsMock.mockReset().mockResolvedValue({ results: [] });
  geoAddressMock.mockReset().mockResolvedValue({ results: [], available: true });
});

describe("AssistantModal", () => {
  it("starts as a describe screen and turns the reply into a survey question", async () => {
    const onApplyState = await reachQuestion();
    expect(onApplyState).toHaveBeenCalledWith(QUESTION.state);
    // Options are radios showing the localized label.
    expect(screen.getByRole("radio", { name: "Colli" })).toBeTruthy();
    expect(screen.getByRole("radio", { name: "Tank" })).toBeTruthy();
  });

  it("an answer needs a selection, and the selection sends the stored value", async () => {
    await reachQuestion();
    const next = screen.getByRole("button", { name: "assistant.next" });
    expect((next as HTMLButtonElement).disabled).toBe(true);
    await userEvent.click(screen.getByRole("radio", { name: "Colli" }));
    stepMock.mockResolvedValueOnce({ state: {}, events: [], pending: null });
    await userEvent.click(next);
    expect(stepMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ message: "packages" }),
    );
  });

  it("previous restores the snapshot taken before the answer", async () => {
    const onApplyState = await reachQuestion();
    await userEvent.click(screen.getByRole("button", { name: "assistant.previous" }));
    // Back to the describe screen, with the pre-answer state re-applied.
    expect(screen.getByLabelText("assistant.describeLabel")).toBeTruthy();
    expect(onApplyState).toHaveBeenLastCalledWith({ modality: "road", draft_lines: [] });
  });

  it("a misunderstood answer keeps the question and grows no history", async () => {
    await reachQuestion();
    await userEvent.click(screen.getByRole("radio", { name: "Tank" }));
    stepMock.mockResolvedValueOnce({
      state: {},
      events: [{ kind: "not_understood" }],
      pending: QUESTION.pending,
    });
    await userEvent.click(screen.getByRole("button", { name: "assistant.next" }));
    expect(await screen.findByText("assistant.notUnderstood")).toBeTruthy();
    expect(screen.getByText(/Vervoerswijze/)).toBeTruthy();
  });

  it("shows a model interpretation for confirmation without saving it or losing the typed answer", async () => {
    const applied = await reachQuestion();
    applied.mockClear();
    await userEvent.type(screen.getByLabelText("assistant.orDescribe"), "in het reservoir op de wagen");
    stepMock.mockResolvedValueOnce({ ...QUESTION, events: [{ kind: "clarify", reason: "confirm_choice", suggested_choice: "tank", option_label: { nl: "Tank" } }] });
    await userEvent.click(screen.getByRole("button", { name: "assistant.next" }));
    expect(await screen.findByText(/assistant.problem.confirm_choice.*Tank/)).toBeTruthy();
    expect(applied).not.toHaveBeenCalled();
    expect((screen.getByLabelText("assistant.orDescribe") as HTMLInputElement).value).toBe("in het reservoir op de wagen");
    await userEvent.click(screen.getByRole("radio", { name: "Tank" }));
    stepMock.mockResolvedValueOnce({ ...QUESTION, events: [] });
    await userEvent.click(screen.getByRole("button", { name: "assistant.next" }));
    expect(stepMock).toHaveBeenLastCalledWith(expect.objectContaining({ message: "tank" }));
    expect(applied).toHaveBeenCalledTimes(1);
  });

  it("shows the lay phrasing and keeps label and help behind the info mark", async () => {
    stepMock.mockResolvedValueOnce({
      ...QUESTION,
      pending: {
        ...QUESTION.pending,
        simple: { nl: "Hoe gaat dit vervoerd worden?" },
        help: { nl: "De regels verschillen per vervoerswijze." },
      },
    });
    renderModal();
    await userEvent.type(screen.getByLabelText("assistant.describeLabel"), "diesel");
    await userEvent.click(screen.getByRole("button", { name: "assistant.start" }));
    expect(await screen.findByText("Hoe gaat dit vervoerd worden?")).toBeTruthy();
    // The formal wording only appears after opening the info mark.
    expect(screen.queryByText(/De regels verschillen/)).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "assistant.info" }));
    expect(screen.getByText(/Vervoerswijze — De regels verschillen/)).toBeTruthy();
  });

  it("a follow-up question shows the example and grows no history", async () => {
    await reachQuestion();
    await userEvent.click(screen.getByRole("radio", { name: "Tank" }));
    stepMock.mockResolvedValueOnce({
      state: {},
      events: [{ kind: "clarify", field: "carriage_mode", example: "25 L" }],
      pending: QUESTION.pending,
    });
    await userEvent.click(screen.getByRole("button", { name: "assistant.next" }));
    expect(await screen.findByText(/assistant.clarify.*25 L/)).toBeTruthy();
    expect(screen.getByText(/Vervoerswijze/)).toBeTruthy();
  });

  it("a corrected answer names what was tried", async () => {
    await reachQuestion();
    await userEvent.click(screen.getByRole("radio", { name: "Tank" }));
    stepMock.mockResolvedValueOnce({
      state: {},
      events: [{ kind: "clarify", field: "carriage_mode", attempt: "per onderzeeboot" }],
      pending: QUESTION.pending,
    });
    await userEvent.click(screen.getByRole("button", { name: "assistant.next" }));
    expect(await screen.findByText(/assistant.corrected.*per onderzeeboot/)).toBeTruthy();
  });

  it("names which goods a question is about", async () => {
    stepMock.mockResolvedValueOnce({
      state: { modality: "road", draft_lines: [{ id: 1 }] },
      events: [{ kind: "lines_added", count: 2 }],
      pending: {
        scope: "goods_question",
        field: "goods_dimensions",
        required: false,
        goods: "kalkzandsteen",
        simple: { nl: "Hoe groot is één pallet?" },
        reason: "dimensions_complete_the_picture",
        options: [],
      },
    });
    renderModal();
    await userEvent.type(screen.getByLabelText("assistant.describeLabel"), "4 pallets");
    await userEvent.click(screen.getByRole("button", { name: "assistant.start" }));
    expect(await screen.findByText("Hoe groot is één pallet?")).toBeTruthy();
    expect(screen.getByText("kalkzandsteen")).toBeTruthy();
    // Optional, so it can be skipped — a measurement is never a blocker.
    expect(screen.getByRole("button", { name: "assistant.skip" })).toBeTruthy();
  });

  it("a location question suggests airports, ports and stations like the wizard", async () => {
    stepMock.mockResolvedValueOnce({
      state: {},
      events: [],
      pending: {
        scope: "doc_question",
        field: "loading_point",
        type: "text",
        required: true,
        label: { nl: "Plaats van inontvangstneming" },
        options: [],
      },
    });
    geoLocationsMock.mockResolvedValue({
      results: [{
        type: "port", code: "NLRTM", name: "Rotterdam",
        city: "Rotterdam", country: "Netherlands",
      }],
    });
    renderModal();
    await userEvent.type(screen.getByLabelText("assistant.describeLabel"), "staal");
    await userEvent.click(screen.getByRole("button", { name: "assistant.start" }));
    const input = await screen.findByPlaceholderText("geo.locationPlaceholder");
    await userEvent.type(input, "rott");
    const suggestion = await screen.findByText("Rotterdam (NLRTM)");
    await userEvent.click(suggestion);
    expect((input as HTMLInputElement).value).toBe("Rotterdam (NLRTM), Netherlands");
    // The picked location is the answer the next button sends.
    stepMock.mockResolvedValueOnce({ state: {}, events: [], pending: null });
    await userEvent.click(screen.getByRole("button", { name: "assistant.next" }));
    expect(stepMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ message: "Rotterdam (NLRTM), Netherlands" }),
    );
  });

  it("an address question suggests addresses like the wizard", async () => {
    stepMock.mockResolvedValueOnce({
      state: {},
      events: [],
      pending: {
        scope: "doc_question",
        field: "consignor_address",
        type: "textarea",
        required: true,
        label: { nl: "Adres afzender" },
        options: [],
      },
    });
    geoAddressMock.mockResolvedValue({
      results: [{
        label: "Kade 1, 3011 AA Rotterdam, Netherlands",
        name: "", street: "Kade", housenumber: "1",
        postcode: "3011 AA", city: "Rotterdam", country: "Netherlands",
      }],
      available: true,
    });
    renderModal();
    await userEvent.type(screen.getByLabelText("assistant.describeLabel"), "staal");
    await userEvent.click(screen.getByRole("button", { name: "assistant.start" }));
    const search = await screen.findByPlaceholderText("geo.addressPlaceholder");
    await userEvent.type(search, "kade 1");
    const suggestion = await screen.findByText("Kade 1, 3011 AA Rotterdam, Netherlands");
    await userEvent.click(suggestion);
    // The picked address lands multi-line in the editable answer box.
    const boxes = screen.getAllByRole("textbox").filter(
      (el) => el.tagName === "TEXTAREA",
    ) as HTMLTextAreaElement[];
    expect(boxes.some((el) => el.value === "Kade 1\n3011 AA Rotterdam\nNetherlands")).toBe(true);
  });

  it("a date question is answered through a date picker", async () => {
    stepMock.mockResolvedValueOnce({
      state: {},
      events: [],
      pending: {
        scope: "doc_question",
        field: "established_date",
        type: "date",
        required: true,
        label: { nl: "Datum van opmaak" },
        options: [],
      },
    });
    renderModal();
    await userEvent.type(screen.getByLabelText("assistant.describeLabel"), "staal");
    await userEvent.click(screen.getByRole("button", { name: "assistant.start" }));
    await screen.findByText(/Datum van opmaak/);
    const picker = document.querySelector('input[type="date"]') as HTMLInputElement;
    expect(picker).toBeTruthy();
    fireEvent.change(picker, { target: { value: "2026-08-20" } });
    stepMock.mockResolvedValueOnce({ state: {}, events: [], pending: null });
    await userEvent.click(screen.getByRole("button", { name: "assistant.next" }));
    expect(stepMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ message: "2026-08-20" }),
    );
  });

  it("no pending question means the survey is done", async () => {
    stepMock.mockResolvedValueOnce({ state: {}, events: [{ kind: "ready", documents: [] }], pending: null });
    const { onClose } = renderModal();
    await userEvent.type(screen.getByLabelText("assistant.describeLabel"), "staal");
    await userEvent.click(screen.getByRole("button", { name: "assistant.start" }));
    expect(await screen.findByText("assistant.ready")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "assistant.done" }));
    expect(onClose).toHaveBeenCalled();
  });

  it("clicking the backdrop closes; clicking the dialog does not", async () => {
    const { onClose } = renderModal();
    await userEvent.click(screen.getByRole("dialog"));
    expect(onClose).not.toHaveBeenCalled();
    await userEvent.click(screen.getByTestId("assistant-backdrop"));
    expect(onClose).toHaveBeenCalled();
  });
});


it("retains an unclear typed answer even if the reply has no next question", async () => {
  const apply = await reachQuestion();
  const input = screen.getByLabelText("assistant.orDescribe");
  await userEvent.type(input, "geen tank");
  stepMock.mockResolvedValueOnce({ state: {}, events: [{ kind: "clarify", attempt: "geen tank" }], pending: null });
  await userEvent.click(screen.getByRole("button", { name: "assistant.next" }));
  await screen.findByRole("alert");
  expect(input).toHaveValue("geen tank");
  expect(screen.getByRole("radio", { name: "Colli" })).toBeInTheDocument();
  expect(apply).toHaveBeenCalledTimes(1);
});

it("uses the latest accepted state even when the parent's snapshot stays stale", async () => {
  await reachQuestion();
  await userEvent.click(screen.getByRole("radio", { name: "Colli" }));
  stepMock.mockResolvedValueOnce({ state: QUESTION.state, events: [], pending: null });
  await userEvent.click(screen.getByRole("button", { name: "assistant.next" }));
  expect(stepMock).toHaveBeenLastCalledWith(expect.objectContaining({ state: QUESTION.state }));
});

it("keeps the answer on connection failure and allows retry without a toast", async () => {
  await reachQuestion();
  await userEvent.type(screen.getByLabelText("assistant.orDescribe"), "colli");
  stepMock.mockRejectedValueOnce(new Error("private runtime path"));
  await userEvent.click(screen.getByRole("button", { name: "assistant.next" }));
  expect(await screen.findByText("assistant.problem.connection")).toBeInTheDocument();
  expect(screen.getByLabelText("assistant.orDescribe")).toHaveValue("colli");
  expect(screen.queryByText("private runtime path")).toBeNull();
  stepMock.mockResolvedValueOnce({ state: QUESTION.state, events: [], pending: null });
  await userEvent.click(screen.getByRole("button", { name: "assistant.next" }));
  expect(await screen.findByText("assistant.ready")).toBeInTheDocument();
});

it("ignores a late answer after the assistant closes", async () => {
  let resolve!: (result: typeof QUESTION) => void;
  stepMock.mockReturnValue(new Promise(yes => { resolve = yes; }));
  const props = { onClose: vi.fn(), buildState: () => ({ modality: "road", draft_lines: [] }), onApplyState: vi.fn() };
  const view = render(<AssistantModal open {...props} />);
  await userEvent.type(screen.getByLabelText("assistant.describeLabel"), "20 jerrycans diesel");
  await userEvent.click(screen.getByRole("button", { name: "assistant.start" }));
  view.rerender(<AssistantModal open={false} {...props} />);
  await act(async () => resolve(QUESTION));
  expect(props.onApplyState).not.toHaveBeenCalled();
});

it("reopens on current wizard data instead of asking for the goods again", async () => {
  stepMock.mockResolvedValueOnce(QUESTION);
  render(<AssistantModal open onClose={vi.fn()} buildState={() => QUESTION.state} onApplyState={vi.fn()} />);
  await screen.findByText(/Vervoerswijze/);
  expect(stepMock).toHaveBeenCalledWith(expect.objectContaining({ message: "", state: QUESTION.state, pending: null }));
});

it("keeps keyboard focus inside the dialog and restores the trigger on close", async () => {
  const trigger = document.createElement("button"); document.body.append(trigger); trigger.focus();
  const view = render(<AssistantModal open onClose={vi.fn()} buildState={() => ({})} onApplyState={vi.fn()} />);
  const close = screen.getByRole("button", { name: "assistant.close" });
  close.focus(); await userEvent.tab({ shift: true });
  expect(screen.getByRole("dialog")).toContainElement(document.activeElement as HTMLElement);
  view.unmount(); expect(trigger).toHaveFocus(); trigger.remove();
});
