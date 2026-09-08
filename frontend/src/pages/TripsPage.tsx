/**
 * The groupage trips this installation kept.
 *
 * Exists only where the history is switched on — the same promise, the same
 * page shape, as the shipments. A list with a search and a date range, and
 * a record with the judgement as it was given: what each consignment said
 * alone, what they said together, the mixed-loading and limited-quantities
 * findings, and the editions all of it was computed against. From the
 * record the trip reopens on the groupage page, or is removed.
 */
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams } from "react-router";

import { api, Department, TripDetail, TripSummary, User } from "../api/client";
import { usePreferences } from "../settings/preferences";
import ConfirmDialog from "../toast/ConfirmDialog";
import { useToast } from "../toast/ToastProvider";
import { localDateFilters } from "../utils/dateRanges";

const panelClass = "bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800";
const inputClass =
  "w-full border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-950 text-slate-900 dark:text-slate-100 rounded-lg px-3 py-2.5 text-sm min-h-[44px]";
const buttonPrimary =
  "bg-brand-600 text-white px-4 py-2.5 rounded-lg font-medium hover:bg-brand-700 disabled:opacity-50 min-h-[44px] text-sm";
const buttonSecondary =
  "px-4 py-2.5 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-50 min-h-[44px] text-sm inline-flex items-center";
const buttonDanger =
  "px-4 py-2.5 rounded-lg border border-red-200 dark:border-red-900 text-red-700 dark:text-red-300 hover:bg-red-50 dark:hover:bg-red-950/40 disabled:opacity-50 min-h-[44px] text-sm";

const PER_PAGE = 25;

function when(iso: string, language: string): string {
  try {
    return new Date(iso).toLocaleString(language, { dateStyle: "medium", timeStyle: "short" });
  } catch {
    return iso;
  }
}

/** The manifest's keys as a reader knows them; anything new keeps its key
 *  with the underscores spaced out. */
const EDITION_LABELS: Record<string, string> = {
  adr: "ADR",
  rid: "RID",
  adn: "ADN",
  imdg: "IMDG",
  imdg_class_tables: "IMDG class tables",
  imdg_un_cards: "IMDG UN cards",
  ems: "EmS",
  iata: "IATA",
};

function editionLabel(key: string): string {
  return EDITION_LABELS[key] ?? key.replace(/_/g, " ").toUpperCase();
}

/** The groupage address a kept trip reopens at. */
export function groupageLinkFor(trip: TripSummary): string {
  return `/groupage?trip=${trip.id}`;
}

export default function TripsPage({ user }: { user?: User | null }) {
  const { t, i18n } = useTranslation();
  const { publicSettings } = usePreferences();
  const { id } = useParams();
  const admin = user?.role === "admin";

  if (publicSettings && !publicSettings.history_enabled) {
    return (
      <div className={`${panelClass} p-5 sm:p-8 space-y-2`}>
        <h2 className="text-xl font-semibold text-slate-900 dark:text-slate-100">{t("trips.title")}</h2>
        <p className="text-sm text-slate-600 dark:text-slate-300">{t("history.off")}</p>
      </div>
    );
  }

  if (id) return <TripView id={Number(id)} language={i18n.language} />;
  return <TripList language={i18n.language} admin={admin} />;
}

function TripList({ language, admin }: { language: string; admin: boolean }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const toast = useToast();
  const [items, setItems] = useState<TripSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [loading, setLoading] = useState(true);
  const [department, setDepartment] = useState("");
  const [departments, setDepartments] = useState<Department[]>([]);

  useEffect(() => {
    if (!admin) return;
    api.departments().then(setDepartments).catch(() => setDepartments([]));
  }, [admin]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const answer = await api.trips({
        q,
        ...localDateFilters(from, to),
        page,
        per_page: PER_PAGE,
        department: admin ? department : undefined,
      });
      setItems(answer.items);
      setTotal(answer.total);
    } catch (e) {
      toast.error(String(e));
    } finally {
      setLoading(false);
    }
    // toast is stable for the provider's lifetime.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, from, to, page, department, admin]);

  useEffect(() => {
    const handle = setTimeout(() => void load(), q ? 250 : 0);
    return () => clearTimeout(handle);
  }, [load, q]);

  const pages = Math.max(1, Math.ceil(total / PER_PAGE));
  const open = (trip: TripSummary) => navigate(`/trips/${trip.id}`);
  const name = (trip: TripSummary) => trip.name || t("trips.noName");

  return (
    <div className="space-y-4 sm:space-y-6">
      <div className={`${panelClass} p-5 sm:p-8 flex flex-wrap items-start justify-between gap-3`}>
        <div>
          <h2 className="text-xl sm:text-2xl font-semibold text-slate-900 dark:text-slate-100">{t("trips.title")}</h2>
          <p className="mt-2 text-sm text-slate-600 dark:text-slate-300 max-w-2xl">{t("trips.intro")}</p>
        </div>
        <Link to="/groupage" className={buttonSecondary}>
          {t("trips.newTrip")}
        </Link>
      </div>

      <div className={`${panelClass} p-4 sm:p-5 grid gap-3 md:grid-cols-[2fr_1fr_1fr]`}>
        <input
          className={inputClass}
          placeholder={t("trips.search")}
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setPage(1);
          }}
          aria-label={t("trips.search")}
        />
        <label className="text-xs text-slate-500 dark:text-slate-400">
          {t("history.from")}
          <input type="date" className={`${inputClass} mt-1`} value={from} onChange={(e) => { setFrom(e.target.value); setPage(1); }} />
        </label>
        <label className="text-xs text-slate-500 dark:text-slate-400">
          {t("history.to")}
          <input type="date" className={`${inputClass} mt-1`} value={to} onChange={(e) => { setTo(e.target.value); setPage(1); }} />
        </label>
        {admin && departments.length > 0 && (
          <select
            className={inputClass}
            value={department}
            onChange={(e) => {
              setDepartment(e.target.value);
              setPage(1);
            }}
            aria-label={t("departments.userDepartment")}
          >
            <option value="">{t("departments.all")}</option>
            <option value="none">{t("departments.unassigned")}</option>
            {departments.map((d) => (
              <option key={d.id} value={String(d.id)}>
                {d.name}
              </option>
            ))}
          </select>
        )}
        <p className="text-xs text-slate-500 dark:text-slate-400 md:col-span-3">
          {t("trips.count", { count: items.length, total })}
        </p>
      </div>

      {!loading && items.length === 0 && (
        <p className={`${panelClass} p-5 text-sm text-slate-600 dark:text-slate-300`}>{t("trips.empty")}</p>
      )}

      {/* Phone: cards */}
      <div className="space-y-3 md:hidden">
        {items.map((trip) => (
          <button
            key={trip.id}
            type="button"
            onClick={() => open(trip)}
            className={`${panelClass} w-full text-left shadow-sm p-4 space-y-1`}
          >
            <div className="flex items-center gap-2">
              <span className="min-w-0 truncate font-semibold text-slate-900 dark:text-slate-100">{name(trip)}</span>
              <Badge trip={trip} />
            </div>
            <p className="text-sm text-slate-700 dark:text-slate-200">
              {t("trips.consignments", { count: trip.consignment_count })}
              {trip.total_points !== null ? ` · ${t("trips.points", { value: trip.total_points })}` : ""}
            </p>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              {when(trip.created_at, language)}
              {trip.created_by ? ` · ${trip.created_by}` : ""}
              {trip.department ? ` · ${trip.department}` : ""}
            </p>
          </button>
        ))}
      </div>

      {/* Desktop: table */}
      {items.length > 0 && (
        <div className={`${panelClass} hidden overflow-x-auto md:block`}>
          <table className="w-full text-sm text-slate-800 dark:text-slate-200">
            <thead className="bg-slate-50 dark:bg-slate-800/80">
              <tr>
                <th className="px-3 py-2 text-left">{t("trips.name")}</th>
                <th className="px-3 py-2 text-right">{t("trips.consignmentsHeader")}</th>
                <th className="px-3 py-2 text-right">{t("trips.pointsHeader")}</th>
                <th className="px-3 py-2 text-left">{t("history.kept")}</th>
                <th className="px-3 py-2 text-left">{t("history.by")}</th>
                {admin && departments.length > 0 && (
                  <th className="px-3 py-2 text-left">{t("departments.userDepartment")}</th>
                )}
              </tr>
            </thead>
            <tbody>
              {items.map((trip) => (
                <tr
                  key={trip.id}
                  onClick={() => open(trip)}
                  className="border-t border-slate-100 dark:border-slate-800 cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800/60"
                >
                  <td className="px-3 py-2">
                    <span className="flex items-center gap-2">
                      <Link to={`/trips/${trip.id}`} className="font-medium text-brand-700 dark:text-brand-300 hover:underline" onClick={(e) => e.stopPropagation()}>
                        {name(trip)}
                      </Link>
                      <Badge trip={trip} />
                    </span>
                  </td>
                  <td className="px-3 py-2 text-right">{trip.consignment_count}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{trip.total_points ?? "—"}</td>
                  <td className="px-3 py-2 whitespace-nowrap">{when(trip.created_at, language)}</td>
                  <td className="px-3 py-2">{trip.created_by || "—"}</td>
                  {admin && departments.length > 0 && <td className="px-3 py-2">{trip.department || "—"}</td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {pages > 1 && (
        <div className="flex items-center justify-between gap-3">
          <button type="button" className={buttonSecondary} disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
            {t("history.previous")}
          </button>
          <span className="text-sm text-slate-500 dark:text-slate-400">{t("history.page", { page, pages })}</span>
          <button type="button" className={buttonSecondary} disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>
            {t("history.next")}
          </button>
        </div>
      )}
    </div>
  );
}

function Badge({ trip }: { trip: TripSummary }) {
  const { t } = useTranslation();
  if (!trip.exemption_lost) return null;
  return (
    <span
      className="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-medium text-amber-800 dark:bg-amber-900/40 dark:text-amber-200"
      title={t("groupage.exemptionLost")}
    >
      {t("trips.exemptionLostShort")}
    </span>
  );
}

function TripView({ id, language }: { id: number; language: string }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const toast = useToast();
  const [trip, setTrip] = useState<TripDetail | null>(null);
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [confirmRemove, setConfirmRemove] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .trip(id)
      .then((detail) => {
        if (!cancelled) setTrip(detail);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  if (failed) {
    return (
      <div className={`${panelClass} p-5 space-y-3`}>
        <p className="text-sm text-slate-600 dark:text-slate-300">{t("trips.notFound")}</p>
        <Link to="/trips" className={buttonSecondary}>
          {t("trips.back")}
        </Link>
      </div>
    );
  }
  if (!trip) {
    return <p className={`${panelClass} p-5 text-sm text-slate-500 dark:text-slate-400`}>{t("trips.loading")}</p>;
  }

  const remove = async () => {
    setConfirmRemove(false);
    setBusy(true);
    try {
      await api.forgetTrip(trip.id);
      toast.success(t("trips.removed"));
      navigate("/trips");
    } catch (e) {
      toast.error(String(e));
      setBusy(false);
    }
  };

  const row = (label: string, value: string | number) => (
    <div className="flex justify-between gap-4 border-b border-slate-100 py-2 text-sm dark:border-slate-800 last:border-b-0">
      <span className="text-slate-500 dark:text-slate-400">{label}</span>
      <span className="text-right text-slate-800 dark:text-slate-100">{value}</span>
    </div>
  );
  const result = trip.result;
  const editions = Object.entries(trip.editions || {})
    .map(([key, value]) => `${editionLabel(key)} ${String(value)}`)
    .join(" · ");

  return (
    <div className="space-y-4 sm:space-y-6 max-w-3xl">
      <Link to="/trips" className="text-sm text-brand-700 dark:text-brand-300 hover:underline">
        ← {t("trips.back")}
      </Link>

      <div className={`${panelClass} p-5 sm:p-8 space-y-4`}>
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-xl sm:text-2xl font-semibold text-slate-900 dark:text-slate-100">
            {trip.name || t("trips.noName")}
          </h2>
          <Badge trip={trip} />
        </div>
        <div>
          {row(t("trips.consignmentsHeader"), trip.consignments.map((c) => c.name).join(", ") || trip.consignment_count)}
          {row(t("history.regulations"), trip.regulations.join(", ") || "—")}
          {row(t("groupage.unitMass"), trip.unit_max_mass_tonnes ?? "—")}
          {row(t("history.kept"), `${when(trip.created_at, language)}${trip.created_by ? ` · ${trip.created_by}` : ""}`)}
          {trip.department && row(t("departments.userDepartment"), trip.department)}
          {trip.updated_at !== trip.created_at && row(t("history.updated"), when(trip.updated_at, language))}
          {editions && row(t("trips.editions"), editions)}
        </div>

        <div className="flex flex-wrap gap-2 pt-2">
          <Link to={groupageLinkFor(trip)} className={buttonPrimary}>
            {t("trips.reopen")}
          </Link>
          <button type="button" className={buttonDanger} disabled={busy} onClick={() => setConfirmRemove(true)}>
            {t("trips.remove")}
          </button>
        </div>
        <p className="text-xs text-slate-500 dark:text-slate-400">{t("trips.keptAsJudged")}</p>
      </div>

      {result && result.consignments && (
        <div className="space-y-4">
          {result.exemption_lost && (
            <div className="rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-700 dark:bg-amber-900/30 dark:text-amber-100">
              <p className="font-semibold">{t("groupage.exemptionLost")}</p>
              <p className="mt-1">{result.exemption_lost.message}</p>
            </div>
          )}
          <div className={`${panelClass} p-4 sm:p-5`}>
            <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
              {t("groupage.apartAndTogether")}
            </h3>
            <table className="mt-2 w-full text-sm">
              <tbody>
                {result.consignments.map((c) => (
                  <tr key={c.name} className="border-b border-slate-100 dark:border-slate-800">
                    <td className="py-1 text-slate-800 dark:text-slate-200">{c.name}</td>
                    <td className="py-1 text-right tabular-nums">{c.points ?? "—"}</td>
                    <td className="py-1 pl-3 text-right text-xs text-slate-500 dark:text-slate-400">
                      {c.exempt === true ? t("groupage.exempt") : c.exempt === false ? t("groupage.notExempt") : t("groupage.incomplete")}
                    </td>
                  </tr>
                ))}
                <tr className="font-semibold">
                  <td className="py-1">{t("groupage.together")}</td>
                  <td className="py-1 text-right tabular-nums">{result.adr_points?.total_points}</td>
                  <td className="py-1 pl-3 text-right text-xs">{t("groupage.threshold", { value: result.adr_points?.threshold })}</td>
                </tr>
              </tbody>
            </table>
          </div>
          {result.mixed_loading && result.mixed_loading.length > 0 && (
            <div className={`${panelClass} p-4 sm:p-5`}>
              <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                {t("groupage.mixedLoading")}
              </h3>
              <ul className="mt-2 space-y-2 text-sm">
                {result.mixed_loading.map((w, i) => (
                  <li key={i} className="text-slate-700 dark:text-slate-300">
                    {w.message}
                    {w.products && <span className="block text-xs text-slate-500 dark:text-slate-400">{w.products}</span>}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {result.lq_marking && (
            <div className={`${panelClass} p-4 sm:p-5`}>
              <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                {result.lq_marking.rule}
              </h3>
              <p className="mt-2 text-sm text-slate-700 dark:text-slate-300">{result.lq_marking.message}</p>
            </div>
          )}
        </div>
      )}

      <ConfirmDialog
        open={confirmRemove}
        title={t("trips.remove")}
        body={t("trips.confirmRemove")}
        confirmLabel={t("trips.remove")}
        onConfirm={remove}
        onCancel={() => setConfirmRemove(false)}
      />
    </div>
  );
}
