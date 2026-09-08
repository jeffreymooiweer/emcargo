/**
 * The overview: what somebody continuing rather than starting sees.
 *
 * The promise worth pinning is the one made to the owner in as many words:
 * **the chooser at `/` is not moved out of the way for this.** So the page has
 * its own address, and the way back to the tiles is on it.
 *
 * The rest is honesty about what an installation actually has. Where nothing
 * may be stored there is no draft, no count and no recent shipment — and the
 * page says that instead of showing four empty boxes.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ShipmentDetail, ShipmentSummary } from "../api/client";
import OverviewPage from "./OverviewPage";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      options && "time" in options ? `${key}:${options.time}` : key,
    i18n: { language: "nl" },
  }),
}));

const settings = { history_enabled: true };
vi.mock("../settings/preferences", () => ({
  usePreferences: () => ({ publicSettings: settings, preferences: {}, loaded: true, mode: "organisation" }),
}));

const api = vi.hoisted(() => ({
  runningDraft: vi.fn(),
  shipments: vi.fn(),
  trips: vi.fn(),
  discardDraft: vi.fn(),
}));
vi.mock("../api/client", () => ({ api }));

const kept: ShipmentSummary = {
  id: 7, reference: "CP-2026-100", modality: "road", language: "nl", regulations: ["ADR"],
  consignor_name: "Afzender BV", consignee_name: "Ontvanger GmbH", goods_count: 3,
  has_dangerous_goods: true, has_documents: true, created_by: "ada",
  created_at: "2026-09-05T08:00:00Z", updated_at: "2026-09-05T08:00:00Z",
};

const draft = {
  ...kept,
  id: 9, reference: "", is_draft: true, consignee_name: "Müller",
  modality: "sea",
  updated_at: "2026-09-07T10:04:00Z",
  snapshot: { version: 1, modality: "rail", stepKey: "details", draftLines: [], nextId: 2 },
} as unknown as ShipmentDetail;

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/overzicht"]}>
      <Routes>
        <Route path="/overzicht" element={<OverviewPage />} />
        <Route path="/wizard/:modality" element={<p>wizard</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  settings.history_enabled = true;
  api.runningDraft.mockResolvedValue(null);
  api.shipments.mockResolvedValue({ items: [], total: 0, page: 1, per_page: 5 });
  api.trips.mockResolvedValue({ items: [], total: 0, page: 1, per_page: 1 });
  api.discardDraft.mockResolvedValue({ ok: true });
});

describe("the overview", () => {
  it("keeps the way back to the tiles, which are still the front door", async () => {
    renderPage();
    expect(await screen.findByRole("link", { name: "wizard.changeModality" })).toHaveAttribute(
      "href",
      "/?choose=1",
    );
  });

  it("offers every available mode as one press", async () => {
    renderPage();
    expect(await screen.findByRole("button", { name: /modality\.road/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /modality\.inland/ })).toBeInTheDocument();
    // Air is locked, so it is not something to press here.
    expect(screen.queryByRole("button", { name: /modality\.air/ })).toBeNull();
  });

  it("takes you back into the draft, in the mode the draft was in", async () => {
    api.runningDraft.mockResolvedValue(draft);
    renderPage();
    // The snapshot's mode wins over the row's: the row is what the wizard last
    // wrote, the snapshot is what the entry itself says.
    const resume = await screen.findByRole("link", { name: "overview.resume" });
    expect(resume).toHaveAttribute("href", "/wizard/rail");
    expect(screen.getByText("Müller")).toBeInTheDocument();
  });

  it("throws the draft away and stops offering it", async () => {
    api.runningDraft.mockResolvedValue(draft);
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "draft.discard" }));
    expect(api.discardDraft).toHaveBeenCalled();
    await waitFor(() => expect(screen.queryByText("overview.resumeTitle")).toBeNull());
  });

  it("counts today from the server rather than from a page of results", async () => {
    api.shipments.mockImplementation((query: { date_from?: string }) =>
      Promise.resolve(
        query.date_from
          ? { items: [], total: 4, page: 1, per_page: 1 }
          : { items: [kept], total: 1, page: 1, per_page: 5 },
      ),
    );
    api.trips.mockResolvedValue({ items: [], total: 2, page: 1, per_page: 1 });
    renderPage();
    expect(await screen.findByText("4")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("lists what was made before, to open or to start from", async () => {
    api.shipments.mockResolvedValue({ items: [kept], total: 1, page: 1, per_page: 5 });
    renderPage();
    expect(await screen.findByText("CP-2026-100")).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText("review.moreActions"));
    expect(screen.getByRole("link", { name: "overview.open" })).toHaveAttribute(
      "href",
      "/wizard/road?shipment=7",
    );
    expect(screen.getByRole("link", { name: "overview.asTemplate" })).toHaveAttribute(
      "href",
      "/wizard/road?template=7",
    );
  });

  it("leaves the running entry off the list of what was made", async () => {
    // A draft is entry in progress, not a shipment that was made. It has its
    // own box at the top and must not appear twice.
    api.shipments.mockResolvedValue({ items: [draft, kept], total: 2, page: 1, per_page: 5 });
    renderPage();
    await screen.findByText("CP-2026-100");
    expect(screen.queryByText("Müller")).toBeNull();
  });

  it("says there is nothing to come back to where nothing is stored", async () => {
    settings.history_enabled = false;
    renderPage();
    expect(await screen.findByText("overview.introNoHistory")).toBeInTheDocument();
    expect(screen.queryByText("overview.todayTitle")).toBeNull();
    expect(screen.queryByText("overview.recentTitle")).toBeNull();
    // Nothing was asked of a server that keeps nothing.
    expect(api.shipments).not.toHaveBeenCalled();
    // Starting still works.
    expect(screen.getByRole("button", { name: /modality\.road/ })).toBeInTheDocument();
  });
});

it("keeps a draft visible when discarding it failed", async () => {
  api.runningDraft.mockResolvedValue(draft);
  api.discardDraft.mockRejectedValue(new Error("offline"));
  renderPage();
  await userEvent.click(await screen.findByRole("button", { name: "draft.discard" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("overview.loadError");
  expect(screen.getByRole("link", { name: "overview.resume" })).toBeInTheDocument();
});

it("filters the recent list without changing the saved shipments", async () => {
  api.shipments.mockResolvedValue({ items: [kept], total: 1, page: 1, per_page: 5 });
  renderPage();
  await screen.findByText("CP-2026-100");
  await userEvent.type(screen.getByRole("searchbox"), "unmatched");
  expect(screen.queryByText("CP-2026-100")).toBeNull();
  expect(screen.getByText("overview.noResults")).toBeInTheDocument();
  await userEvent.clear(screen.getByRole("searchbox"));
  expect(screen.getByText("CP-2026-100")).toBeInTheDocument();
});

it("opens the paste workflow directly in an available transport mode", async () => {
  renderPage();
  expect(screen.getByRole("link", { name: /overview.paste/ })).toHaveAttribute("href", "/wizard/road?input=paste");
});
