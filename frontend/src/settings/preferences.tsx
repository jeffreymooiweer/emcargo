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
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import i18n from "i18next";

import { api, PublicSettings, UserPreferences } from "../api/client";
import { documentLanguage } from "../i18n/language";
import { applySystemTheme, applyTheme } from "../theme";

export const LANGUAGE_STORAGE_KEY = "emcargo-lang";

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
  save: (values: UserPreferences) => Promise<UserPreferences>;
  reload: () => Promise<void>;
}

const PreferencesContext = createContext<PreferencesValue>({
  preferences: EMPTY_PREFERENCES,
  publicSettings: null,
  loaded: false,
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

interface ProviderProps {
  children: ReactNode;
}

export function PreferencesProvider({ children }: ProviderProps) {
  const [preferences, setPreferences] = useState<UserPreferences>(EMPTY_PREFERENCES);
  const [publicSettings, setPublicSettings] = useState<PublicSettings | null>(null);
  const [loaded, setLoaded] = useState(false);

  const reload = useCallback(async () => {
    // A failure here must not block the app: someone whose settings cannot be
    // read still has to be able to make a transport document. The defaults and
    // the cached theme carry on.
    const [mine, shared] = await Promise.all([
      api.mySettings().catch(() => null),
      api.publicSettings().catch(() => null),
    ]);
    if (shared) setPublicSettings(shared);
    if (mine) {
      setPreferences(mine);
      applyPreferences(mine);
    }
    setLoaded(true);
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const save = useCallback(
    async (values: UserPreferences) => {
      const saved = await api.saveMySettings(values);
      setPreferences(saved);
      applyPreferences(saved);
      return saved;
    },
    [],
  );

  const value = useMemo(
    () => ({ preferences, publicSettings, loaded, save, reload }),
    [preferences, publicSettings, loaded, save, reload],
  );

  return <PreferencesContext.Provider value={value}>{children}</PreferencesContext.Provider>;
}

export function usePreferences(): PreferencesValue {
  return useContext(PreferencesContext);
}
