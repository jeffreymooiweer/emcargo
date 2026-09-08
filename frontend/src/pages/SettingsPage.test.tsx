/**
 * The settings, grouped into tabs.
 *
 * One long scroll put the personal fields and the instance-wide ones in a
 * single list, which they are emphatically not: a theme sits beside a switch
 * that decides whether this installation talks to the internet at all. The
 * tabs separate them, the dropdown does the same on a phone where a tab row
 * would wrap or scroll out of sight, and the administrator's groups exist
 * only for an administrator.
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SettingsPage from "./SettingsPage";
import { ToastProvider } from "../toast/ToastProvider";
import { MemoryRouter } from "react-router";
import { User } from "../api/client";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, vars?: Record<string, unknown>) =>
      vars && typeof vars.defaultValue === "string" ? String(vars.defaultValue) : key,
    i18n: { language: "nl" },
  }),
}));

vi.mock("../api/client", () => ({
  api: {
    health: vi.fn().mockResolvedValue({ version: "1.115.0" }),
    settingsOptions: vi.fn().mockResolvedValue({ modalities: ["road"], units: [] }),
    instanceSettings: vi.fn().mockResolvedValue({}),
    organisationSettings: vi.fn().mockResolvedValue({ organisation_name: "Test", organisation_address: "", default_language: "nl", default_theme: "dark" }),
    assistantStatus: vi.fn().mockResolvedValue({
      mode: "deterministic", installed: false, available: true, installable: true,
      download: { state: "idle" },
    }),
    // The maintenance tab's panels ask for their state on mount.
    updateStatus: vi.fn().mockResolvedValue({current:"2.1.1",enabled:false}),
    updateCapability: vi.fn().mockResolvedValue({ available: false }),
    updateState: vi.fn().mockResolvedValue({ current: "1.115.0", state: null }),
    unCardStoreStatus: vi.fn().mockResolvedValue({
      local: { installed: false }, remote: null,
    }),
    // My details carries the second factor, which asks for its own state.
    twoFactorStatus: vi.fn().mockResolvedValue({
      active: false, method: "", required: false, recovery_codes_left: 0,
    }),
  },
}));

const preferences = {
  theme: "system", language: "nl", default_modality: "", default_unit: "pcs",
  prefill_documents: true, consignor_name: "", consignor_address: "",
  consignor_contact: "", carrier_name: "", loading_point: "",
  emergency_contact: "", signature_image: "",
};

vi.mock("../settings/preferences", () => ({
  usePreferences: () => ({ preferences, save: vi.fn(), loaded: true }),
}));

/** The open tab lives in the address now, so the page needs a router — and a
 *  test can point at a tab the way the two-factor notice does. */
function renderAt(user: User, path = "/settings") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <ToastProvider>
        <SettingsPage user={user} />
      </ToastProvider>
    </MemoryRouter>,
  );
}

const userOf = (role: string) => ({ id: 1, username: "u", role, active: true }) as unknown as User;

beforeEach(() => vi.clearAllMocks());

describe("SettingsPage tabs", () => {
  it("opens on appearance and shows only that group", async () => {
    renderAt(userOf("user"));
    expect(await screen.findByText("settings.appearance")).toBeTruthy();
    expect(screen.queryByText("settings.myDetails")).toBeNull();
    expect(screen.queryByText("settings.shipmentDefaults")).toBeNull();
  });

  it("switching tabs shows the other group", async () => {
    renderAt(userOf("user"));
    await userEvent.click(await screen.findByRole("button", { name: "settings.tabDetails" }));
    expect(screen.getByText("settings.myDetails")).toBeTruthy();
    expect(screen.queryByText("settings.appearance")).toBeNull();
    // The save button travels with the personal tabs; one draft, one button.
    expect(screen.getByRole("button", { name: "settings.save" })).toBeTruthy();
  });

  it("the phone dropdown selects the same groups", async () => {
    renderAt(userOf("user"));
    const picker = await screen.findByLabelText("settings.tabPick");
    await userEvent.selectOptions(picker, "shipment");
    expect(screen.getByText("settings.shipmentDefaults")).toBeTruthy();
  });

  it("the administrator groups exist only for an administrator", async () => {
    const { unmount } = renderAt(userOf("user"));
    await screen.findByText("settings.appearance");
    expect(screen.queryByRole("button", { name: "settingsNav.organisation" })).toBeNull();
    expect(screen.queryByRole("button", { name: "settings.adminUpdates" })).toBeNull();
    unmount();

    renderAt(userOf("admin"));
    expect(await screen.findByRole("button", { name: "settingsNav.organisation" })).toBeTruthy();
    // Maintenance actions now have distinct destinations. The update must be
    // discoverable without loading the UN-card store or assistant model.
    await userEvent.click(screen.getByRole("button", { name: "settings.adminUpdates" }));
    expect(await screen.findByRole("heading", { name: "settings.adminUpdates" })).toBeTruthy();
    expect(screen.queryByText("settings.unCardsStoreTitle")).toBeNull();
    expect(screen.queryByText("settings.assistantTitle")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "settingsNav.cards" }));
    expect(await screen.findByText("settings.unCardsStoreTitle")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "settingsNav.assistant" }));
    expect(await screen.findByText("settings.assistantTitle")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "settings.saveAdmin" })).toBeNull();
  });

  it("a link can point straight at a tab", async () => {
    // What the two-factor notice relies on: its button lands on the panel it
    // is about, not on the theme settings with the panel three tabs away.
    renderAt(userOf("user"), "/settings?tab=details");
    expect(await screen.findByText("settings.myDetails")).toBeTruthy();
    expect(screen.queryByText("settings.appearance")).toBeNull();
  });

  it("an unknown tab in the address falls back rather than showing nothing", async () => {
    renderAt(userOf("user"), "/settings?tab=nonsense");
    expect(await screen.findByText("settings.appearance")).toBeTruthy();
  });

  it("a plain user cannot reach an administrator tab through the address", async () => {
    renderAt(userOf("user"), "/settings?tab=admin");
    // The server refuses their writes anyway; this keeps the screen honest.
    expect(await screen.findByText("settings.appearance")).toBeTruthy();
  });
});


it("gives Super Users organisation defaults without exposing system or DG policy tabs", async () => {
  renderAt(userOf("super_user"), "/settings?tab=admin");
  expect(await screen.findByDisplayValue("Test")).toBeInTheDocument();
  for (const label of ["settings.adminBranding", "settings.mailTitle", "settingsNav.connections", "settings.adminUpdates", "settingsNav.assistant", "dgReview.settingsTitle"]) {
    expect(screen.queryByRole("button", { name: label })).toBeNull();
  }
  await userEvent.click(screen.getByRole("button", { name: "settingsNav.security" }));
  expect(screen.queryByText("settingsNav.accessPolicy")).toBeNull();
});
