import { useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { useTranslation } from "react-i18next";
import { useBranding } from "../branding";
import { ModalityIcon } from "../components/WizardShell";
import { ArrowRightIcon, ImportIcon } from "../components/icons";
import { usePreferences } from "../settings/preferences";

export const MODALITIES = ["road", "rail", "sea", "inland", "air", "multimodal"] as const;
export type ModalityKey = (typeof MODALITIES)[number];

/** The modalities a user may actually draw up documents for.
 *
 *  Air is built and reachable and *wrong* in ways that do not announce
 *  themselves, and it carries known gaps listed in `docs/dg-coverage.md`. A
 *  half-right document is worse than no document, because it is signed and
 *  handed over — the consignor has no way to see which half was right.
 *
 *  **Inland waterway was unlocked in v1.63.0.** It went on the lock in v1.60.0
 *  because it answered its separation question with the *road* table and had no
 *  cone data at all. Both are now answered out of the ADN itself: the exemption
 *  from 1.1.3.6.1, the separation in the holds from 7.1.4.3, and the signals the
 *  vessel must show from 7.1.5.0 — each visible in the panel and on the
 *  document.
 *
 *  **Rail was unlocked in v1.122.0**, over the same bar. Its checks are cited
 *  to RID rather than borrowed: the 1.1.3.6 count per wagon or large
 *  container, its own 7.5.2 tables and the 7.5.3 protective distance, CW 28,
 *  the hazard identification number of 5.4.1.1.1 (j) on the CIM, bulk
 *  admission under RID 7.3, and since v1.121.0 the placarding of chapter 5.3
 *  — package wagons for every class, orange plates only via column (20), the
 *  shunting labels of 5.3.4 as the named condition they are. The CIM flow is
 *  verified end to end in the rail archetypes.
 *
 *  This remains a lock and not a hint. It is checked in three places, because
 *  the tile is not the only way in: a bookmark reaches /wizard/sea directly,
 *  and the default-modality preference navigates there without anyone touching
 *  a tile. Guarding only the tiles would guard only the honest route. */
/** **Sea was unlocked in v1.152.0**, over the same bar as rail and inland
 *  waterway. What was missing was never the substance data — the Dangerous
 *  Goods List of Amendment 42-24 has been read since v1.48.0 — but the two
 *  things that turn data into a document somebody can sign:
 *
 *  - **chapter 5.3, added in v1.150.0.** Sea was the last mode carrying goods
 *    without its own placarding, and reusing the road's would have been wrong
 *    five ways over: four sides rather than two, the proper shipping name
 *    marked on the unit, the UN number in the placard rather than on an
 *    orange plate, class 9 placarded as 9 where table A says 9A, and the
 *    marine pollutant mark, which no land regime has.
 *  - **the flow verified end to end**, which is what unlocked rail in
 *    v1.122.0 and what sea did not have. Writing those archetypes found two
 *    things a live test would have found instead: the 24-hour emergency
 *    number of 5.4.1.5.11 was asked of the user and then had nowhere to go on
 *    any sea document, and the IMO form called the container number
 *    `container_identification` while the VGM and the B/L instruction called
 *    it `container_number` — the same number, typed twice, on one
 *    consignment. Both are fixed.
 *
 *  What sea still cannot do is stated rather than hidden: the stowage
 *  category is shown and not enforced (on-deck or under-deck is the carrier's
 *  call), segregation from foodstuffs is raised to verify because the
 *  application cannot see what else is in the container, and nothing about
 *  the ship is claimed at all. That is the same shape of limit inland
 *  waterway was unlocked with, and it is visible on the screen. */
/** Air was unlocked for one demonstration in v1.117.0 and locked again in
 *  v1.118.0, the demonstration over. Nothing about its coverage changed in
 *  between: the IATA quantity tables are still not held, so the Q value
 *  depends on the M a user enters. That is fine to show while someone is
 *  standing next to the screen explaining it, and not fine on a document
 *  someone signs unattended. */
export const AVAILABLE_MODALITIES: readonly ModalityKey[] = ["road", "rail", "sea", "inland"];

export function isModalityKey(value: string | undefined): value is ModalityKey {
  return !!value && (MODALITIES as readonly string[]).includes(value);
}

export function isModalityAvailable(value: string | undefined): value is ModalityKey {
  return isModalityKey(value) && AVAILABLE_MODALITIES.includes(value);
}

export default function ModalitySelectPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const { preferences, publicSettings, loaded } = usePreferences();
  const custom = useBranding().branding.modalities;

  // Someone who only ever ships by road should not tap the same tile every
  // morning. `?choose=1` switches the tiles back on for one visit — without it,
  // "change transport mode" would land here and bounce straight back.
  const skipDefault = params.get("choose") === "1";
  const preferred = preferences.default_modality;
  useEffect(() => {
    if (!loaded || skipDefault) return;
    // A preference set while a modality was open must not keep opening it after
    // it has been locked. The tiles come back instead, with the reason on them.
    if (isModalityAvailable(preferred)) navigate(`/wizard/${preferred}`, { replace: true });
  }, [loaded, skipDefault, preferred, navigate]);

  return (
    <div className="start-workspace page-enter">
      <header className="page-heading">
        <div><p className="eyebrow">{t("nav.new")}</p><h2>{t("modality.title")}</h2>
        <p>{t("modality.intro")}</p></div>
      </header>
      <div className="start-layout">
        <section className="mode-grid" aria-label={t("wizard.mode")}>
          {AVAILABLE_MODALITIES.map((key) => <button key={key} type="button" className={`mode-card mode-card-${key}`} onClick={() => navigate(`/wizard/${key}`)}>
            <span className="mode-card-visual"><img src={custom[key] || `/art/${key}.webp`} alt="" width="768" height="384" decoding="async" />
              <span className="mode-card-rule">{({ road: "ADR", rail: "RID", sea: "IMDG", inland: "ADN" } as Record<string,string>)[key]}</span>
            </span>
            <span className="mode-card-content"><ModalityIcon modality={key} className="mode-card-icon" />
              <span className="mode-copy"><strong>{t(`modality.${key}`)}</strong><span>{t(`modality.${key}Desc`)}</span></span>
              <span className="mode-card-arrow"><ArrowRightIcon className="h-5 w-5" /></span>
            </span>
          </button>)}
        </section>
        <aside className="start-import surface">
          <span className="import-glyph"><ImportIcon className="h-6 w-6" /></span>
          <h3>{t("studio.importTitle")}</h3>
          <p>{t("studio.importHint")}</p>
          <button className="action-primary" onClick={() => navigate(`/wizard/${isModalityAvailable(preferred) ? preferred : "road"}?input=paste`)}>{t("overview.paste")}<ArrowRightIcon className="h-4 w-4" /></button>
          <span className="import-formats">XLSX <span>·</span> CSV <span>·</span> TXT</span>
        </aside>
      </div>
      <div className="start-footnote">
        <p>{t(publicSettings?.history_enabled ? "studio.historyPrivacy" : "dashboard.privacy")}</p>
        <details className="future-modes"><summary>{t("studio.otherModes")}</summary><div>{MODALITIES.filter((key): boolean => !isModalityAvailable(key)).map(key => <div key={key} className="mode-future"><img src={custom[key] || `/art/${key}.webp`} alt="" width="160" height="80" loading="lazy" /><div><strong>{t(`modality.${key}`)}</strong><span>{t("modality.lockedReason")}</span></div></div>)}</div></details>
      </div>
    </div>
  );
}
