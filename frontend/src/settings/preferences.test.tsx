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
  BROWSER_PREFERENCES_KEY,
  EMPTY_PREFERENCES,
  LANGUAGE_STORAGE_KEY,
  PreferencesProvider,
  applyPreferences,
  readBrowserPreferences,
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

describe("de open installatie", () => {
  // No accounts, so no server-side settings: the browser is the truth. The
  // one call that must never be made is the one to `/settings/me` — the
  // address is not on the server, and a 404 on every page load is exactly
  // the kind of noise a public installation should not produce.
  const shared = {
    default_language: "nl",
    default_theme: "system" as const,
    address_lookup_enabled: true,
    un_cards_enabled: true,
    card_links_enabled: false,
    organisation_name: "",
    organisation_address: "",
    mail_enabled: false,
  };

  it("leest de voorkeuren uit de browser en vraagt ze nooit aan de server", async () => {
    localStorage.setItem(
      BROWSER_PREFERENCES_KEY,
      JSON.stringify(preferences({ consignor_name: "Mooiweer BV", default_unit: "pallet" })),
    );
    const mine = vi.spyOn(api, "mySettings").mockRejectedValue(new Error("404"));
    vi.spyOn(api, "publicSettings").mockResolvedValue(shared);

    render(
      <PreferencesProvider mode="open">
        <Probe />
      </PreferencesProvider>,
    );

    await waitFor(() => expect(screen.getByTestId("loaded")).toHaveTextContent("true"));
    expect(screen.getByTestId("consignor")).toHaveTextContent("Mooiweer BV");
    expect(screen.getByTestId("unit")).toHaveTextContent("pallet");
    expect(mine).not.toHaveBeenCalled();
  });

  it("bewaart een wijziging in de browser, niet op de server", async () => {
    vi.spyOn(api, "publicSettings").mockResolvedValue(shared);
    const server = vi.spyOn(api, "saveMySettings").mockRejectedValue(new Error("404"));

    function Saver() {
      const { save } = usePreferences();
      return (
        <button type="button" onClick={() => void save(preferences({ consignor_name: "Ada" }))}>
          save
        </button>
      );
    }
    render(
      <PreferencesProvider mode="open">
        <Saver />
        <Probe />
      </PreferencesProvider>,
    );

    await waitFor(() => expect(screen.getByTestId("loaded")).toHaveTextContent("true"));
    screen.getByText("save").click();

    await waitFor(() => expect(screen.getByTestId("consignor")).toHaveTextContent("Ada"));
    expect(JSON.parse(localStorage.getItem(BROWSER_PREFERENCES_KEY)!).consignor_name).toBe("Ada");
    expect(server).not.toHaveBeenCalled();
  });

  it("laat een onleesbare of verouderde kopie niet door", () => {
    // Garbage, or a document from an older version with a key that has
    // since changed type, reads as the defaults rather than as an error.
    localStorage.setItem(BROWSER_PREFERENCES_KEY, "{not json");
    expect(readBrowserPreferences()).toEqual(EMPTY_PREFERENCES);

    localStorage.setItem(
      BROWSER_PREFERENCES_KEY,
      JSON.stringify({ consignor_name: "Ada", prefill_documents: "yes", unknown: 1 }),
    );
    const read = readBrowserPreferences();
    expect(read.consignor_name).toBe("Ada");
    expect(read.prefill_documents).toBe(true);
    expect("unknown" in read).toBe(false);
  });
});
