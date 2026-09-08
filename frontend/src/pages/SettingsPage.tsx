import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router";
import { useToast } from "../toast/ToastProvider";
import ConfirmDialog from "../toast/ConfirmDialog";
import NumberInput from "../components/NumberInput";
import {
  AssistantStatus,
  InstanceSettings,
  SettingsOptions,
  ThemeChoice,
  UnCardStoreStatus,
  UpdateCapability,
  UpdateStatus,
  User,
  UserPreferences,
  api,
} from "../api/client";
import SignaturePad from "../components/SignaturePad";
import TwoFactorPanel from "../components/TwoFactorPanel";
import { LANGUAGE_NAMES, SUPPORTED_LANGUAGES } from "../i18n/language";
import { useBranding } from "../branding";
import { MODALITIES } from "./ModalitySelectPage";
import { usePreferences } from "../settings/preferences";

const panelClass = "bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800";
const inputClass =
  "w-full border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-950 text-slate-900 dark:text-slate-100 rounded-lg px-3 py-2.5 text-sm min-h-[44px]";
const buttonPrimary =
  "bg-brand-600 text-white px-5 py-2.5 rounded-lg font-medium hover:bg-brand-700 disabled:opacity-50 min-h-[44px] text-sm";
const buttonSecondary =
  "px-4 py-2.5 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-50 min-h-[44px] text-sm inline-flex items-center";

const THEMES: ThemeChoice[] = ["light", "dark", "system"];

/** The settings, grouped the way someone looks for them: how it looks, what a
 *  new shipment starts with, who I am — and, for an administrator, what
 *  applies to the whole installation and the assistant's model. One long
 *  scroll made the personal fields and the instance-wide ones look like one
 *  list, which they are emphatically not. */
const TABS = [
  { key: "appearance", label: "settings.tabAppearance", admin: false },
  { key: "shipment", label: "settings.tabShipment", admin: false },
  { key: "details", label: "settings.tabDetails", admin: false },
  { key: "admin", label: "settings.tabAdmin", admin: true },
  // Maintenance holds the action panels (updating, the UN card set, the
  // assistant's model): things an administrator does now, as opposed to
  // settings an administrator saves. Mixing the two put buttons that act
  // immediately above a save button that does not govern them.
  { key: "maintenance", label: "settings.tabMaintenance", admin: true },
] as const;

type TabKey = (typeof TABS)[number]["key"];

/** The personal tabs share one draft and therefore one save button. */
const PERSONAL_TABS: TabKey[] = ["appearance", "shipment", "details"];

interface Props {
  user: User;
}

export default function SettingsPage({ user }: Props) {
  const { t } = useTranslation();
  const { preferences, save, loaded, mode } = usePreferences();
  // In the open application what is saved here stays in the browser, and
  // the screen has to say so: "stored in your browser" is a promise about
  // where the data is *not*, and a warning that it goes with the browser
  // data. There is also no account to put a second factor on.
  const open = mode === "open";
  const [draft, setDraft] = useState<UserPreferences>(preferences);
  const [options, setOptions] = useState<SettingsOptions | null>(null);
  const [version, setVersion] = useState("");
  const [saving, setSaving] = useState(false);
  const toast = useToast();
  // The open tab lives in the address, so a link can point at one. The
  // two-factor nudge needs that: "set it up now" landing on the theme
  // settings, with the panel it meant three tabs away, is not an answer to
  // the notice the user just clicked.
  const [params, setParams] = useSearchParams();
  const tab_ = (params.get("tab") ?? "appearance") as TabKey;
  const setTab = (key: TabKey) => setParams({ tab: key }, { replace: true });

  useEffect(() => setDraft(preferences), [preferences]);

  useEffect(() => {
    api.health().then((h) => setVersion(h.version)).catch(() => {});
    api.settingsOptions().then(setOptions).catch(() => {});
  }, []);

  const dirty = useMemo(
    () => JSON.stringify(draft) !== JSON.stringify(preferences),
    [draft, preferences],
  );

  const set = <K extends keyof UserPreferences>(key: K, value: UserPreferences[K]) => {
    setDraft((current) => ({ ...current, [key]: value }));
  };

  /** The theme and the language take effect the moment they are picked — they
   *  always did, and having to press Save to see a dark screen would be a step
   *  backwards. Everything else waits for the button. */
  const setAndApply = async (values: Partial<UserPreferences>) => {
    const next = { ...draft, ...values };
    setDraft(next);
    try {
      await save(next);
    } catch (e) {
      toast.error(String(e));
    }
  };

  const submit = async () => {
    setSaving(true);
    try {
      await save(draft);
      toast.success(t("settings.saved"));
    } catch (e) {
      toast.error(String(e));
    } finally {
      setSaving(false);
    }
  };

  const tabs = TABS.filter((tab) => !tab.admin || user.role === "admin");
  const active = tabs.some((tab) => tab.key === tab_) ? tab_ : "appearance";

  return (
    <div className="space-y-6 max-w-2xl pb-4">
      <div>
        <h2 className="text-xl font-semibold text-slate-900 dark:text-slate-100">{t("settings.title")}</h2>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
          {open ? t("settings.introOpen") : t("settings.intro")}
        </p>
      </div>

      {/* On a phone a row of tabs would either wrap or scroll out of sight;
          a dropdown says which group you are in and holds the rest one tap
          away. From the medium breakpoint the tabs themselves fit. */}
      <div className="md:hidden">
        <label htmlFor="settings-tab" className="sr-only">
          {t("settings.tabPick")}
        </label>
        <select
          id="settings-tab"
          className={inputClass}
          value={active}
          onChange={(event) => setTab(event.target.value as TabKey)}
        >
          {tabs.map((tab) => (
            <option key={tab.key} value={tab.key}>
              {t(tab.label as "settings.tabAppearance")}
            </option>
          ))}
        </select>
      </div>

      <div
        role="tablist"
        aria-label={t("settings.title")}
        className="hidden md:flex flex-wrap gap-1 border-b border-slate-200 dark:border-slate-800"
      >
        {tabs.map((tab) => (
          <button
            key={tab.key}
            type="button"
            role="tab"
            aria-selected={active === tab.key}
            onClick={() => setTab(tab.key)}
            className={`-mb-px rounded-t-lg border-b-2 px-4 py-2.5 text-sm font-medium transition ${
              active === tab.key
                ? "border-brand-600 text-brand-700 dark:border-brand-400 dark:text-brand-300"
                : "border-transparent text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200"
            }`}
          >
            {t(tab.label as "settings.tabAppearance")}
          </button>
        ))}
      </div>

      {active === "appearance" && (
      <section className={`${panelClass} p-5 space-y-5`}>
        <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
          {t("settings.appearance")}
        </h3>

        <div>
          <label className="text-sm font-medium text-slate-800 dark:text-slate-200">{t("settings.theme")}</label>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">{t("settings.themeHint")}</p>
          <div className="grid grid-cols-3 gap-2 mt-2">
            {THEMES.map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => void setAndApply({ theme: option })}
                className={`px-3 py-2.5 rounded-lg text-sm min-h-[44px] border ${
                  draft.theme === option
                    ? "border-brand-500 bg-brand-50 text-brand-700 dark:bg-brand-950/50 dark:text-brand-200"
                    : "border-slate-200 dark:border-slate-700"
                }`}
              >
                {t(option === "system" ? "settings.auto" : `theme.${option}`)}
              </button>
            ))}
          </div>
        </div>

        <div>
          <label className="text-sm font-medium text-slate-800 dark:text-slate-200">{t("settings.language")}</label>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">{t("settings.languageHint")}</p>
          <select
            className={`${inputClass} mt-2`}
            value={draft.language || ""}
            onChange={(e) => void setAndApply({ language: e.target.value })}
          >
            {SUPPORTED_LANGUAGES.map((language) => (
              <option key={language} value={language}>
                {LANGUAGE_NAMES[language]}
              </option>
            ))}
          </select>
        </div>

        <p className="text-xs text-slate-500 dark:text-slate-400 border-t border-slate-100 dark:border-slate-800 pt-3">
          {t("settings.autoDetectNote")}
        </p>
      </section>
      )}

      {active === "shipment" && (
      <section className={`${panelClass} p-5 space-y-5`}>
        <div>
          <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
            {t("settings.shipmentDefaults")}
          </h3>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">{t("settings.shipmentDefaultsHint")}</p>
        </div>

        <div>
          <label className="text-sm font-medium text-slate-800 dark:text-slate-200">{t("settings.defaultModality")}</label>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">{t("settings.defaultModalityHint")}</p>
          <select
            className={`${inputClass} mt-2`}
            value={draft.default_modality}
            onChange={(e) => set("default_modality", e.target.value)}
          >
            <option value="">{t("settings.askEveryTime")}</option>
            {(options?.modalities ?? []).map((modality) => (
              <option key={modality} value={modality}>
                {t(`modality.${modality}`)}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="text-sm font-medium text-slate-800 dark:text-slate-200">{t("settings.defaultUnit")}</label>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">{t("settings.defaultUnitHint")}</p>
          <select
            className={`${inputClass} mt-2`}
            value={draft.default_unit}
            onChange={(e) => set("default_unit", e.target.value)}
          >
            {(options?.units ?? []).map((unit) => (
              <option key={unit.code} value={unit.code}>
                {t(`units.name.${unit.code}`, { defaultValue: `${unit.code} (${unit.symbol})` })}
              </option>
            ))}
          </select>
        </div>

        <Toggle
          label={t("settings.prefillDocuments")}
          hint={t("settings.prefillDocumentsHint")}
          checked={draft.prefill_documents}
          onChange={(value) => set("prefill_documents", value)}
        />
      </section>
      )}

      {active === "details" && (
      <section className={`${panelClass} p-5 space-y-4`}>
        <div>
          <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
            {t("settings.myDetails")}
          </h3>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
            {open ? t("settings.myDetailsHintOpen") : t("settings.myDetailsHint")}
          </p>
        </div>

        <Field
          label={t("settings.consignorName")}
          value={draft.consignor_name}
          onChange={(value) => set("consignor_name", value)}
        />
        <div>
          <label className="text-sm font-medium text-slate-800 dark:text-slate-200">
            {t("settings.consignorAddress")}
          </label>
          <textarea
            className={`${inputClass} mt-1 min-h-[80px]`}
            value={draft.consignor_address}
            onChange={(e) => set("consignor_address", e.target.value)}
          />
        </div>
        <Field
          label={t("settings.consignorContact")}
          value={draft.consignor_contact}
          onChange={(value) => set("consignor_contact", value)}
        />
        <Field
          label={t("settings.carrierName")}
          value={draft.carrier_name}
          onChange={(value) => set("carrier_name", value)}
        />
        <Field
          label={t("settings.loadingPoint")}
          value={draft.loading_point}
          onChange={(value) => set("loading_point", value)}
        />
        <Field
          label={t("settings.emergencyContact")}
          hint={t("settings.emergencyContactHint")}
          value={draft.emergency_contact}
          onChange={(value) => set("emergency_contact", value)}
        />
      </section>
      )}

      {active === "details" && (
        <div className="space-y-2">
          <p className="text-xs text-slate-500 dark:text-slate-400">{t("settings.signatureHint")}</p>
          <SignaturePad
            value={draft.signature_image || null}
            onChange={(dataUrl) => set("signature_image", dataUrl ?? "")}
          />
        </div>
      )}

      {/* One draft across the personal tabs, so one save button — switching
          tabs never loses what was typed on another. */}
      {PERSONAL_TABS.includes(active) && (
        <>
          <div className="flex flex-wrap items-center gap-3">
            <button type="button" onClick={submit} disabled={saving || !dirty} className={buttonPrimary}>
              {saving ? t("settings.saving") : t("settings.save")}
            </button>
            {!loaded && <span className="text-sm text-slate-500 dark:text-slate-400">{t("wizard.loading")}</span>}
          </div>
        </>
      )}

      {active === "details" && !open && <TwoFactorPanel />}
      {active === "admin" && user.role === "admin" && <AdminSettings />}
      {active === "maintenance" && user.role === "admin" && (
        <div className="space-y-4">
          <UpdatePanel />
          <UnCardsAdminPanel />
          <AssistantAdmin />
        </div>
      )}

      {version && (
        <p className="text-xs text-slate-500 dark:text-slate-400">
          {t("settings.version")}: {version}
        </p>
      )}
    </div>
  );
}

/**
 * The instance-wide settings, for administrators.
 *
 * Separate from the block above in more than looks: these apply to everyone, and
 * two of them decide whether this installation talks to the internet at all. The
 * server enforces that with `require_admin`; hiding the section here only keeps
 * it out of the way of people who cannot change it anyway.
 */
function AdminSettings() {
  const { t } = useTranslation();
  const toast = useToast();
  const { reload } = usePreferences();
  const [settings, setSettings] = useState<InstanceSettings | null>(null);
  const [draft, setDraft] = useState<InstanceSettings | null>(null);
  const [saving, setSaving] = useState(false);
  const [testTo, setTestTo] = useState("");
  const [testing, setTesting] = useState(false);
  // Switching the history off destroys what it kept. The server refuses
  // while anything is kept; the screen asks first, with the counts, and
  // deletes on confirmation before saving the switch.
  const [discard, setDiscard] = useState<{ shipments: number; trips: number } | null>(null);

  useEffect(() => {
    api
      .instanceSettings()
      .then((values) => {
        setSettings(values);
        setDraft(values);
      })
      .catch((e) => toast.error(String(e)));
    // toast is stable for the provider's lifetime; this effect runs once.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!draft || !settings) return null;

  const dirty = JSON.stringify(draft) !== JSON.stringify(settings);

  const set = <K extends keyof InstanceSettings>(key: K, value: InstanceSettings[K]) => {
    setDraft((current) => (current ? { ...current, [key]: value } : current));
  };

  const runTest = async () => {
    setTesting(true);
    // A test mail takes as long as the SMTP conversation takes — the loading
    // toast holds the user's place until the server has actually answered.
    const pending = toast.loading(t("settings.mailTesting"));
    try {
      const result = await api.sendTestMail(testTo.trim());
      pending.success(t("settings.mailTestSent", { to: result.to }));
    } catch (e) {
      // Whatever the mail server said, said plainly: that sentence is the
      // whole diagnosis for a wrong port, a refused password or a firewall.
      pending.error(String(e));
    } finally {
      setTesting(false);
    }
  };

  const store = async () => {
    const stored = await api.saveInstanceSettings(draft);
    setSettings(stored);
    setDraft(stored);
    toast.success(t("settings.saved"));
    // The menu and the export step read the public settings; a switch
    // saved here must show there without a page reload.
    if (stored.history_enabled !== settings.history_enabled) void reload();
  };

  const submit = async () => {
    setSaving(true);
    try {
      if (settings.history_enabled && !draft.history_enabled) {
        const counts = await api.historyCounts();
        if (counts.shipments || counts.trips) {
          setDiscard(counts);
          return;
        }
      }
      await store();
    } catch (e) {
      toast.error(String(e));
    } finally {
      setSaving(false);
    }
  };

  const discardAndSwitchOff = async () => {
    setDiscard(null);
    setSaving(true);
    try {
      await api.discardHistory();
      await store();
    } catch (e) {
      toast.error(String(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      <p className="text-xs text-slate-500 dark:text-slate-400">{t("settings.adminIntro")}</p>

      <section className={`${panelClass} p-5 space-y-5`}>
        <h4 className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
          {t("settings.adminNewUsers")}
        </h4>

        <div>
          <label className="text-sm font-medium text-slate-800 dark:text-slate-200">
            {t("settings.adminDefaultLanguage")}
          </label>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
            {t("settings.adminDefaultLanguageHint")}
          </p>
          <select
            className={`${inputClass} mt-2`}
            value={draft.default_language}
            onChange={(e) => set("default_language", e.target.value)}
          >
            {SUPPORTED_LANGUAGES.map((language) => (
              <option key={language} value={language}>
                {LANGUAGE_NAMES[language]}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="text-sm font-medium text-slate-800 dark:text-slate-200">
            {t("settings.adminDefaultTheme")}
          </label>
          <select
            className={`${inputClass} mt-2`}
            value={draft.default_theme}
            onChange={(e) => set("default_theme", e.target.value as ThemeChoice)}
          >
            {THEMES.map((option) => (
              <option key={option} value={option}>
                {t(option === "system" ? "settings.auto" : `theme.${option}`)}
              </option>
            ))}
          </select>
        </div>

        <Field
          label={t("settings.organisationName")}
          hint={t("settings.organisationHint")}
          value={draft.organisation_name}
          onChange={(value) => set("organisation_name", value)}
        />
        <div>
          <label className="text-sm font-medium text-slate-800 dark:text-slate-200">
            {t("settings.organisationAddress")}
          </label>
          <textarea
            className={`${inputClass} mt-1 min-h-[80px]`}
            value={draft.organisation_address}
            onChange={(e) => set("organisation_address", e.target.value)}
          />
        </div>
      </section>

      <section className={`${panelClass} p-5 space-y-5`}>
        <div>
          <h4 className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
            {t("settings.adminBranding")}
          </h4>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">{t("settings.adminBrandingHint")}</p>
        </div>
        <Field
          label={t("settings.brandName")}
          hint={t("settings.brandNameHint")}
          value={draft.brand_name ?? ""}
          onChange={(value) => set("brand_name", value)}
        />
        <BrandingPictures />
      </section>

      <section className={`${panelClass} p-5 space-y-5`}>
        <div>
          <h4 className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
            {t("settings.adminNetwork")}
          </h4>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">{t("settings.adminNetworkHint")}</p>
        </div>

        <Toggle
          label={t("settings.addressLookup")}
          hint={t("settings.addressLookupHint")}
          checked={draft.address_lookup_enabled}
          onChange={(value) => set("address_lookup_enabled", value)}
        />
        {draft.address_lookup_enabled && (
          <>
            <Field
              label={t("settings.addressApiUrl")}
              hint={t("settings.addressApiUrlHint")}
              value={draft.address_api_url}
              onChange={(value) => set("address_api_url", value)}
            />
            <div>
              <label className="text-sm font-medium text-slate-800 dark:text-slate-200">
                {t("settings.addressTimeout")}
              </label>
              <NumberInput
                min={1}
                max={60}
                step={0.5}
                className={`${inputClass} mt-1`}
                value={draft.address_timeout_seconds}
                onChange={(e) => set("address_timeout_seconds", Number(e.target.value))}
              />
            </div>
          </>
        )}

        <Toggle
          label={t("settings.catalogAutoSync")}
          hint={t("settings.catalogAutoSyncHint")}
          checked={draft.catalog_auto_sync}
          onChange={(value) => set("catalog_auto_sync", value)}
        />

        <Toggle
          label={t("settings.updateCheck")}
          hint={t("settings.updateCheckHint")}
          checked={draft.update_check_enabled}
          onChange={(value) => set("update_check_enabled", value)}
        />
      </section>

      <section className={`${panelClass} p-5 space-y-5`}>
        <h4 className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
          {t("settings.adminFeatures")}
        </h4>

        <Toggle
          label={t("settings.unCardsEnabled")}
          hint={t("settings.unCardsEnabledHint")}
          checked={draft.un_cards_enabled}
          onChange={(value) => set("un_cards_enabled", value)}
        />

        <Toggle
          label={t("settings.historyEnabled")}
          hint={t("settings.historyEnabledHint")}
          checked={draft.history_enabled}
          onChange={(value) => set("history_enabled", value)}
        />
        <ConfirmDialog
          open={discard !== null}
          title={t("settings.historyDiscardTitle")}
          body={t("settings.historyDiscardBody", {
            shipments: discard?.shipments ?? 0,
            trips: discard?.trips ?? 0,
          })}
          confirmLabel={t("settings.historyDiscardConfirm")}
          onConfirm={() => void discardAndSwitchOff()}
          onCancel={() => setDiscard(null)}
        />

        <div>
          <label className="text-sm font-medium text-slate-800 dark:text-slate-200">
            {t("settings.sessionTimeout")}
          </label>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">{t("settings.sessionTimeoutHint")}</p>
          <NumberInput
            min={15}
            max={10080}
            step={15}
            className={`${inputClass} mt-1`}
            value={draft.session_timeout_minutes}
            onChange={(e) => set("session_timeout_minutes", Number(e.target.value))}
          />
        </div>

        <div>
          <label className="text-sm font-medium text-slate-800 dark:text-slate-200">
            {t("settings.auditRetention")}
          </label>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">{t("settings.auditRetentionHint")}</p>
          <NumberInput
            min={1}
            max={3650}
            step={1}
            className={`${inputClass} mt-1`}
            value={draft.audit_retention_days}
            onChange={(e) => set("audit_retention_days", Number(e.target.value))}
          />
        </div>
      </section>

      <section className={`${panelClass} p-5 space-y-5`}>
        <div>
          <h4 className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
            {t("settings.mailTitle")}
          </h4>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">{t("settings.mailHint")}</p>
        </div>

        <div>
          <label className="text-sm font-medium text-slate-800 dark:text-slate-200">
            {t("settings.twoFactorPolicy")}
          </label>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
            {t("settings.twoFactorPolicyHint")}
          </p>
          <select
            className={`${inputClass} mt-2`}
            value={draft.two_factor_policy}
            onChange={(e) =>
              set("two_factor_policy", e.target.value as InstanceSettings["two_factor_policy"])
            }
          >
            <option value="off">{t("settings.twoFactorOff")}</option>
            <option value="admins">{t("settings.twoFactorAdmins")}</option>
            <option value="everyone">{t("settings.twoFactorEveryone")}</option>
          </select>
        </div>

        <Field
          label={t("settings.publicUrl")}
          hint={t("settings.publicUrlHint")}
          value={draft.public_url}
          onChange={(value) => set("public_url", value)}
        />

        <Toggle
          label={t("settings.cardLinks")}
          hint={t("settings.cardLinksHint")}
          checked={draft.card_links_enabled}
          onChange={(value) => set("card_links_enabled", value)}
        />

        {/* A code printed without an address leads nowhere, and the driver
            holding the paper three days later cannot tell that from a code
            that simply failed to scan. */}
        {draft.card_links_enabled && !draft.public_url.trim() && (
          <p className="rounded-lg bg-amber-50 p-3 text-xs text-amber-800 dark:bg-amber-900/30 dark:text-amber-200">
            {t("settings.cardLinksNeedsUrl")}
          </p>
        )}

        <Toggle
          label={t("settings.mailEnabled")}
          hint={t("settings.mailEnabledHint")}
          checked={draft.mail_enabled}
          onChange={(value) => set("mail_enabled", value)}
        />

        {draft.mail_enabled && (
          <>
            <div className="grid gap-4 md:grid-cols-2">
              <Field
                label={t("settings.mailHost")}
                hint={t("settings.mailHostHint")}
                value={draft.mail_host}
                onChange={(value) => set("mail_host", value)}
              />
              <div>
                <label className="text-sm font-medium text-slate-800 dark:text-slate-200">
                  {t("settings.mailPort")}
                </label>
                <NumberInput
                  min={1}
                  max={65535}
                  className={`${inputClass} mt-1`}
                  value={draft.mail_port}
                  onChange={(e) => set("mail_port", Number(e.target.value))}
                />
              </div>
              <div>
                <label className="text-sm font-medium text-slate-800 dark:text-slate-200">
                  {t("settings.mailSecurity")}
                </label>
                <select
                  className={`${inputClass} mt-1`}
                  value={draft.mail_security}
                  onChange={(e) =>
                    set("mail_security", e.target.value as InstanceSettings["mail_security"])
                  }
                >
                  <option value="starttls">{t("settings.mailSecurityStarttls")}</option>
                  <option value="ssl">{t("settings.mailSecuritySsl")}</option>
                  <option value="none">{t("settings.mailSecurityNone")}</option>
                </select>
              </div>
              <Field
                label={t("settings.mailUsername")}
                hint={t("settings.mailUsernameHint")}
                value={draft.mail_username}
                onChange={(value) => set("mail_username", value)}
              />
              <div>
                <label className="text-sm font-medium text-slate-800 dark:text-slate-200">
                  {t("settings.mailPassword")}
                </label>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                  {settings.mail_password_set ? t("settings.mailPasswordStored") : t("settings.mailPasswordHint")}
                </p>
                <input
                  type="password"
                  autoComplete="new-password"
                  className={`${inputClass} mt-1`}
                  value={draft.mail_password}
                  onChange={(e) => set("mail_password", e.target.value)}
                />
              </div>
              <Field
                label={t("settings.mailFrom")}
                hint={t("settings.mailFromHint")}
                value={draft.mail_from}
                onChange={(value) => set("mail_from", value)}
              />
              <Field
                label={t("settings.mailFromName")}
                value={draft.mail_from_name}
                onChange={(value) => set("mail_from_name", value)}
              />
            </div>

            <div className="border-t border-slate-100 dark:border-slate-800 pt-4 space-y-2">
              <label className="text-sm font-medium text-slate-800 dark:text-slate-200">
                {t("settings.mailTest")}
              </label>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                {dirty ? t("settings.mailTestSaveFirst") : t("settings.mailTestHint")}
              </p>
              <div className="flex flex-wrap items-center gap-2">
                <input
                  type="email"
                  className={`${inputClass} max-w-xs`}
                  placeholder={t("settings.mailTestPlaceholder")}
                  value={testTo}
                  onChange={(e) => setTestTo(e.target.value)}
                />
                <button
                  type="button"
                  className={buttonSecondary}
                  disabled={testing || dirty}
                  onClick={runTest}
                >
                  {testing ? t("settings.mailTesting") : t("settings.mailTestSend")}
                </button>
              </div>
            </div>
          </>
        )}
      </section>

      <div className="flex flex-wrap items-center gap-3">
        <button type="button" onClick={submit} disabled={saving || !dirty} className={buttonPrimary}>
          {saving ? t("settings.saving") : t("settings.saveAdmin")}
        </button>
      </div>
    </div>
  );
}

function Field({
  label,
  hint,
  value,
  onChange,
}: {
  label: string;
  hint?: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div>
      <label className="text-sm font-medium text-slate-800 dark:text-slate-200">{label}</label>
      {hint && <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">{hint}</p>}
      <input className={`${inputClass} mt-1`} value={value} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}

function Toggle({
  label,
  hint,
  checked,
  onChange,
}: {
  label: string;
  hint?: string;
  checked: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <label className="flex items-start gap-3 cursor-pointer">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-1 h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
      />
      <span className="min-w-0">
        <span className="block text-sm font-medium text-slate-800 dark:text-slate-200">{label}</span>
        {hint && <span className="block text-xs text-slate-500 dark:text-slate-400 mt-0.5">{hint}</span>}
      </span>
    </label>
  );
}

/**
 * The local AI model: an opt-in download, never part of the image.
 *
 * The assistant always works — without a model it runs its deterministic
 * chain. What this block installs is flexibility only: a small local model
 * that reads free text. The download is the assistant's single external
 * fetch, verified against the SHA-256 pinned in the repository, into
 * /data/assistant; while the sources are unpinned the button stays off.
 */
function AssistantAdmin() {
  const { t } = useTranslation();
  const toast = useToast();
  const [status, setStatus] = useState<AssistantStatus | null>(null);

  const refresh = () =>
    api.assistantStatus().then(setStatus).catch((e) => toast.error(String(e)));

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (status?.download.state !== "downloading") return;
    const timer = window.setInterval(() => void refresh(), 3000);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status?.download.state]);

  if (!status) return null;

  const act = async (action: "download" | "remove") => {
    try {
      await api.assistantModel(action);
      await refresh();
    } catch (e) {
      toast.error(String(e));
    }
  };

  return (
    <section className={`${panelClass} p-5 space-y-4`}>
      <h4 className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
        {t("settings.assistantTitle")}
      </h4>
      <p className="text-sm text-slate-600 dark:text-slate-400">{t("settings.assistantIntro")}</p>
      <ul className="space-y-1 text-sm text-slate-700 dark:text-slate-300">
        <li>
          {t("settings.assistantMode")}:{" "}
          <span className="font-medium">
            {status.mode === "model" ? status.model : t("settings.assistantDeterministic")}
          </span>
        </li>
        {status.download.state === "downloading" && (
          <li className="text-amber-700 dark:text-amber-300">
            {t("settings.assistantDownloading")} ({status.download.detail})
          </li>
        )}
        {status.download.state === "error" && (
          <li className="text-red-600 dark:text-red-400">{status.download.detail}</li>
        )}
      </ul>
      <div className="flex flex-wrap gap-2">
        {!status.installed && (
          <button
            type="button"
            disabled={!status.installable || status.download.state === "downloading"}
            onClick={() => void act("download")}
            className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
          >
            {t("settings.assistantInstall")}
          </button>
        )}
        {status.installed && (
          <button
            type="button"
            onClick={() => void act("remove")}
            className="rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            {t("settings.assistantRemove")}
          </button>
        )}
      </div>
      {!status.installable && !status.installed && (
        <p className="text-xs text-slate-500 dark:text-slate-400">{t("settings.assistantUnpinned")}</p>
      )}
      {!status.installed && (
        <p className="text-xs text-slate-500 dark:text-slate-400">{t("settings.assistantFootprint")}</p>
      )}
    </section>
  );
}

/** The UN card store: what is installed, and the two ways to fill it.
 *
 *  The cards left the Docker image in v1.129.0 — thousands of generated PDFs
 *  live in a GitHub Release instead, and this panel is where an administrator
 *  pulls them in. Checking the remote feed happens only on the button, never
 *  on page load: an admin opening settings is not consent for an outbound
 *  request. The upload path exists for installations that cannot reach
 *  GitHub; both run the same server-side verification.
 */
function UnCardsAdminPanel() {
  const { t } = useTranslation();
  const toast = useToast();
  const [status, setStatus] = useState<UnCardStoreStatus | null>(null);
  const [busy, setBusy] = useState<"" | "check" | "download" | "import" | "remove">("");

  const refresh = (remote = false) =>
    api
      .unCardStoreStatus(remote)
      .then(setStatus)
      .catch((e) => toast.error(String(e)));

  useEffect(() => {
    void refresh(false);
  }, []);

  const run = async (
    kind: "check" | "download" | "import" | "remove",
    action: () => Promise<unknown>,
    done: string,
  ) => {
    setBusy(kind);
    try {
      await action();
      if (done) toast.success(done);
    } catch (e) {
      toast.error(String(e));
    } finally {
      setBusy("");
    }
  };

  const local = status?.local;
  const remote = status?.remote;
  const sizeMb = local?.total_size ? (local.total_size / 1e6).toFixed(0) : null;

  return (
    <section className={`${panelClass} p-5 space-y-4`}>
      <div>
        <h4 className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
          {t("settings.unCardsStoreTitle")}
        </h4>
        <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{t("settings.unCardsStoreIntro")}</p>
      </div>

      {local && !local.installed && (
        <p className="text-sm text-slate-700 dark:text-slate-300">{t("settings.unCardsNone")}</p>
      )}
      {local && local.installed && (
        <div className="space-y-1 text-sm text-slate-700 dark:text-slate-300">
          <p>
            {t("settings.unCardsInstalled", {
              count: local.total_cards ?? 0,
              generated: local.generated_at ?? "?",
            })}
            {sizeMb ? ` (${sizeMb} MB)` : ""}
          </p>
          {local.imported_at && (
            <p className="text-xs text-slate-500 dark:text-slate-400">
              {t("settings.unCardsImportedAt", { date: local.imported_at })} · {local.location}
            </p>
          )}
          <p className="text-xs text-slate-500 dark:text-slate-400">
            {Object.entries(local.counts ?? {})
              .map(([modality, count]) => `${modality}: ${count} (${local.editions?.[modality] ?? "?"})`)
              .join(" · ")}
          </p>
        </div>
      )}

      {remote && (
        <p className="text-sm text-slate-700 dark:text-slate-300">
          {remote.reachable === false
            ? t("settings.unCardsRemoteUnreachable")
            : !remote.available
              ? t("settings.unCardsNoRelease")
              : remote.update_available
                ? t("settings.unCardsUpdateAvailable", { tag: remote.tag ?? "" })
                : t("settings.unCardsUpToDate", { tag: remote.tag ?? "" })}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          className={buttonSecondary}
          disabled={busy !== ""}
          onClick={() => run("check", () => refresh(true), "")}
        >
          {busy === "check" ? t("settings.unCardsChecking") : t("settings.unCardsCheck")}
        </button>
        <button
          type="button"
          className={buttonPrimary}
          disabled={busy !== ""}
          onClick={() =>
            run(
              "download",
              async () => {
                await api.unCardStoreDownloadLatest();
                await refresh(false);
              },
              t("settings.unCardsImportDone"),
            )
          }
        >
          {busy === "download" ? t("settings.unCardsDownloading") : t("settings.unCardsDownload")}
        </button>
        <label className={`${buttonSecondary} cursor-pointer`}>
          {busy === "import" ? t("settings.unCardsImporting") : t("settings.unCardsImportZip")}
          <input
            type="file"
            accept=".zip"
            className="hidden"
            disabled={busy !== ""}
            onChange={(e) => {
              const file = e.target.files?.[0];
              e.target.value = "";
              if (!file) return;
              void run(
                "import",
                async () => {
                  await api.unCardStoreImport(file);
                  await refresh(false);
                },
                t("settings.unCardsImportDone"),
              );
            }}
          />
        </label>
        {local?.installed && (
          <button
            type="button"
            className={buttonSecondary}
            disabled={busy !== ""}
            onClick={() => {
              // Deferred removal with undo: the panel flips to "not installed"
              // now; the store is only cleared when the window closes. Undo
              // restores the view — nothing was removed yet.
              const before = status;
              setStatus((current) =>
                current ? { ...current, local: { ...current.local, installed: false } } : current);
              toast.undoable(t("toast.removedUnCards"), {
                execute: () => {
                  api.unCardStoreRemove().then(() => refresh(false)).catch((e) => {
                    toast.error(String(e));
                    void refresh(false);
                  });
                },
                restore: () => setStatus(before),
              });
            }}
          >
            {t("settings.unCardsRemove")}
          </button>
        )}
      </div>

    </section>
  );
}

/** The Updating section: check on click, and — where the operator mounted
 *  the Docker socket and set the switch — update and restart from here.
 *  Without that capability the panel explains the manual route and how to
 *  enable the in-app one, including what handing over the socket means. */
function UpdatePanel() {
  const { t } = useTranslation();
  const toast = useToast();
  const [capability, setCapability] = useState<UpdateCapability | null>(null);
  const [status, setStatus] = useState<UpdateStatus | null>(null);
  const [checking, setChecking] = useState(false);
  const [applying, setApplying] = useState(false);
  const [confirmApply, setConfirmApply] = useState(false);

  useEffect(() => {
    api.updateCapability().then(setCapability).catch(() => setCapability(null));
    // How the previous in-app update went, surviving its own restart.
    api
      .updateState()
      .then((answer) => {
        if (answer.state?.phase === "done") {
          toast.success(t("settings.updateDone", { version: answer.current }));
        } else if (answer.state?.phase === "failed") {
          toast.error(t("settings.updateFailed", { error: answer.state.error ?? "" }));
        }
      })
      .catch(() => undefined);
    // Runs once: t or toast retriggering it would repeat the outcome toast.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const checkNow = async () => {
    setChecking(true);
    try {
      setStatus(await api.updateCheckNow());
    } catch (e) {
      toast.error(String(e));
    } finally {
      setChecking(false);
    }
  };

  const apply = async () => {
    if (!status?.latest) return;
    setApplying(true);
    // One loading toast follows the whole update: pulling, restarting, and —
    // on success — the page reloads into the new version underneath it.
    const pending = toast.loading(t("settings.updatePhasePulling"));
    try {
      await api.updateApply();
    } catch (e) {
      pending.error(String(e));
      setApplying(false);
      return;
    }
    // Follow the state until the restart cuts the connection, then wait for
    // the new instance and reload into it.
    const started = Date.now();
    const poll = async () => {
      try {
        const answer = await api.updateState();
        if (answer.state?.phase === "failed") {
          pending.error(t("settings.updateFailed", { error: answer.state.error ?? "" }));
          setApplying(false);
          return;
        }
        if (answer.current !== status.current || answer.state?.phase === "done") {
          window.location.reload();
          return;
        }
        pending.progress(
          answer.state?.phase === "handed_over" || answer.state?.phase === "stopping"
            ? t("settings.updatePhaseRestarting")
            : t("settings.updatePhasePulling"),
        );
      } catch {
        // The application is restarting; keep knocking until it answers.
        pending.progress(t("settings.updatePhaseRestarting"));
      }
      if (Date.now() - started < 10 * 60 * 1000) {
        window.setTimeout(poll, 2500);
      } else {
        pending.error(t("settings.updateTimeout"));
        setApplying(false);
      }
    };
    window.setTimeout(poll, 2500);
  };

  const canApply = capability?.available === true;
  const updateAvailable = status?.update_available === true;

  return (
    <section className={`${panelClass} p-5 space-y-3`}>
      <h4 className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
        {t("settings.adminUpdates")}
      </h4>

      <div className="flex flex-wrap items-center gap-3">
        <button type="button" className={buttonSecondary} onClick={checkNow} disabled={checking || applying}>
          {checking ? t("settings.updateChecking") : t("settings.updateCheckNow")}
        </button>
        {status && status.enabled && status.reachable === false && (
          <span className="text-sm text-amber-700 dark:text-amber-300">{t("settings.updateUnreachable")}</span>
        )}
        {status && status.reachable && !updateAvailable && (
          <span className="text-sm text-emerald-700 dark:text-emerald-400">
            {t("settings.updateUpToDate", { version: status.current })}
          </span>
        )}
        {status && updateAvailable && (
          <span className="text-sm text-slate-700 dark:text-slate-200">
            {t("settings.updateFound", { current: status.current, latest: status.latest })}
          </span>
        )}
      </div>

      {updateAvailable && canApply && (
        <div className="space-y-2">
          <button
            type="button"
            className={buttonPrimary}
            onClick={() => setConfirmApply(true)}
            disabled={applying}
          >
            {applying
              ? t("settings.updateApplying")
              : t("settings.updateApplyNow", { version: status?.latest })}
          </button>
          <p className="text-xs text-slate-500 dark:text-slate-400">{t("settings.updateApplyHint")}</p>
        </div>
      )}
      {/* Updating restarts the application for everyone using it — that asks
          for a deliberate step before, not an undo window after. */}
      <ConfirmDialog
        open={confirmApply}
        title={t("settings.adminUpdates")}
        body={t("settings.updateApplyConfirm", { version: status?.latest ?? "" })}
        confirmLabel={t("settings.updateApplyNow", { version: status?.latest ?? "" })}
        onConfirm={() => {
          setConfirmApply(false);
          void apply();
        }}
        onCancel={() => setConfirmApply(false)}
      />

      {/* The operator did their part (switch on, socket mounted) and the
          capability is still off: say why, right here — this state used to
          be silent and looked like the feature simply not existing. */}
      {capability && capability.apply_enabled && capability.socket && !capability.available && (
        <p className="text-sm text-amber-700 dark:text-amber-300">
          {capability.reason === "socket_permission"
            ? t("settings.updateReasonPermission")
            : capability.reason === "container_not_found"
              ? t("settings.updateReasonContainerNotFound")
              : capability.reason === "foreign_image"
                ? t("settings.updateReasonForeignImage")
                : t("settings.updateReasonSocketUnusable")}
        </p>
      )}

      {!canApply && capability?.install_method === "native" && (
        <div className="space-y-2">
          <p className="text-sm text-slate-700 dark:text-slate-300">{t("settings.updateNative")}</p>
          <pre className="overflow-x-auto rounded-lg bg-slate-100 px-3 py-2 text-xs text-slate-800 dark:bg-slate-800 dark:text-slate-200">
            sudo /opt/emcargo/current/deploy/native/update.sh
          </pre>
        </div>
      )}
      {!canApply && capability?.install_method === "kubernetes" && (
        <div className="space-y-2">
          <p className="text-sm text-slate-700 dark:text-slate-300">{t("settings.updateKubernetes")}</p>
          <pre className="overflow-x-auto rounded-lg bg-slate-100 px-3 py-2 text-xs text-slate-800 dark:bg-slate-800 dark:text-slate-200">
            kubectl -n emcargo set image deployment/emcargo emcargo=ghcr.io/jeffreymooiweer/emcargo:{status?.latest ?? "<version>"}
          </pre>
        </div>
      )}
      {!canApply && (capability?.install_method ?? "docker") === "docker" && (
        <div className="space-y-3">
          <p className="text-sm text-slate-700 dark:text-slate-300">{t("settings.updateExplain")}</p>
          <pre className="overflow-x-auto rounded-lg bg-slate-100 px-3 py-2 text-xs text-slate-800 dark:bg-slate-800 dark:text-slate-200">
            docker compose pull && docker compose up -d
          </pre>
          <details className="text-sm text-slate-700 dark:text-slate-300">
            <summary className="cursor-pointer font-medium">{t("settings.updateEnableApply")}</summary>
            <div className="mt-2 space-y-2">
              <p>{t("settings.updateAuto")}</p>
              <p>{t("settings.updateEnableApplyHow")}</p>
              <pre className="overflow-x-auto rounded-lg bg-slate-100 px-3 py-2 text-xs text-slate-800 dark:bg-slate-800 dark:text-slate-200">
{`environment:
  - UPDATE_APPLY_ENABLED=true
volumes:
  - /var/run/docker.sock:/var/run/docker.sock`}
              </pre>
              <p className="text-amber-700 dark:text-amber-300">{t("settings.updateSocketWarning")}</p>
              {capability && capability.apply_enabled && capability.reason === "no_socket" && (
                <p>{t("settings.updateReasonNoSocket")}</p>
              )}
              {capability && !capability.apply_enabled && capability.socket && (
                <p>{t("settings.updateReasonSwitchOff")}</p>
              )}
            </div>
          </details>
        </div>
      )}

    </section>
  );
}

/**
 * The logo and the six tile pictures.
 *
 * These act the moment a file is chosen, unlike the name above them, which
 * waits for the save button: a picture is a file on the server, not a value
 * in a form, and "choose a file, then also press save" is the step everyone
 * forgets. The hint says so. The server decides what a file is from its
 * bytes and refuses anything that is not a PNG, JPEG or WebP; the message it
 * answers with is shown as it comes.
 */
function BrandingPictures() {
  const { t } = useTranslation();
  const toast = useToast();
  const { branding, refresh } = useBranding();
  const [busy, setBusy] = useState<string | null>(null);

  const act = async (key: string, work: () => Promise<unknown>, done: string) => {
    setBusy(key);
    try {
      await work();
      await refresh();
      toast.success(t(done));
    } catch (e) {
      toast.error(String(e));
    } finally {
      setBusy(null);
    }
  };

  const pick = (key: string, upload: (file: File) => Promise<unknown>) => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "image/png,image/jpeg,image/webp";
    input.onchange = () => {
      const file = input.files?.[0];
      if (file) void act(key, () => upload(file), "settings.brandUploaded");
    };
    input.click();
  };

  const slot = (key: string, label: string, current: string | null,
                upload: (file: File) => Promise<unknown>, remove: () => Promise<unknown>,
                fallback: string, fallbackClass = "") => (
    <div key={key} className="flex items-center gap-3 rounded-xl border border-slate-200 dark:border-slate-800 p-3">
      <img
        src={current ?? fallback}
        alt=""
        aria-hidden="true"
        className={`h-12 w-20 shrink-0 rounded-lg object-contain bg-slate-50 dark:bg-slate-950 ${current ? "" : fallbackClass}`}
      />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">{label}</p>
        <p className="text-xs text-slate-500 dark:text-slate-400">
          {current ? t("settings.brandCustom") : t("settings.brandDefault")}
        </p>
      </div>
      <div className="flex shrink-0 flex-wrap gap-2">
        <button
          type="button"
          className={buttonSecondary}
          disabled={busy !== null}
          onClick={() => pick(key, upload)}
        >
          {current ? t("settings.brandReplace") : t("settings.brandUpload")}
        </button>
        {current && (
          <button
            type="button"
            className={buttonSecondary}
            disabled={busy !== null}
            onClick={() => void act(key, remove, "settings.brandRemoved")}
          >
            {t("settings.brandRemove")}
          </button>
        )}
      </div>
    </div>
  );

  return (
    <div className="space-y-4">
      <div>
        <label className="text-sm font-medium text-slate-800 dark:text-slate-200">{t("settings.brandLogo")}</label>
        <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5 mb-2">{t("settings.brandLogoHint")}</p>
        {slot("logo", t("settings.brandLogo"), branding.logo, api.uploadBrandLogo, api.removeBrandLogo,
              "/shipping.png", "dark:brightness-0 dark:invert")}
      </div>
      <div>
        <label className="text-sm font-medium text-slate-800 dark:text-slate-200">{t("settings.brandModalities")}</label>
        <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5 mb-2">{t("settings.brandModalitiesHint")}</p>
        <div className="grid gap-2 md:grid-cols-2">
          {MODALITIES.map((key) =>
            slot(key, t(`modality.${key}`), branding.modalities[key] ?? null,
                 (file) => api.uploadBrandModality(key, file), () => api.removeBrandModality(key),
                 `/modalities/${key}-light.webp`),
          )}
        </div>
      </div>
    </div>
  );
}
