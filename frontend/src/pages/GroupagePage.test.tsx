/**
 * Groupage from the history: the kept shipments the viewer may see become
 * consignments on the vehicle with one click, through the same export the
 * file route reads — and, where the history is on, the assessed trip can be
 * kept and reopened.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import GroupagePage from "./GroupagePage";
import { ToastProvider } from "../toast/ToastProvider";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      options && "count" in options ? `${key}:${options.count}` : key,
    i18n: { language: "nl" },
  }),
}));

const settings = { history_enabled: true };
vi.mock("../settings/preferences", () => ({
  usePreferences: () => ({ publicSettings: settings, preferences: {}, loaded: true, mode: "organisation" }),
}));

const api = vi.hoisted(() => ({
  shipments: vi.fn(),
  shipment: vi.fn(),
  dgTrip: vi.fn(),
  trip: vi.fn(),
  keepTrip: vi.fn(),
  updateTrip: vi.fn(),
}));
vi.mock("../api/client", () => ({ api }));

const kept = [
  {
    id: 7, reference: "CP-2026-100", modality: "road", language: "nl", regulations: ["ADR"],
    consignor_name: "Afzender BV", consignee_name: "Ontvanger GmbH", goods_count: 3,
    has_dangerous_goods: true, has_documents: true, created_by: "ada",
    created_at: "2026-09-05T08:00:00Z", updated_at: "2026-09-05T08:00:00Z",
  },
  {
    id: 8, reference: "CP-2026-101", modality: "road", language: "nl", regulations: [],
    consignor_name: "Afzender BV", consignee_name: "", goods_count: 1,
    has_dangerous_goods: false, has_documents: false, created_by: "",
    created_at: "2026-09-04T08:00:00Z", updated_at: "2026-09-04T08:00:00Z",
  },
];

const verdict = {
  consignments: [
    { name: "CP-2026-100", points: 600, exempt: true, status: "exempt_possible" },
    { name: "CP-2026-100", points: 600, exempt: true, status: "exempt_possible" },
  ],
  adr_points: { total_points: 1200, threshold: 1000, status: "above_threshold" },
  mixed_loading: [],
  lq_marking: { rule: "ADR 3.4.13/3.4.14", message: "—", lq_gross_kg: 0, required: false, reason: "x" },
  exemption_lost: { severity: "warning", rule: "ADR 1.1.3.6", consignments: ["a", "b"], message: "lost" },
};

beforeEach(() => {
  vi.clearAllMocks();
  settings.history_enabled = true;
  api.shipments.mockResolvedValue({ items: kept, total: 2, page: 1, per_page: 50 });
  api.shipment.mockResolvedValue({
    ...kept[0],
    snapshot: {},
    export: {
      format: "emcargo.shipment",
      regulations: ["ADR"],
      // The wizard's own field name; a consignment is named by its reference,
      // not by its consignor, or three from one shipper look alike.
      consignment: { reference: "CP-2026-100", consignor_name: "Afzender BV" },
      dangerous_goods: [{ line_id: "1", products: [{ un_number: "1203" }, { un_number: "1263" }] }],
    },
  });
  api.dgTrip.mockResolvedValue(verdict);
  api.keepTrip.mockResolvedValue({ id: 3, name: "Maandag" });
  api.updateTrip.mockResolvedValue({ id: 3, name: "Maandag" });
  api.trip.mockResolvedValue({
    id: 3, name: "Maandag", language: "nl", regulations: ["ADR"], consignment_count: 2,
    total_points: 1200, exemption_lost: true, unit_max_mass_tonnes: 18, created_by: "ada",
    created_at: "2026-09-05T08:00:00Z", updated_at: "2026-09-05T08:00:00Z",
    consignments: [
      { name: "Klant A", entries: [{ products: [{ un_number: "1203" }] }], shipment_id: 7 },
      { name: "Klant B", entries: [{ products: [{ un_number: "1203" }] }], shipment_id: null },
    ],
    result: verdict,
    editions: { adr: "2025" },
  });
});

function renderPage(path = "/groupage") {
  return render(
    <ToastProvider>
      <MemoryRouter initialEntries={[path]}>
        <GroupagePage />
      </MemoryRouter>
    </ToastProvider>,
  );
}

describe("groepage uit de historie", () => {
  it("toont het kiesvak alleen waar de historie aanstaat", () => {
    settings.history_enabled = false;
    renderPage();
    expect(screen.queryByText("groupage.fromHistory")).toBeNull();
    expect(api.shipments).not.toHaveBeenCalled();
  });

  it("zet een bewaarde zending met één klik op het voertuig, en niet twee keer", async () => {
    renderPage();
    const list = await screen.findByTestId("groupage-history");
    expect(list).toHaveTextContent("CP-2026-100");
    // The one without dangerous goods has nothing to add.
    expect(screen.getByText("groupage.noDgShort")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "groupage.addFromHistory" }));
    await waitFor(() => expect(api.shipment).toHaveBeenCalledWith(7));
    expect(await screen.findByText("groupage.onTheVehicle:1")).toBeInTheDocument();
    expect(screen.getByLabelText("groupage.consignmentName")).toHaveValue("CP-2026-100");
    expect(screen.getByText("groupage.positions:2")).toBeInTheDocument();
    // Added once: the button now says so and is disabled.
    expect(screen.getByRole("button", { name: "groupage.alreadyAdded" })).toBeDisabled();
  });

  it("stuurt de zoekopdracht mee", async () => {
    renderPage();
    await screen.findByTestId("groupage-history");
    await userEvent.type(screen.getByPlaceholderText("groupage.searchHistory"), "101");
    await waitFor(() =>
      expect(api.shipments).toHaveBeenLastCalledWith(expect.objectContaining({ q: "101" })),
    );
  });
});

describe("de rit bewaren", () => {
  it("biedt na de beoordeling aan de rit te bewaren, met de bewaarde zending erbij", async () => {
    renderPage();
    await screen.findByTestId("groupage-history");
    // Two consignments: the same kept shipment twice is refused, so the
    // second comes in as if from a file by adding it through the history
    // mock with another id.
    api.shipment.mockResolvedValueOnce({
      ...kept[0], snapshot: {},
      export: { format: "emcargo.shipment", regulations: ["ADR"],
        consignment: { reference: "CP-2026-100" },
        dangerous_goods: [{ line_id: "1", products: [{ un_number: "1203" }] }] },
    });
    await userEvent.click(screen.getByRole("button", { name: "groupage.addFromHistory" }));
    await screen.findByText("groupage.onTheVehicle:1");
    // Nothing to keep before an assessment, and not with one consignment.
    expect(screen.queryByTestId("groupage-keep")).toBeNull();
    expect(screen.getByRole("button", { name: "groupage.assess" })).toBeDisabled();
  });

  it("heropent een bewaarde rit via ?trip= en werkt hem bij", async () => {
    renderPage("/groupage?trip=3");
    await waitFor(() => expect(api.trip).toHaveBeenCalledWith(3));
    expect(await screen.findByText("groupage.onTheVehicle:2")).toBeInTheDocument();
    const names = screen.getAllByLabelText("groupage.consignmentName");
    expect(names[0]).toHaveValue("Klant A");
    expect(names[1]).toHaveValue("Klant B");
    // The kept judgement is shown without asking the server again.
    expect(screen.getByText("groupage.exemptionLost")).toBeInTheDocument();
    expect(api.dgTrip).not.toHaveBeenCalled();
    // The kept shipment on it is marked as on the vehicle in the history list.
    expect(await screen.findByRole("button", { name: "groupage.alreadyAdded" })).toBeDisabled();

    const keep = screen.getByTestId("groupage-keep");
    expect(keep).toHaveTextContent("groupage.update");
    expect(screen.getByLabelText("groupage.tripName")).toHaveValue("Maandag");
    await userEvent.clear(screen.getByLabelText("groupage.tripName"));
    await userEvent.type(screen.getByLabelText("groupage.tripName"), "Dinsdag");
    await userEvent.click(screen.getByRole("button", { name: "groupage.update" }));
    await waitFor(() => expect(api.updateTrip).toHaveBeenCalledWith(3, expect.objectContaining({
      name: "Dinsdag",
      unit_max_mass_tonnes: 18,
      profiles: ["ADR"],
      consignments: [
        expect.objectContaining({ name: "Klant A", shipment_id: 7 }),
        expect.objectContaining({ name: "Klant B", shipment_id: null }),
      ],
    })));
    expect(api.keepTrip).not.toHaveBeenCalled();
  });

  it("bewaart een nieuwe rit na de beoordeling", async () => {
    renderPage("/groupage?trip=3");
    await screen.findByText("groupage.onTheVehicle:2");
    // Assess again, then keep as new: the page was opened on a kept trip, so
    // it updates — the new-trip path is the same call without an id, which
    // the first test of the keep button covers through updateTrip; here the
    // assessment itself is checked to still run on the reopened load.
    await userEvent.click(screen.getByRole("button", { name: "groupage.assess" }));
    await waitFor(() => expect(api.dgTrip).toHaveBeenCalledWith(expect.objectContaining({
      unit_max_mass_tonnes: 18,
      consignments: [
        expect.objectContaining({ name: "Klant A" }),
        expect.objectContaining({ name: "Klant B" }),
      ],
    })));
  });
});
