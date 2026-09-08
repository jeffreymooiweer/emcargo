/** Groupage: several consignments on one vehicle, judged as one load.
 *
 *  Every other screen reasons about a consignment, because a consignment is
 *  what somebody fills in. The ADR looks at what is on the vehicle, and three
 *  of its rules cannot be settled per consignment however carefully each one is
 *  completed: the 1.1.3.6 points, the mixed loading of 7.5.2, and the
 *  limited-quantities marking of 3.4.13.
 *
 *  The consignments come in two ways. As the shipment exports the export step
 *  writes (`emcargo.shipment`) — on an installation that keeps nothing,
 *  the file the planner already has is the honest input. And, on an
 *  installation that keeps its shipments, straight from the history: the
 *  kept shipments the viewer may see, picked by reference, with the same
 *  export underneath, so a consignment picked and a consignment uploaded are
 *  the same thing to the check.
 *
 *  On an installation that keeps nothing, nothing here is saved: the trip
 *  lives in this page and in the request, and reloading loses it. On an
 *  installation that keeps its shipments the assessed trip can be kept as
 *  well — named, with what was on the vehicle and the judgement as it was
 *  given — and reopened from the trips page through `?trip=<id>`.
 */
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router";

import { api } from "../api/client";
import type { ShipmentSummary, TripResult } from "../api/client";
import { usePreferences } from "../settings/preferences";
import { useToast } from "../toast/ToastProvider";

type Loaded = {
  name: string;
  entries: Record<string, unknown>[];
  profiles: string[];
  fileName: string;
  /** Set when the consignment came from the history, so it is not added twice. */
  shipmentId?: number;
};

/** The export's own name for the consignment, or the file's, or nothing.
 *
 *  The wizard's field is `reference`; `shipment_reference` is kept for
 *  exports written by hand or by an older reader. Until v1.175.0 only the
 *  latter was read, so every consignment picked from the history was named
 *  after its consignor — three consignments from one shipper looked alike. */
function nameOf(payload: Record<string, any>, fileName: string): string {
  const values = (payload?.consignment ?? {}) as Record<string, string>;
  return (
    values.reference ||
    values.shipment_reference ||
    values.consignor_name ||
    values.consignee_name ||
    fileName.replace(/\.json$/i, "")
  );
}

export default function GroupagePage() {
  const { t, i18n } = useTranslation();
  const toast = useToast();
  const { publicSettings } = usePreferences();
  const historyOn = !!publicSettings?.history_enabled;
  const [loaded, setLoaded] = useState<Loaded[]>([]);
  const [unitMass, setUnitMass] = useState("");
  const [result, setResult] = useState<TripResult | null>(null);
  const [busy, setBusy] = useState(false);
  // The kept trip this page is showing, when it was opened from the trips
  // page; keeping again then brings that row up to date rather than adding.
  const [searchParams] = useSearchParams();
  const reopenId = searchParams.get("trip");
  const [tripId, setTripId] = useState<number | null>(null);
  const [tripName, setTripName] = useState("");
  const [keeping, setKeeping] = useState(false);

  useEffect(() => {
    if (!historyOn || !reopenId) return;
    let cancelled = false;
    api
      .trip(Number(reopenId))
      .then((detail) => {
        if (cancelled) return;
        setLoaded(
          detail.consignments.map((c, index) => ({
            name: c.name,
            entries: c.entries,
            profiles: detail.regulations,
            fileName: c.shipment_id ? `shipment-${c.shipment_id}` : `kept-${index}`,
            shipmentId: c.shipment_id ?? undefined,
          })),
        );
        setUnitMass(detail.unit_max_mass_tonnes === null ? "" : String(detail.unit_max_mass_tonnes));
        setResult(detail.result);
        setTripId(detail.id);
        setTripName(detail.name);
      })
      .catch(() => {
        if (!cancelled) toast.error(t("trips.notFound"));
      });
    return () => {
      cancelled = true;
    };
    // toast and t are stable for the provider's lifetime.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [historyOn, reopenId]);

  // The history's side: the kept shipments the viewer may see, by reference
  // or party. Only ones with dangerous goods are worth a place on the vehicle
  // here — the three rules are all about dangerous goods.
  const [query, setQuery] = useState("");
  const [kept, setKept] = useState<ShipmentSummary[]>([]);
  useEffect(() => {
    if (!historyOn) return;
    const handle = setTimeout(() => {
      api
        .shipments({ q: query, per_page: 50 })
        .then((page) => setKept(page.items))
        .catch(() => setKept([]));
    }, query ? 250 : 0);
    return () => clearTimeout(handle);
  }, [historyOn, query]);

  // A selection made on the shipments page arrives as ids in the address. The
  // authorisation is not carried with them: each one is fetched in the
  // viewer's own name, and a shipment they may not see simply is not there.
  const fromList = searchParams.get("shipments") ?? "";
  const claimed = useRef("");
  useEffect(() => {
    if (!historyOn || !fromList || claimed.current === fromList) return;
    claimed.current = fromList;
    const ids = fromList.split(",").map((one) => Number(one)).filter((one) => one > 0);
    void (async () => {
      let added = 0;
      for (const id of ids) {
        if (await addFromHistory({ id } as ShipmentSummary)) added += 1;
      }
      if (added) toast.success(t("groupage.addedFromList", { count: added }));
    })();
    // addFromHistory reads state through the setter form; the ids decide.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [historyOn, fromList]);

  async function addFromHistory(summary: ShipmentSummary): Promise<boolean> {
    if (loaded.some((c) => c.shipmentId === summary.id)) return false;
    try {
      const detail = await api.shipment(summary.id);
      const payload = detail.export as Record<string, any>;
      const entries = Array.isArray(payload.dangerous_goods) ? payload.dangerous_goods : [];
      const named = summary.reference || detail.reference || `#${summary.id}`;
      if (!entries.length) {
        // Said either way: a consignment left out of the trip because it
        // carries nothing dangerous is a thing the planner has to know.
        toast.error(t("groupage.noDangerousGoods", { file: named }));
        return false;
      }
      setLoaded((current) =>
        current.some((c) => c.shipmentId === summary.id)
          ? current
          : [
              ...current,
              {
                name: nameOf(payload, named),
                entries,
                profiles: Array.isArray(payload.regulations) ? payload.regulations : [],
                fileName: `shipment-${summary.id}`,
                shipmentId: summary.id,
              },
            ],
      );
      setResult(null);
      return true;
    } catch {
      toast.error(t("groupage.unreadable", { file: summary.reference || `#${summary.id}` }));
      return false;
    }
  }

  async function addFiles(files: FileList | null) {
    if (!files?.length) return;
    const added: Loaded[] = [];
    for (const file of Array.from(files)) {
      try {
        const payload = JSON.parse(await file.text());
        // A file that is not a shipment export is refused by name rather than
        // half-read: a trip built from the wrong half of somebody's disk would
        // produce a confident answer about goods that are not on the vehicle.
        if (payload?.format !== "emcargo.shipment") {
          toast.error(t("groupage.notAnExport", { file: file.name }));
          continue;
        }
        const entries = Array.isArray(payload.dangerous_goods) ? payload.dangerous_goods : [];
        if (!entries.length) {
          toast.error(t("groupage.noDangerousGoods", { file: file.name }));
          continue;
        }
        added.push({
          name: nameOf(payload, file.name),
          entries,
          profiles: Array.isArray(payload.regulations) ? payload.regulations : [],
          fileName: file.name,
        });
      } catch {
        toast.error(t("groupage.unreadable", { file: file.name }));
      }
    }
    if (added.length) {
      setLoaded((current) => [...current, ...added]);
      setResult(null);
    }
  }

  function rename(index: number, name: string) {
    setLoaded((current) => current.map((c, i) => (i === index ? { ...c, name } : c)));
    setResult(null);
  }

  function remove(index: number) {
    setLoaded((current) => current.filter((_, i) => i !== index));
    setResult(null);
  }

  const profiles = [...new Set(loaded.flatMap((c) => c.profiles))];

  async function assess() {
    setBusy(true);
    try {
      const mass = unitMass.trim() === "" ? null : Number(unitMass);
      setResult(
        await api.dgTrip({
          consignments: loaded.map((c) => ({ name: c.name, entries: c.entries })),
          profiles,
          language: i18n.language,
          unit_max_mass_tonnes: Number.isFinite(mass as number) ? (mass as number) : null,
        }),
      );
    } catch {
      toast.error(t("groupage.failed"));
    } finally {
      setBusy(false);
    }
  }

  async function keep() {
    setKeeping(true);
    try {
      const mass = unitMass.trim() === "" ? null : Number(unitMass);
      const payload = {
        name: tripName.trim(),
        consignments: loaded.map((c) => ({ name: c.name, entries: c.entries, shipment_id: c.shipmentId ?? null })),
        profiles,
        language: i18n.language,
        unit_max_mass_tonnes: Number.isFinite(mass as number) ? (mass as number) : null,
      };
      const kept = tripId ? await api.updateTrip(tripId, payload) : await api.keepTrip(payload);
      setTripId(kept.id);
      toast.success(t(tripId ? "groupage.updated" : "groupage.kept"));
    } catch {
      toast.error(t("groupage.keepFailed"));
    } finally {
      setKeeping(false);
    }
  }

  const card = "rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900";
  const input =
    "rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-800";

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-4">
      <header>
        <h1 className="text-2xl font-semibold text-slate-900 dark:text-slate-100">
          {t("groupage.title")}
        </h1>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">{t("groupage.intro")}</p>
      </header>

      <section className={card}>
        <label className="text-sm font-medium text-slate-800 dark:text-slate-200">
          {t("groupage.addConsignments")}
        </label>
        <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
          {t("groupage.addHint")}
        </p>
        <input
          type="file"
          accept="application/json,.json"
          multiple
          className="mt-2 block w-full text-sm"
          onChange={(e) => {
            void addFiles(e.target.files);
            e.target.value = "";
          }}
        />
      </section>

      {historyOn && (
        <section className={`${card} space-y-2`}>
          <label className="text-sm font-medium text-slate-800 dark:text-slate-200" htmlFor="groupage-history">
            {t("groupage.fromHistory")}
          </label>
          <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{t("groupage.fromHistoryHint")}</p>
          <input
            id="groupage-history"
            className={`${input} w-full`}
            placeholder={t("groupage.searchHistory")}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          {kept.length === 0 ? (
            <p className="text-xs text-slate-500 dark:text-slate-400">{t("groupage.historyEmpty")}</p>
          ) : (
            <ul className="divide-y divide-slate-100 dark:divide-slate-800" data-testid="groupage-history">
              {kept.map((s) => {
                const added = loaded.some((c) => c.shipmentId === s.id);
                return (
                  <li key={s.id} className="flex items-center gap-3 py-2 text-sm">
                    <span className="min-w-0 flex-1 truncate">
                      <span className="font-medium text-slate-900 dark:text-slate-100">
                        {s.reference || t("history.noReference")}
                      </span>
                      <span className="ml-2 text-slate-500 dark:text-slate-400">
                        {[s.consignor_name, s.consignee_name].filter(Boolean).join(" → ")}
                      </span>
                    </span>
                    {!s.has_dangerous_goods ? (
                      <span className="text-xs text-slate-500 dark:text-slate-400">{t("groupage.noDgShort")}</span>
                    ) : (
                      <button
                        type="button"
                        className="rounded-lg border border-slate-300 px-3 py-1 text-sm disabled:opacity-50 dark:border-slate-600"
                        disabled={added}
                        onClick={() => void addFromHistory(s)}
                      >
                        {added ? t("groupage.alreadyAdded") : t("groupage.addFromHistory")}
                      </button>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      )}

      {loaded.length > 0 && (
        <section className={`${card} space-y-3`}>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
            {t("groupage.onTheVehicle", { count: loaded.length })}
          </h2>
          {loaded.map((c, index) => (
            <div key={`${c.fileName}-${index}`} className="flex items-center gap-2">
              <input
                className={`${input} flex-1`}
                value={c.name}
                aria-label={t("groupage.consignmentName")}
                onChange={(e) => rename(index, e.target.value)}
              />
              <span className="text-xs text-slate-500 dark:text-slate-400">
                {t("groupage.positions", {
                  count: c.entries.reduce(
                    (n, e: any) => n + ((e?.products?.length as number) ?? 0),
                    0,
                  ),
                })}
              </span>
              <button
                type="button"
                className="rounded-lg px-2 py-1 text-sm text-slate-500 hover:text-red-600"
                onClick={() => remove(index)}
              >
                {t("common.remove")}
              </button>
            </div>
          ))}

          <div>
            <label className="text-sm font-medium text-slate-800 dark:text-slate-200">
              {t("groupage.unitMass")}
            </label>
            {/* 3.4.13 turns on the vehicle's permitted maximum mass, which is
                the one thing about the load the application cannot derive.
                Optional, and its absence is reported rather than guessed. */}
            <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
              {t("groupage.unitMassHint")}
            </p>
            <input
              className={`${input} mt-1 w-32`}
              inputMode="decimal"
              value={unitMass}
              onChange={(e) => setUnitMass(e.target.value)}
              placeholder="18"
            />
          </div>

          <button
            type="button"
            disabled={busy || loaded.length < 2}
            className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            onClick={() => void assess()}
          >
            {busy ? t("groupage.assessing") : t("groupage.assess")}
          </button>
          {loaded.length < 2 && (
            <p className="text-xs text-slate-500 dark:text-slate-400">{t("groupage.needTwo")}</p>
          )}
        </section>
      )}

      {result && (
        <section className="space-y-4">
          {result.exemption_lost && (
            <div className="rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-700 dark:bg-amber-900/30 dark:text-amber-100">
              <p className="font-semibold">{t("groupage.exemptionLost")}</p>
              <p className="mt-1">{result.exemption_lost.message}</p>
            </div>
          )}

          <div className={card}>
            <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
              {t("groupage.apartAndTogether")}
            </h2>
            <table className="mt-2 w-full text-sm">
              <tbody>
                {result.consignments.map((c) => (
                  <tr key={c.name} className="border-b border-slate-100 dark:border-slate-800">
                    <td className="py-1 text-slate-800 dark:text-slate-200">{c.name}</td>
                    <td className="py-1 text-right tabular-nums">{c.points ?? "—"}</td>
                    <td className="py-1 pl-3 text-right text-xs text-slate-500 dark:text-slate-400">
                      {c.exempt === true
                        ? t("groupage.exempt")
                        : c.exempt === false
                          ? t("groupage.notExempt")
                          : t("groupage.incomplete")}
                    </td>
                  </tr>
                ))}
                <tr className="font-semibold">
                  <td className="py-1">{t("groupage.together")}</td>
                  <td className="py-1 text-right tabular-nums">
                    {result.adr_points.total_points}
                  </td>
                  <td className="py-1 pl-3 text-right text-xs">
                    {t("groupage.threshold", { value: result.adr_points.threshold })}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          {result.mixed_loading.length > 0 && (
            <div className={card}>
              <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                {t("groupage.mixedLoading")}
              </h2>
              <ul className="mt-2 space-y-2 text-sm">
                {result.mixed_loading.map((w, i) => (
                  <li key={i} className="text-slate-700 dark:text-slate-300">
                    {w.message}
                    {w.products && (
                      <span className="block text-xs text-slate-500 dark:text-slate-400">
                        {w.products}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className={card}>
            <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
              {result.lq_marking.rule}
            </h2>
            <p className="mt-2 text-sm text-slate-700 dark:text-slate-300">
              {result.lq_marking.message}
            </p>
          </div>

          {historyOn ? (
            <div className={`${card} space-y-2`} data-testid="groupage-keep">
              <label className="text-sm font-medium text-slate-800 dark:text-slate-200" htmlFor="groupage-trip-name">
                {t("groupage.tripName")}
              </label>
              <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{t("groupage.keepHint")}</p>
              <div className="flex flex-wrap items-center gap-2">
                <input
                  id="groupage-trip-name"
                  className={`${input} flex-1`}
                  value={tripName}
                  placeholder={t("groupage.tripNamePlaceholder")}
                  onChange={(e) => setTripName(e.target.value)}
                />
                <button
                  type="button"
                  disabled={keeping}
                  className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
                  onClick={() => void keep()}
                >
                  {keeping ? t("groupage.keeping") : tripId ? t("groupage.update") : t("groupage.keep")}
                </button>
                {tripId && (
                  <Link to={`/trips/${tripId}`} className="text-sm text-brand-700 hover:underline dark:text-brand-300">
                    {t("groupage.openKept")}
                  </Link>
                )}
              </div>
            </div>
          ) : (
            <p className="text-xs text-slate-500 dark:text-slate-400">{t("groupage.notStored")}</p>
          )}
        </section>
      )}
    </div>
  );
}
