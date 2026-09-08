/**
 * What the installation calls itself and looks like.
 *
 * An organisation that hosts EMCargo for its own people would rather see
 * its own name on the door and its own pictures on the tiles. The server
 * answers `/api/branding` without a sign-in — the sign-in page is the door,
 * and a door has its sign on the outside — so this provider sits above the
 * user gate in `App` and both halves of the app read the same answer.
 *
 * Three consumers, each drawing the default when there is nothing custom:
 * the header and the sign-in page (name and logo), the modality tiles (one
 * picture per mode), and the browser tab, which this provider sets itself
 * because nothing else owns `document.title`.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { api, Branding } from "./api/client";

export const DEFAULT_BRANDING: Branding = { name: "", logo: null, modalities: {} };

/** The name the tab and the header fall back to. Not translated: it is the
 *  product's name, and the same in every language. */
export const PRODUCT_NAME = "EMCargo";

interface BrandingValue {
  branding: Branding;
  /** After an administrator uploads or removes a picture, so the header and
   *  the tiles follow without a reload. */
  refresh: () => Promise<void>;
}

export const BrandingContext = createContext<BrandingValue>({
  branding: DEFAULT_BRANDING,
  refresh: async () => {},
});

export function BrandingProvider({ children }: { children: ReactNode }) {
  const [branding, setBranding] = useState<Branding>(DEFAULT_BRANDING);

  const refresh = useCallback(async () => {
    // A failed request must not block the app: a sign-in page with the
    // default logo is a sign-in page, and the wizard does not need a logo.
    const answer = await api.branding().catch(() => null);
    if (answer) setBranding(answer);
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    document.title = branding.name || PRODUCT_NAME;
  }, [branding.name]);

  const value = useMemo(() => ({ branding, refresh }), [branding, refresh]);
  return <BrandingContext.Provider value={value}>{children}</BrandingContext.Provider>;
}

export function useBranding(): BrandingValue {
  return useContext(BrandingContext);
}
