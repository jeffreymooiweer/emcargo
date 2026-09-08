/**
 * Settings that come from the server, in an app that is already painted.
 *
 * Two things can break here, and neither shows up without a test.
 *
 * The first is the order. The preferences come over the network, but something
 * has to be on the screen before the answer is in. So the app keeps a copy in
 * `localStorage` and applies it straight away; the server's answer wins after
 * that. Whoever promotes that copy to the truth gets back exactly the behaviour
 * we wanted rid of: a user who signs in on a second device and finds the app in
 * Dutch and in the light.
 *
 * The second is the fallback. A failed request for settings must not block the
 * wizard — somebody who cannot fetch their preferences still has to be able to
 * make a waybill.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import i18n from "i18next";

import { api, UserPreferences } from "../api/client";
import {
  EMPTY_PREFERENCES,
  LANGUAGE_STORAGE_KEY,
  PreferencesProvider,
  applyPreferences,
  usePreferences,
} from "./preferences";

function preferences(overrides: Partial<UserPreferences> = {}): UserPreferences {
  return { ...EMPTY_PREFERENCES, ...overrides };
}

function Probe() {
  const { preferences: current, loaded } = usePreferences();
  return (
    <div>
      <span data-testid="loaded">{String(loaded)}</span>
      <span data-testid="consignor">{current.consignor_name}</span>
      <span data-testid="unit">{current.default_unit}</span>
    </div>
  );
}

beforeEach(() => {
  localStorage.clear();
  document.documentElement.classList.remove("dark");
  vi.spyOn(i18n, "changeLanguage").mockResolvedValue(((key: string) => key) as never);
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
    }),
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("applyPreferences", () => {
  it("zet het donkere thema aan", () => {
    applyPreferences(preferences({ theme: "dark" }));

    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });

  it("laat 'system' het systeem volgen in plaats van een keuze te bewaren", () => {
    // A stored "light" would keep overruling the system; that is why
    // applySystemTheme erases the key instead of putting a value in it.
    applyPreferences(preferences({ theme: "dark" }));
    applyPreferences(preferences({ theme: "system" }));

    expect(document.documentElement.classList.contains("dark")).toBe(false);
    expect(localStorage.getItem("emcargo-theme")).toBeNull();
  });

  it("bewaart de taal als kopie, zodat de volgende start niet flikkert", () => {
    applyPreferences(preferences({ language: "fr" }));

    expect(i18n.changeLanguage).toHaveBeenCalledWith("fr");
    expect(localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe("fr");
  });

  it("laat een taal die we niet kennen niet door naar i18next", () => {
    // documentLanguage catches it: an unknown code would otherwise produce an
    // empty screen, because there is no translation file for it.
    applyPreferences(preferences({ language: "it" }));

    expect(i18n.changeLanguage).toHaveBeenCalledWith("nl");
  });
});

describe("de voorkeurenprovider", () => {
  it("haalt de voorkeuren op en deelt ze met de rest van de app", async () => {
    vi.spyOn(api, "mySettings").mockResolvedValue(
      preferences({ consignor_name: "Mooiweer BV", default_unit: "pallet", theme: "dark" }),
    );
    vi.spyOn(api, "publicSettings").mockResolvedValue({
      default_language: "nl",
      default_theme: "system",
      address_lookup_enabled: true,
      un_cards_enabled: true,
      card_links_enabled: false,
      organisation_name: "",
      organisation_address: "",
      mail_enabled: false,
    });

    render(
      <PreferencesProvider>
        <Probe />
      </PreferencesProvider>,
    );

    await waitFor(() => expect(screen.getByTestId("loaded")).toHaveTextContent("true"));
    expect(screen.getByTestId("consignor")).toHaveTextContent("Mooiweer BV");
    expect(screen.getByTestId("unit")).toHaveTextContent("pallet");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });

  it("blijft bruikbaar wanneer de instellingen niet op te halen zijn", async () => {
    // No preferences is no reason not to be able to make a waybill.
    vi.spyOn(api, "mySettings").mockRejectedValue(new Error("offline"));
    vi.spyOn(api, "publicSettings").mockRejectedValue(new Error("offline"));

    render(
      <PreferencesProvider>
        <Probe />
      </PreferencesProvider>,
    );

    await waitFor(() => expect(screen.getByTestId("loaded")).toHaveTextContent("true"));
    expect(screen.getByTestId("unit")).toHaveTextContent(EMPTY_PREFERENCES.default_unit);
  });
});

describe("account persistence", () => {
  it("uses the account instead of legacy guest preferences", async () => {
    localStorage.setItem("emcargo-preferences", JSON.stringify(preferences({ consignor_name: "Guest" })));
    vi.spyOn(api, "mySettings").mockResolvedValue(preferences({ consignor_name: "Account" }));
    vi.spyOn(api, "publicSettings").mockRejectedValue(new Error("unavailable"));
    render(<PreferencesProvider><Probe /></PreferencesProvider>);
    await waitFor(() => expect(screen.getByTestId("consignor")).toHaveTextContent("Account"));
  });

  it("persists edits through the authenticated API", async () => {
    vi.spyOn(api, "mySettings").mockResolvedValue(preferences());
    vi.spyOn(api, "publicSettings").mockRejectedValue(new Error("unavailable"));
    const saved = preferences({ consignor_name: "Ada" });
    const server = vi.spyOn(api, "saveMySettings").mockResolvedValue(saved);
    function Saver() {
      const { save } = usePreferences();
      return <button onClick={() => void save(saved)}>save</button>;
    }
    render(<PreferencesProvider><Saver /><Probe /></PreferencesProvider>);
    await waitFor(() => expect(screen.getByTestId("loaded")).toHaveTextContent("true"));
    screen.getByText("save").click();
    await waitFor(() => expect(screen.getByTestId("consignor")).toHaveTextContent("Ada"));
    expect(server).toHaveBeenCalledWith(saved);
    expect(localStorage.getItem("emcargo-preferences")).toBeNull();
  });
});
