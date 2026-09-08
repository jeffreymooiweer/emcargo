/**
 * The user's own settings, loaded once and shared by the whole app.
 *
 * Until v1.45.0 the theme and the language lived in `localStorage` only. That
 * works right up to the moment the same person opens EMCargo on a second
 * device and finds it back in Dutch on a white background — the settings were
 * never theirs, they belonged to one browser.
 *
 * They now live with the account. `localStorage` is kept as a *cache*, not as
 * the truth: the app has to paint something before the first request comes
 * back, and a flash from light to dark on every page load is its own kind of
 * broken. So the cached values are applied immediately, the server's answer
 * arrives a moment later, and it wins.
 *
 * **Except in the open application**, which has no accounts and therefore no
 * server-side settings to win. There the browser *is* the truth: the same
 * preferences, kept in `localStorage` under one key, read on load and written
 * on save, and never sent anywhere except along with the shipment being drawn
 * up. The settings screen says so in as many words, because "stored in your
 * browser" is a promise about where the data is *not* — and a warning that it
 * goes when the browser data goes.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import i18n from "i18next";

import { api, InstallationMode, PublicSettings, UserPreferences } from "../api/client";
import { documentLanguage } from "../i18n/language";
import { applySystemTheme, applyTheme } from "../theme";

export const LANGUAGE_STORAGE_KEY = "emcargo-lang";

/** Where the open application keeps the preferences. One key, one JSON
 *  document, so clearing it is one line and nothing is left half-cleared. */
export const BROWSER_PREFERENCES_KEY = "emcargo-preferences";

export const EMPTY_PREFERENCES: UserPreferences = {
  language: "",
  theme: "dark",
  default_modality: "",
  default_unit: "pcs",
  prefill_documents: true,
  consignor_name: "",
  consignor_address: "",
  consignor_contact: "",
  carrier_name: "",
  loading_point: "",
  emergency_contact: "",
  signature_image: "",
  last_seen_version: "",
};

interface PreferencesValue {
  preferences: UserPreferences;
  publicSettings: PublicSettings | null;
  /** False until the server has answered; the cached values are in use. */
  loaded: boolean;
  /** Which application this is. The chrome reads it to know whether there
   *  is somebody to sign out, a library to link to, release notes to show. */
  mode: InstallationMode;
  save: (values: UserPreferences) => Promise<UserPreferences>;
  reload: () => Promise<void>;
}

const PreferencesContext = createContext<PreferencesValue>({
  preferences: EMPTY_PREFERENCES,
  publicSettings: null,
  loaded: false,
  mode: "organisation",
  save: async (values) => values,
  reload: async () => {},
});

/** Apply what can be seen: the theme and the interface language. */
export function applyPreferences(preferences: UserPreferences) {
  if (preferences.theme === "system") applySystemTheme();
  else applyTheme(preferences.theme);

  if (preferences.language) {
    const language = documentLanguage(preferences.language);
    if (i18n.language !== language) i18n.changeLanguage(language);
    localStorage.setItem(LANGUAGE_STORAGE_KEY, language);
  }
}

/** The open application's preferences, as the browser holds them. Unknown
 *  keys are dropped and missing ones filled in, so a document written by an
 *  older version still reads — the same rule the server applies to its own
 *  JSON column. */
export function readBrowserPreferences(): UserPreferences {
  try {
    const raw = localStorage.getItem(BROWSER_PREFERENCES_KEY);
    if (!raw) return EMPTY_PREFERENCES;
    const stored = JSON.parse(raw) as Partial<UserPreferences>;
    const merged = { ...EMPTY_PREFERENCES };
    for (const key of Object.keys(EMPTY_PREFERENCES) as (keyof UserPreferences)[]) {
      if (key in stored && typeof stored[key] === typeof EMPTY_PREFERENCES[key]) {
        (merged as Record<string, unknown>)[key] = stored[key];
      }
    }
    return merged;
  } catch {
    return EMPTY_PREFERENCES;
  }
}

export function writeBrowserPreferences(values: UserPreferences) {
  try {
    localStorage.setItem(BROWSER_PREFERENCES_KEY, JSON.stringify(values));
  } catch {
    // A full or blocked storage loses the save, not the shipment: the values
    // stay in memory for this visit, which is what the caller keeps anyway.
  }
}

interface ProviderProps {
  children: ReactNode;
  mode?: InstallationMode;
}

export function PreferencesProvider({ children, mode = "organisation" }: ProviderProps) {
  const [preferences, setPreferences] = useState<UserPreferences>(EMPTY_PREFERENCES);
  const [publicSettings, setPublicSettings] = useState<PublicSettings | null>(null);
  const [loaded, setLoaded] = useState(false);
  const open = mode === "open";

  const reload = useCallback(async () => {
    // A failure here must not block the app: someone whose settings cannot be
    // read still has to be able to make a transport document. The defaults and
    // the cached theme carry on.
    const [mine, shared] = await Promise.all([
      open ? Promise.resolve(readBrowserPreferences()) : api.mySettings().catch(() => null),
      api.publicSettings().catch(() => null),
    ]);
    if (shared) setPublicSettings(shared);
    if (mine) {
      setPreferences(mine);
      applyPreferences(mine);
    }
    setLoaded(true);
  }, [open]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const save = useCallback(
    async (values: UserPreferences) => {
      let saved: UserPreferences;
      if (open) {
        writeBrowserPreferences(values);
        saved = values;
      } else {
        saved = await api.saveMySettings(values);
      }
      setPreferences(saved);
      applyPreferences(saved);
      return saved;
    },
    [open],
  );

  const value = useMemo(
    () => ({ preferences, publicSettings, loaded, mode, save, reload }),
    [preferences, publicSettings, loaded, mode, save, reload],
  );

  return <PreferencesContext.Provider value={value}>{children}</PreferencesContext.Provider>;
}

export function usePreferences(): PreferencesValue {
  return useContext(PreferencesContext);
}
