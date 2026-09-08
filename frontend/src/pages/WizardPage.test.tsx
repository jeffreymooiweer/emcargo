/** Restore reads must survive effect cleanup and must finish before autosave. */
import { StrictMode } from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { DocumentRegistry, ShipmentDetail } from "../api/client";
import type { DraftLine } from "../components/ReviewLinesPanel";
import WizardPage from "./WizardPage";

const mocks = vi.hoisted(() => ({
  api: {
    documentsRegistry: vi.fn(), shipments: vi.fn(), shipment: vi.fn(), runningDraft: vi.fn(),
    saveDraft: vi.fn(), calculate: vi.fn(),
  },
  toast: { info: vi.fn(), error: vi.fn(), success: vi.fn() },
  settings: { history_enabled: true },
  preferences: { prefill_documents: false, consignor_name: "", default_unit: "pcs" },
}));
vi.mock("../api/client", () => ({ api: mocks.api }));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key, i18n: { language: "nl" } }) }));
vi.mock("../settings/preferences", () => ({
  usePreferences: () => ({ preferences: mocks.preferences, publicSettings: mocks.settings, loaded: true }),
}));
vi.mock("../toast/ToastProvider", () => ({ useToast: () => mocks.toast }));
vi.mock("../components/AssistantModal", () => ({ default: () => null }));
vi.mock("../components/ReviewLinesPanel", async (original) => ({
  ...await original<typeof import("../components/ReviewLinesPanel")>(),
  default: ({ draftLines, onDraftChange }: { draftLines: DraftLine[]; onDraftChange: (lines: DraftLine[]) => void }) => (
    <input aria-label="Goods description" value={draftLines[0]?.description ?? ""}
      onChange={(event) => onDraftChange([{ ...draftLines[0], description: event.target.value }])} />
  ),
}));

const registry = {
  modalities: [{ key: "road", documents: [] }, { key: "rail", documents: [] }],
  documents: [], shared_sections: [],
} as unknown as DocumentRegistry;

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

function saved(description = "Saved goods", modality = "road"): ShipmentDetail {
  return {
    id: 42, reference: "SAVED-42", updated_at: "2026-09-08T10:00:00Z", modality,
    snapshot: {
      version: 1, modality, stepKey: "lines", nextId: 2,
      draftLines: [{ id: 1, description, quantity: 1, unit: "pcs" }],
      docValues: { consignor_name: "Saved company", shipment_reference: "SAVED-42" },
      result: null, dgEntries: [], selectedDocs: null, skippedQuestions: [], signature: null,
    },
  } as unknown as ShipmentDetail;
}

function open(path = "/wizard/road", strict = true) {
  const app = <MemoryRouter initialEntries={[path]}><Routes>
    <Route path="/wizard/:modality" element={<WizardPage />} />
  </Routes></MemoryRouter>;
  return render(strict ? <StrictMode>{app}</StrictMode> : app);
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  mocks.settings.history_enabled = true;
  mocks.preferences.prefill_documents = false;
  mocks.preferences.consignor_name = "";
  mocks.api.documentsRegistry.mockResolvedValue(registry);
  mocks.api.shipments.mockResolvedValue({ items: [] });
  mocks.api.runningDraft.mockResolvedValue(null);
  mocks.api.shipment.mockResolvedValue(saved());
  mocks.api.saveDraft.mockResolvedValue({ id: 42, updated_at: "2026-09-08T10:00:00Z" });
  mocks.api.calculate.mockImplementation(() => new Promise(() => {}));
});
afterEach(() => { vi.useRealTimers(); });

describe("shipment restoration", () => {
  it("restores a running draft once under StrictMode", async () => {
    const draft = deferred<ShipmentDetail | null>();
    mocks.api.runningDraft.mockReturnValue(draft.promise);
    open();
    await waitFor(() => expect(mocks.api.runningDraft).toHaveBeenCalled());
    expect(screen.queryByLabelText("Goods description")).toBeNull();
    await act(async () => draft.resolve(saved()));
    expect(await screen.findByLabelText("Goods description")).toHaveValue("Saved goods");
    expect(mocks.toast.info).toHaveBeenCalledTimes(1);
    expect(mocks.toast.info).toHaveBeenCalledWith("draft.resumed");
  });

  it.each(["shipment", "template"])("restores a %s when the registry changes during its pending read", async (source) => {
    const firstRegistry = deferred<DocumentRegistry>();
    const secondRegistry = deferred<DocumentRegistry>();
    const record = deferred<ShipmentDetail>();
    mocks.api.documentsRegistry.mockReturnValueOnce(firstRegistry.promise).mockReturnValueOnce(secondRegistry.promise);
    mocks.api.shipment.mockReturnValue(record.promise);
    open(`/wizard/road?${source}=42`);
    await act(async () => firstRegistry.resolve(registry));
    await waitFor(() => expect(mocks.api.shipment).toHaveBeenCalled());
    await act(async () => secondRegistry.resolve({ ...registry }));
    await act(async () => record.resolve(saved()));
    expect(await screen.findByLabelText("Goods description")).toHaveValue("Saved goods");
    expect(mocks.api.runningDraft).not.toHaveBeenCalled();
    if (source === "template") {
      expect(mocks.toast.info).toHaveBeenCalledTimes(1);
      expect(mocks.toast.info).toHaveBeenCalledWith("history.templateOpened");
    }
  });

  it("does not reapply a saved shipment over edits when a late registry response arrives", async () => {
    const firstRegistry = deferred<DocumentRegistry>();
    const secondRegistry = deferred<DocumentRegistry>();
    mocks.api.documentsRegistry.mockReturnValueOnce(firstRegistry.promise).mockReturnValueOnce(secondRegistry.promise);
    open("/wizard/road?shipment=42");
    await act(async () => firstRegistry.resolve(registry));
    const input = await screen.findByLabelText("Goods description");
    fireEvent.change(input, { target: { value: "Edited goods" } });
    await act(async () => secondRegistry.resolve({ ...registry }));
    expect(input).toHaveValue("Edited goods");
    expect(mocks.api.shipment).toHaveBeenCalledTimes(1);
  });

  it("keeps a slow or failed draft read ahead of prefilled autosave and offers retry", async () => {
    vi.useFakeTimers();
    const draft = deferred<ShipmentDetail | null>();
    mocks.preferences.prefill_documents = true;
    mocks.preferences.consignor_name = "Default company";
    mocks.api.runningDraft.mockReturnValueOnce(draft.promise).mockResolvedValueOnce(saved());
    open();
    await act(async () => { await vi.advanceTimersByTimeAsync(3500); });
    expect(mocks.api.saveDraft).not.toHaveBeenCalled();
    expect(screen.queryByLabelText("Goods description")).toBeNull();
    await act(async () => draft.reject(new Error("offline")));
    expect(screen.getByRole("alert")).toHaveTextContent("history.loadFailed");
    await act(async () => { await vi.advanceTimersByTimeAsync(3500); });
    expect(mocks.api.saveDraft).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "overview.retry" }));
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(screen.getByLabelText("Goods description")).toHaveValue("Saved goods");
    await act(async () => { await vi.advanceTimersByTimeAsync(2600); });
    expect(mocks.api.saveDraft).toHaveBeenCalledWith(expect.objectContaining({
      snapshot: expect.objectContaining({ docValues: expect.objectContaining({ consignor_name: "Saved company" }) }),
    }));
  });

  it("carries edits through a modality change without reading the old server draft again", async () => {
    mocks.api.runningDraft.mockResolvedValue(saved());
    open();
    const input = await screen.findByLabelText("Goods description");
    fireEvent.change(input, { target: { value: "Changed before switching" } });
    fireEvent.change(screen.getByRole("combobox", { name: "wizard.mode" }), { target: { value: "rail" } });
    expect(await screen.findByLabelText("Goods description")).toHaveValue("Changed before switching");
    expect(screen.getByRole("combobox", { name: "wizard.mode" })).toHaveValue("rail");
    expect(mocks.api.runningDraft).toHaveBeenCalledTimes(1);
  });

  it("never reads or autosaves drafts where history is disabled", async () => {
    vi.useFakeTimers();
    mocks.settings.history_enabled = false;
    mocks.preferences.prefill_documents = true;
    mocks.preferences.consignor_name = "Default company";
    open();
    await act(async () => { await vi.advanceTimersByTimeAsync(3500); });
    expect(screen.getByLabelText("Goods description")).toBeInTheDocument();
    expect(mocks.api.runningDraft).not.toHaveBeenCalled();
    expect(mocks.api.saveDraft).not.toHaveBeenCalled();
  });
});
