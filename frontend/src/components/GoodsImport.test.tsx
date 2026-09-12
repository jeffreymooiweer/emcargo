/** Import keeps the main goods list quiet while retaining mapping decisions,
 * append/replace semantics, direct paste entry and cancellation safety. */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";

import GoodsImport from "./GoodsImport";
import { ToastProvider } from "../toast/ToastProvider";
import { api, ImportAnalysis } from "../api/client";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      options && "count" in options ? `${key}:${options.count}` : key,
    i18n: { language: "nl" },
  }),
}));

const RECOGNISED: ImportAnalysis = {
  source: "header",
  has_header: true,
  mapping: { description: 0, quantity: 1, unit: 2 },
  columns: [
    { index: 0, header: "Omschrijving", samples: ["Stalen hoekprofiel"] },
    { index: 1, header: "Aantal", samples: ["8"] },
    { index: 2, header: "Eenheid", samples: ["stuks"] },
  ],
};

const GUESSED: ImportAnalysis = { ...RECOGNISED, source: "position", has_header: false };

const FILE = new File(["x"], "goods.xlsx", { type: "application/vnd.ms-excel" });

function renderImport(hasLines: boolean, onImport = vi.fn()) {
  render(
    <ToastProvider>
      <GoodsImport hasLines={hasLines} onImport={onImport} />
    </ToastProvider>,
  );
  return onImport;
}

beforeEach(() => {
  vi.restoreAllMocks();
  HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  HTMLDialogElement.prototype.close = function () { this.open = false; };
});

describe("the entrance on the goods step", () => {
  it("offers one named import action and keeps the main surface quiet", async () => {
    renderImport(false);
    expect(screen.getByRole("button", { name: "review.importAction" })).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(screen.queryByRole("button", { name: "import.downloadTemplate" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "review.importAction" }));
    expect(screen.getByRole("dialog", { name: "review.importTitle" })).toBeInTheDocument();
    expect(screen.getByLabelText("review.importPaste")).toBeInTheDocument();
    expect(screen.getByText("review.importFile")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "import.downloadTemplate" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "review.importTitle" })).toHaveFocus();
  });

  it("closing with Escape returns focus without changing the goods", async () => {
    const onImport = renderImport(true);
    const trigger = screen.getByRole("button", { name: "review.importAction" });
    await userEvent.click(trigger);
    await userEvent.type(screen.getByLabelText("review.importPaste"), "unfinished input");
    fireEvent(screen.getByRole("dialog"), new Event("cancel", { bubbles: false, cancelable: true }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(trigger).toHaveFocus();
    expect(onImport).not.toHaveBeenCalled();
  });

  it("a direct paste shortcut opens with the textarea focused", () => {
    render(<ToastProvider><GoodsImport initialPaste hasLines={false} onImport={vi.fn()} /></ToastProvider>);
    expect(screen.getByLabelText("review.importPaste")).toHaveFocus();
  });

});

describe("asking only where there is doubt", () => {
  it("a recognised file goes straight in when there is nothing to replace", async () => {
    vi.spyOn(api, "parseWizardImportFile").mockResolvedValue({
      text: "Stalen hoekprofiel | 8 | stuks", has_header: true, analysis: RECOGNISED,
      rows: [["Omschrijving", "Aantal", "Eenheid"], ["Stalen hoekprofiel", "8", "stuks"]],
    });
    const onImport = renderImport(false);
    await userEvent.click(screen.getByRole("button", { name: "review.importAction" }));
    await userEvent.upload(screen.getByLabelText("review.importFile", { selector: "input" }), FILE);
    await waitFor(() => expect(onImport).toHaveBeenCalledWith("Stalen hoekprofiel | 8 | stuks", "replace"));
    // Nothing was asked, so nothing is left standing.
    expect(screen.queryByLabelText("review.importPaste")).toBeNull();
  });

  it("a guessed file shows its columns before anything is imported", async () => {
    vi.spyOn(api, "parseWizardImportFile").mockResolvedValue({
      text: "Stalen hoekprofiel | 8 | stuks", has_header: false, analysis: GUESSED,
      rows: [["Stalen hoekprofiel", "8", "stuks"]],
    });
    const onImport = renderImport(false);
    await userEvent.click(screen.getByRole("button", { name: "review.importAction" }));
    await userEvent.upload(screen.getByLabelText("review.importFile", { selector: "input" }), FILE);
    expect(await screen.findByText("import.guessedColumns")).toBeInTheDocument();
    expect(onImport).not.toHaveBeenCalled();
  });

  it("says what it read and what it had to skip", async () => {
    vi.spyOn(api, "parseWizardImportFile").mockResolvedValue({
      text: "Stalen hoekprofiel | 8 | stuks", has_header: false, analysis: GUESSED,
      rows: [["Stalen hoekprofiel", "8", "stuks"], ["", "3", "stuks"], ["", "", ""]],
    });
    renderImport(false);
    await userEvent.click(screen.getByRole("button", { name: "review.importAction" }));
    await userEvent.upload(screen.getByLabelText("review.importFile", { selector: "input" }), FILE);
    expect(await screen.findByText(/review.importRead:1/)).toBeInTheDocument();
    expect(screen.getByText(/review.importSkipped:2/)).toBeInTheDocument();
  });
});

describe("adding or replacing", () => {
  it("an empty shipment is not asked which of the two it wants", async () => {
    const onImport = renderImport(false);
    await userEvent.click(screen.getByRole("button", { name: "review.importAction" }));
    await userEvent.type(screen.getByLabelText("review.importPaste"), "Stalen plaat | 4 | stuks");
    expect(screen.queryByRole("button", { name: "review.importAppend" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "review.importConfirm" }));
    expect(onImport).toHaveBeenCalledWith("Stalen plaat | 4 | stuks", "replace");
  });

  it("a shipment with lines is offered both, by name", async () => {
    const onImport = renderImport(true);
    await userEvent.click(screen.getByRole("button", { name: "review.importAction" }));
    await userEvent.type(screen.getByLabelText("review.importPaste"), "Stalen plaat | 4 | stuks");
    expect(screen.getByRole("button", { name: "review.importReplace" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "review.importAppend" }));
    expect(onImport).toHaveBeenCalledWith("Stalen plaat | 4 | stuks", "append");
  });

  it("a recognised file with lines already there still asks which", async () => {
    vi.spyOn(api, "parseWizardImportFile").mockResolvedValue({
      text: "Stalen hoekprofiel | 8 | stuks", has_header: true, analysis: RECOGNISED,
      rows: [["Omschrijving", "Aantal", "Eenheid"], ["Stalen hoekprofiel", "8", "stuks"]],
    });
    const onImport = renderImport(true);
    await userEvent.click(screen.getByRole("button", { name: "review.importAction" }));
    await userEvent.upload(screen.getByLabelText("review.importFile", { selector: "input" }), FILE);
    expect(await screen.findByRole("button", { name: "review.importAppend" })).toBeInTheDocument();
    expect(onImport).not.toHaveBeenCalled();
  });

  it("nothing is imported from an empty paste", async () => {
    const onImport = renderImport(false);
    await userEvent.click(screen.getByRole("button", { name: "review.importAction" }));
    expect(screen.getByRole("button", { name: "review.importConfirm" })).toBeDisabled();
    expect(onImport).not.toHaveBeenCalled();
  });

  it("maps Excel clipboard columns and excludes the heading row", async () => {
    vi.spyOn(api, "parseWizardImportFile").mockResolvedValue({
      text: "Bolts | 8 | stuks", has_header: true, analysis: RECOGNISED,
      rows: [["Aantal", "Omschrijving", "Eenheid"], ["8", "Bolts", "stuks"]],
    });
    const onImport = renderImport(true);
    await userEvent.click(screen.getByRole("button", { name: "review.importAction" }));
    fireEvent.change(screen.getByLabelText("review.importPaste"), { target: { value: "Aantal\tOmschrijving\tEenheid\n8\tBolts\tstuks" } });
    await userEvent.click(screen.getByRole("button", { name: "review.importAppend" }));
    await waitFor(() => expect(onImport).toHaveBeenCalledWith("Bolts | 8 | stuks", "append"));
  });

  it("lets the user check a guessed clipboard mapping before importing", async () => {
    vi.spyOn(api, "parseWizardImportFile").mockResolvedValue({
      text: "Bolts | 8 | stuks", has_header: false, analysis: GUESSED,
      rows: [["Bolts", "8", "stuks"]],
    });
    const onImport = renderImport(false);
    await userEvent.click(screen.getByRole("button", { name: "review.importAction" }));
    fireEvent.change(screen.getByLabelText("review.importPaste"), { target: { value: "Bolts\t8\tstuks" } });
    await userEvent.click(screen.getByRole("button", { name: "review.importConfirm" }));
    await waitFor(() => expect(screen.getByLabelText("review.importPaste")).toHaveValue("Bolts | 8 | stuks"));
    expect(onImport).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "review.importConfirm" }));
    expect(onImport).toHaveBeenCalledWith("Bolts | 8 | stuks", "replace");
  });
});

it("closing an in-flight file import cannot apply its late response", async () => {
  let finish!: (value: any) => void;
  vi.spyOn(api, "parseWizardImportFile").mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  const onImport = renderImport(false);
  await userEvent.click(screen.getByRole("button", { name: "review.importAction" }));
  await userEvent.upload(screen.getByLabelText("review.importFile", { selector: "input" }), FILE);
  await userEvent.click(screen.getByRole("button", { name: "review.cancel" }));
  finish({text: "Staal | 1 | stuks", analysis: RECOGNISED, rows: []});
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  expect(onImport).not.toHaveBeenCalled();
});

it("opens dropped-file progress immediately so new entry cannot race with replacement", async () => {
  let finish!: (value: any) => void;
  vi.spyOn(api, "parseWizardImportFile").mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  const onImport = vi.fn();
  render(<ToastProvider><GoodsImport dropped={FILE} hasLines={false} onImport={onImport} /></ToastProvider>);
  expect(screen.getByRole("dialog", { name: "review.importTitle" })).toBeInTheDocument();
  expect(screen.getByLabelText("review.importPaste")).toBeDisabled();
  await userEvent.click(screen.getByRole("button", { name: "review.cancel" }));
  finish({text: "Staal | 1 | stuks", analysis: RECOGNISED, rows: []});
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  expect(onImport).not.toHaveBeenCalled();
});
