/**
 * Which modalities may draw up documents, and the lock that has three ways in.
 *
 * Air is built and reachable and *wrong* in ways that do not announce
 * themselves. A half-right document is worse than no document: it is signed
 * and handed over, and the consignor has no way to see which half was right.
 *
 * Inland waterway came off the lock in v1.63.0. It went on in v1.60.0 because
 * it answered its separation question with the road table and held no cone
 * data; the exemption, the separation of 7.1.4.3 and the signals of 7.1.5.0
 * now all come out of the ADN itself. The tank vessel regime is still missing
 * and a tank vessel consignment cannot be entered here at all — this wizard
 * models packages — so what can be drawn up is what is covered.
 *
 * The reason this file exists rather than a line in the component is that the
 * tile is not the only way in. A bookmark reaches `/wizard/rail` without
 * touching a tile, and a `default_modality` set while a modality was open
 * navigates there on its own. Guarding the tiles alone guards the honest route
 * and leaves the other two open — which is the shape of lock that gets found
 * out in production rather than in review.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { describe, expect, it, vi } from "vitest";

import ModalitySelectPage, {
  AVAILABLE_MODALITIES,
  MODALITIES,
  isModalityAvailable,
} from "./ModalitySelectPage";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "nl" } }),
}));

const preferences = { default_modality: undefined as string | undefined };
vi.mock("../settings/preferences", () => ({
  usePreferences: () => ({ preferences, loaded: true }),
}));

const branding = { name: "", logo: null as string | null, modalities: {} as Record<string, string | null> };
vi.mock("../branding", () => ({
  useBranding: () => ({ branding, refresh: async () => {} }),
}));

function renderAt(path = "/") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/" element={<ModalitySelectPage />} />
        <Route path="/wizard/:modality" element={<p>wizard</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("de modaliteitkeuze", () => {
  it("laat wegvervoer, spoorvervoer, zeevervoer en binnenvaart toe", () => {
    // Rail came off the lock in v1.122.0 and sea in v1.152.0, once chapter
    // 5.3 was derived (v1.150.0) and the flow was verified end to end. Air
    // stays locked: its one demonstration (v1.117.0) is over and the IATA
    // quantity tables are still not held.
    expect([...AVAILABLE_MODALITIES]).toEqual(["road", "rail", "sea", "inland"]);
    for (const key of AVAILABLE_MODALITIES) {
      expect(isModalityAvailable(key)).toBe(true);
    }
    // Everything else stays locked — the lock is not a hint.
    for (const key of MODALITIES.filter((m) => !AVAILABLE_MODALITIES.includes(m))) {
      expect(isModalityAvailable(key)).toBe(false);
    }
  });

  it("explains unavailable modes in a disclosure without offering navigation", async () => {
    preferences.default_modality = undefined;
    renderAt("/?choose=1");
    await userEvent.click(screen.getByText("studio.otherModes"));
    for (const key of ["air", "multimodal"]) {
      expect(screen.getByText(`modality.${key}`)).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: new RegExp(`modality.${key}`) })).not.toBeInTheDocument();
    }
    expect(screen.getAllByText("modality.lockedReason")).toHaveLength(2);
    expect(screen.queryByText("wizard")).not.toBeInTheDocument();
  });

  it("opent wegvervoer gewoon", async () => {
    preferences.default_modality = undefined;
    renderAt("/?choose=1");
    const road = screen.getAllByRole("button").find((tile) => !tile.hasAttribute("disabled"))!;
    await userEvent.click(road);
    await waitFor(() => expect(screen.getByText("wizard")).toBeInTheDocument());
  });

  it("volgt een voorkeur voor een vergrendelde modaliteit niet meer", async () => {
    // The route that skips every tile: a preference set while a modality was
    // open would otherwise keep opening it after the lock went on. Air is the
    // locked case now — it was open for one demonstration in v1.117.0.
    preferences.default_modality = "air";
    renderAt("/");
    await waitFor(() => expect(screen.getAllByRole("button").length).toBeGreaterThan(0));
    expect(screen.queryByText("wizard")).not.toBeInTheDocument();
  });

  it("volgt een voorkeur voor spoorvervoer sinds de vrijgave", async () => {
    preferences.default_modality = "rail";
    renderAt("/");
    await waitFor(() => expect(screen.getByText("wizard")).toBeInTheDocument());
  });

  it("volgt een voorkeur voor wegvervoer wel", async () => {
    preferences.default_modality = "road";
    renderAt("/");
    await waitFor(() => expect(screen.getByText("wizard")).toBeInTheDocument());
  });

  it("volgt een voorkeur voor binnenvaart nu ook", async () => {
    preferences.default_modality = "inland";
    renderAt("/");
    await waitFor(() => expect(screen.getByText("wizard")).toBeInTheDocument());
  });
});

describe("de eigen tegelafbeeldingen", () => {
  it("toont een geüploade afbeelding in beide thema's en de standaard waar er geen is", () => {
    // Custom organisation images remain supported; other modes use vector icons.
    preferences.default_modality = undefined;
    branding.modalities = { road: "/api/branding/modality/road?v=42" };
    renderAt("/?choose=1");
    const images = document.querySelectorAll("img");
    const sources = Array.from(images).map((img) => img.getAttribute("src"));
    expect(sources).toContain("/api/branding/modality/road?v=42");
    expect(sources).not.toContain("/modalities/road-light.webp");
    expect(sources).not.toContain("/modalities/road-dark.webp");
    expect(sources).toHaveLength(1);
    expect(screen.getByRole("button", { name: /modality.rail/ }).querySelector("svg")).not.toBeNull();
    branding.modalities = {};
  });
});
