/**
 * The shipments page: what it lists, what it says when there is nothing to
 * list, and the one action that must ask first.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ShipmentSummary } from "../api/client";
import ShipmentsPage, { wizardLinkFor } from "./ShipmentsPage";
import { ToastProvider } from "../toast/ToastProvider";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      options && "count" in options ? `${key}:${options.count}/${options.total}` : key,
    i18n: { language: "nl" },
  }),
}));

const settings = { history_enabled: true };
vi.mock("../settings/preferences", () => ({
  usePreferences: () => ({ publicSettings: settings, preferences: {}, loaded: true, mode: "organisation" }),
}));

const kept: ShipmentSummary[] = [
  {
    id: 7, reference: "CP-2026-100", modality: "road", language: "nl", regulations: ["ADR"],
    consignor_name: "Afzender BV", consignee_name: "Ontvanger GmbH", goods_count: 3,
    has_dangerous_goods: true, has_documents: true, created_by: "ada",
    created_at: "2026-09-05T08:00:00Z", updated_at: "2026-09-05T08:00:00Z",
  },
  {
    id: 8, reference: "", modality: "sea", language: "en", regulations: [],
    consignor_name: "Afzender BV", consignee_name: "", goods_count: 1,
    has_dangerous_goods: false, has_documents: false, created_by: "",
    created_at: "2026-09-04T08:00:00Z", updated_at: "2026-09-04T08:00:00Z",
  },
];

const api = vi.hoisted(() => ({
  shipments: vi.fn(),
  shipment: vi.fn(),
  forgetShipment: vi.fn(),
  shipmentDocuments: vi.fn(),
  departments: vi.fn(),
  runningDraft: vi.fn(),
  shipmentExportUrl: (id: number) => `/api/shipments/${id}/export.json`,
}));
vi.mock("../api/client", () => ({ api }));

function renderAt(path: string, user?: { id: number; username: string; email: string; role: string; active: boolean }) {
  return render(
    <ToastProvider>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/shipments" element={<ShipmentsPage user={user} />} />
          <Route path="/shipments/:id" element={<ShipmentsPage user={user} />} />
          <Route path="/wizard/:modality" element={<p>wizard</p>} />
        </Routes>
      </MemoryRouter>
    </ToastProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  settings.history_enabled = true;
  api.shipments.mockResolvedValue({ items: kept, total: 2, page: 1, per_page: 25 });
  api.shipment.mockImplementation(async (id: number) => ({
    ...kept.find((s) => s.id === id)!,
    snapshot: { version: 1 },
    export: { format: "emcargo.shipment", documents: ["cmr"] },
  }));
  api.forgetShipment.mockResolvedValue({ ok: true });
  api.departments.mockResolvedValue([{ id: 1, name: "Sales", users: 2, shipments: 5 }]);
  api.runningDraft.mockResolvedValue(null);
});

it("sends selected local shipment dates as complete UTC day bounds", async () => {
  renderAt("/shipments");
  await screen.findAllByText("CP-2026-100");
  fireEvent.change(screen.getByLabelText("history.from"), { target: { value: "2026-03-29" } });
  fireEvent.change(screen.getByLabelText("history.to"), { target: { value: "2026-03-29" } });
  await waitFor(() => expect(api.shipments).toHaveBeenLastCalledWith(expect.objectContaining({
    date_from: new Date(2026, 2, 29, 0).toISOString(),
    date_to: new Date(2026, 2, 29, 23, 59, 59, 999).toISOString().replace(".999Z", ".999999Z"),
  })));
  fireEvent.change(screen.getByLabelText("history.from"), { target: { value: "" } });
  fireEvent.change(screen.getByLabelText("history.to"), { target: { value: "" } });
  await waitFor(() => expect(api.shipments).toHaveBeenLastCalledWith(expect.objectContaining({
    date_from: undefined, date_to: undefined,
  })));
});

describe("de zendingenpagina", () => {
  it("zegt dat er niets bewaard wordt waar de historie uitstaat", () => {
    settings.history_enabled = false;
    renderAt("/shipments");
    expect(screen.getByText("history.off")).toBeInTheDocument();
    expect(api.shipments).not.toHaveBeenCalled();
  });

  it("toont de bewaarde zendingen met referentie, partijen en een DG-badge", async () => {
    renderAt("/shipments");
    expect(await screen.findAllByText("CP-2026-100")).not.toHaveLength(0);
    expect(screen.getAllByText("Afzender BV → Ontvanger GmbH").length).toBeGreaterThan(0);
    // The one without a reference says so instead of showing an empty cell.
    expect(screen.getAllByText("history.noReference").length).toBeGreaterThan(0);
    // The regimes stand on the badge; a shipment without dangerous goods has
    // none. The phone cards and the desktop table are both in the DOM (CSS
    // shows one), so the one DG shipment carries two badges.
    expect(screen.getAllByTitle("history.dg")).toHaveLength(2);
    expect(screen.getAllByText("ADR")).toHaveLength(2);
    expect(screen.getByText("history.count:2/2")).toBeInTheDocument();
  });

  it("biedt de drie dingen die je met een bewaarde zending doet, op de regel zelf", async () => {
    // The baseline found no reuse action on the list at all: the detail page
    // was compulsory before anything could be done.
    renderAt("/shipments");
    await screen.findAllByText("CP-2026-100");
    const edit = screen.getAllByRole("link", { name: "history.edit" });
    expect(edit[0]).toHaveAttribute("href", "/wizard/road?shipment=7");
    const template = screen.getAllByRole("link", { name: "history.useTemplate" });
    expect(template[0]).toHaveAttribute("href", "/wizard/road?template=7");
    // Only the one that has a kept package is offered its documents again.
    expect(screen.getAllByRole("button", { name: "history.documents" })).toHaveLength(2);
  });

  it("zegt van elke regel wat hij is", async () => {
    renderAt("/shipments");
    await screen.findAllByText("CP-2026-100");
    // One has a kept package and is ready; the other stopped before that.
    expect(screen.getAllByText("history.stateReady")).toHaveLength(2);
    expect(screen.getAllByText("history.stateOpen")).toHaveLength(2);
  });

  it("maakt van een selectie een rit", async () => {
    renderAt("/shipments");
    await screen.findAllByText("CP-2026-100");
    // Each shipment is on the page twice — as a card and as a table row, one
    // of which the width hides — and since v1.206.0 both boxes carry the same
    // name. They used to differ: the card's said only "Select", five times
    // over, with nothing saying which shipment each one selected.
    await userEvent.click(screen.getAllByLabelText("history.pick — CP-2026-100")[0]);
    await userEvent.click(screen.getAllByLabelText("history.pick — history.noReference")[0]);
    expect(screen.getByText(/history\.picked:2/)).toBeInTheDocument();
    // The trip is opened with the selection in the address; the server
    // decides per shipment whether this viewer may read it.
    expect(screen.getByRole("link", { name: /history\.toTrip:2/ })).toHaveAttribute(
      "href", "/trips?shipments=7,8");
  });

  it("zet het concept waar de gebruiker mee bezig was bovenaan", async () => {
    api.runningDraft.mockResolvedValue({
      ...kept[0], id: 12, reference: "Concept", is_draft: true,
      snapshot: {}, export: {},
    });
    renderAt("/shipments");
    expect(await screen.findByText("history.stateDraft")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "history.resumeDraft" })).toHaveAttribute(
      "href", "/wizard/road?shipment=12");
  });

  it("stuurt de zoekopdracht en de modaliteit als filters mee", async () => {
    renderAt("/shipments");
    await screen.findAllByText("CP-2026-100");
    await userEvent.selectOptions(screen.getByLabelText("history.modality"), "sea");
    await waitFor(() =>
      expect(api.shipments).toHaveBeenLastCalledWith(expect.objectContaining({ modality: "sea", page: 1 })),
    );
  });

  it("opent een zending met de knoppen die erbij horen, en verwijdert pas na bevestiging", async () => {
    renderAt("/shipments/7");
    expect(await screen.findByRole("heading", { name: "CP-2026-100" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "history.open" })).toHaveAttribute("href", "/wizard/road?shipment=7");
    // A template is the same shipment opened as a new one: its own address.
    expect(screen.getByRole("link", { name: "history.useTemplate" })).toHaveAttribute("href", "/wizard/road?template=7");
    expect(screen.getByRole("button", { name: "history.documents" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "history.remove" }));
    expect(api.forgetShipment).not.toHaveBeenCalled();
    // The dialog's confirm button carries the same label as the trigger.
    const confirms = screen.getAllByRole("button", { name: "history.remove" });
    await userEvent.click(confirms[confirms.length - 1]);
    await waitFor(() => expect(api.forgetShipment).toHaveBeenCalledWith(7));
  });

  it("biedt zonder bewaard pakket geen documenten opnieuw aan", async () => {
    renderAt("/shipments/8");
    expect(await screen.findByRole("heading", { name: "history.noReference" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "history.documents" })).toBeNull();
    expect(screen.getByText("history.documentsNone")).toBeInTheDocument();
  });

  it("geeft alleen een beheerder het afdelingsfilter, en stuurt de keuze mee", async () => {
    // Anybody else sees their own department whatever they ask for, so a
    // filter would only promise a choice the server does not offer them.
    renderAt("/shipments");
    await screen.findAllByText("CP-2026-100");
    expect(screen.queryByLabelText("departments.userDepartment")).toBeNull();
    expect(api.departments).not.toHaveBeenCalled();

    renderAt("/shipments", { id: 1, username: "root", email: "r@example.com", role: "admin", active: true });
    const filter = await screen.findByLabelText("departments.userDepartment");
    await userEvent.selectOptions(filter, "none");
    await waitFor(() =>
      expect(api.shipments).toHaveBeenLastCalledWith(expect.objectContaining({ department: "none" })),
    );
    await userEvent.selectOptions(filter, "1");
    await waitFor(() =>
      expect(api.shipments).toHaveBeenLastCalledWith(expect.objectContaining({ department: "1" })),
    );
  });

  it("opent een zending in de wizard van haar eigen modaliteit", () => {
    expect(wizardLinkFor(kept[1])).toBe("/wizard/sea?shipment=8");
  });
});
