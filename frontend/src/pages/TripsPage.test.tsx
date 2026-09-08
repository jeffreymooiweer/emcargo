/**
 * The trips page: what it lists, what it says where the history is off, the
 * record with the kept judgement, and the one action that must ask first.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { TripSummary } from "../api/client";
import TripsPage, { groupageLinkFor } from "./TripsPage";
import { ToastProvider } from "../toast/ToastProvider";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      options && "count" in options ? `${key}:${options.count}${"total" in options ? `/${options.total}` : ""}` : key,
    i18n: { language: "nl" },
  }),
}));

const settings = { history_enabled: true };
vi.mock("../settings/preferences", () => ({
  usePreferences: () => ({ publicSettings: settings, preferences: {}, loaded: true, mode: "organisation" }),
}));

const kept: TripSummary[] = [
  {
    id: 3, name: "Maandag", language: "nl", regulations: ["ADR"], consignment_count: 2,
    total_points: 1200, exemption_lost: true, unit_max_mass_tonnes: 18, created_by: "ada",
    created_at: "2026-09-05T08:00:00Z", updated_at: "2026-09-05T08:00:00Z",
  },
  {
    id: 4, name: "", language: "nl", regulations: ["ADR"], consignment_count: 3,
    total_points: 600, exemption_lost: false, unit_max_mass_tonnes: null, created_by: "",
    created_at: "2026-09-04T08:00:00Z", updated_at: "2026-09-04T08:00:00Z",
  },
];

const api = vi.hoisted(() => ({
  trips: vi.fn(),
  trip: vi.fn(),
  forgetTrip: vi.fn(),
  departments: vi.fn(),
}));
vi.mock("../api/client", () => ({ api }));

function renderAt(path: string, user?: { id: number; username: string; email: string; role: string; active: boolean }) {
  return render(
    <ToastProvider>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/trips" element={<TripsPage user={user} />} />
          <Route path="/trips/:id" element={<TripsPage user={user} />} />
          <Route path="/groupage" element={<p>groupage</p>} />
        </Routes>
      </MemoryRouter>
    </ToastProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  settings.history_enabled = true;
  api.trips.mockResolvedValue({ items: kept, total: 2, page: 1, per_page: 25 });
  api.trip.mockImplementation(async (id: number) => ({
    ...kept.find((t) => t.id === id)!,
    consignments: [
      { name: "Klant A", entries: [], shipment_id: 7 },
      { name: "Klant B", entries: [], shipment_id: null },
    ],
    result: {
      consignments: [
        { name: "Klant A", points: 600, exempt: true, status: "exempt_possible" },
        { name: "Klant B", points: 600, exempt: true, status: "exempt_possible" },
      ],
      adr_points: { total_points: 1200, threshold: 1000, status: "above_threshold" },
      mixed_loading: [{ message: "niet samen", products: "UN 1203 / UN 1263" }],
      lq_marking: { rule: "ADR 3.4.13/3.4.14", message: "LQ-tekst", lq_gross_kg: 0, required: false, reason: "x" },
      exemption_lost: { severity: "warning", rule: "ADR 1.1.3.6", consignments: ["Klant A", "Klant B"], message: "vervalt" },
    },
    editions: { adr: "2025" },
  }));
  api.forgetTrip.mockResolvedValue({ ok: true });
  api.departments.mockResolvedValue([]);
});

it("sends selected local trip dates as complete UTC day bounds", async () => {
  renderAt("/trips");
  await screen.findAllByText("Maandag");
  fireEvent.change(screen.getByLabelText("history.from"), { target: { value: "2026-10-25" } });
  fireEvent.change(screen.getByLabelText("history.to"), { target: { value: "2026-10-25" } });
  await waitFor(() => expect(api.trips).toHaveBeenLastCalledWith(expect.objectContaining({
    date_from: new Date(2026, 9, 25, 0).toISOString(),
    date_to: new Date(2026, 9, 25, 23, 59, 59, 999).toISOString().replace(".999Z", ".999999Z"),
  })));
  fireEvent.change(screen.getByLabelText("history.from"), { target: { value: "" } });
  fireEvent.change(screen.getByLabelText("history.to"), { target: { value: "" } });
  await waitFor(() => expect(api.trips).toHaveBeenLastCalledWith(expect.objectContaining({
    date_from: undefined, date_to: undefined,
  })));
});

describe("de rittenpagina", () => {
  it("zegt dat er niets bewaard wordt waar de historie uitstaat", () => {
    settings.history_enabled = false;
    renderAt("/trips");
    expect(screen.getByText("history.off")).toBeInTheDocument();
    expect(api.trips).not.toHaveBeenCalled();
  });

  it("toont de bewaarde ritten met het verlies van de vrijstelling als merk", async () => {
    renderAt("/trips");
    expect((await screen.findAllByText("Maandag")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("trips.noName").length).toBeGreaterThan(0);
    expect(screen.getAllByText("trips.exemptionLostShort")).toHaveLength(2); // card and row
    expect(screen.getByText("trips.count:2/2")).toBeInTheDocument();
  });

  it("stuurt de zoekopdracht mee", async () => {
    renderAt("/trips");
    await screen.findAllByText("Maandag");
    await userEvent.type(screen.getByLabelText("trips.search"), "maan");
    await waitFor(() =>
      expect(api.trips).toHaveBeenLastCalledWith(expect.objectContaining({ q: "maan", page: 1 })));
  });

  it("toont het bewaarde oordeel en heropent op de groepagepagina", async () => {
    renderAt("/trips/3");
    expect(await screen.findByText("groupage.exemptionLost")).toBeInTheDocument();
    expect(screen.getByText("vervalt")).toBeInTheDocument();
    expect(screen.getByText("niet samen")).toBeInTheDocument();
    expect(screen.getByText("LQ-tekst")).toBeInTheDocument();
    expect(screen.getByText("Klant A, Klant B")).toBeInTheDocument();
    expect(screen.getByText("ADR 2025")).toBeInTheDocument();
    // The judgement is shown as kept, not recomputed.
    expect(screen.getByText("1200")).toBeInTheDocument();
    expect(groupageLinkFor(kept[0])).toBe("/groupage?trip=3");
    await userEvent.click(screen.getByText("trips.reopen"));
    expect(await screen.findByText("groupage")).toBeInTheDocument();
  });

  it("verwijdert pas na bevestiging", async () => {
    renderAt("/trips/3");
    await screen.findByText("groupage.exemptionLost");
    await userEvent.click(screen.getByRole("button", { name: "trips.remove" }));
    expect(api.forgetTrip).not.toHaveBeenCalled();
    // The dialog's confirm button carries the same label as the trigger.
    const confirms = await screen.findAllByRole("button", { name: "trips.remove" });
    await userEvent.click(confirms[confirms.length - 1]);
    await waitFor(() => expect(api.forgetTrip).toHaveBeenCalledWith(3));
  });
});
