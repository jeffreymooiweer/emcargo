import { canUseDgsa, canOversee } from "../permissions";
import HistoryStatus from "../components/HistoryStatus";
/**
 * The shipments this installation kept.
 *
 * Exists only where the history is switched on; elsewhere the page says so
 * rather than showing an empty table over a 404. A table on a wide screen,
 * cards on a phone — the same split the equipment library uses — with three
 * filters: a search over reference and parties, the transport mode, and a
 * date range. Opening a row shows the record and offers the three things
 * one does with a kept shipment: open it in the wizard, download its
 * documents again, or remove it.
 */
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams } from "react-router";

import { api, Department, ShipmentDetail, ShipmentSummary, User } from "../api/client";
import { usePreferences } from "../settings/preferences";
import ConfirmDialog from "../toast/ConfirmDialog";
import { useToast } from "../toast/ToastProvider";
import { localDateFilters } from "../utils/dateRanges";
import { MODALITIES } from "./ModalitySelectPage";

const panelClass = "bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800";
const inputClass =
  "w-full border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-950 text-slate-900 dark:text-slate-100 rounded-lg px-3 py-2.5 text-sm min-h-[44px]";
const buttonPrimary =
  "bg-brand-600 text-white px-4 py-2.5 rounded-lg font-medium hover:bg-brand-700 disabled:opacity-50 min-h-[44px] text-sm";
const buttonSecondary =
  "px-4 py-2.5 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-50 min-h-[44px] text-sm inline-flex items-center";
const actionClass =
  "font-medium text-brand-700 underline hover:text-brand-800 disabled:opacity-50 dark:text-brand-300";
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

/** The wizard address a kept shipment opens at: its own mode, its own id. */
export function wizardLinkFor(shipment: ShipmentSummary): string {
  return `/wizard/${shipment.modality || "road"}?shipment=${shipment.id}`;
}

/** The wizard address that starts a new shipment from a kept one: the same
 *  goods, parties and route, without the reference, the dates or the
 *  record's identity. */
export function templateLinkFor(shipment: ShipmentSummary): string {
  return `/wizard/${shipment.modality || "road"}?template=${shipment.id}`;
}

export default function ShipmentsPage({ user }: { user?: User | null }) {
  const { t, i18n } = useTranslation();
  const { publicSettings } = usePreferences();
  const { id } = useParams();
  // Only an administrator sees more than one department, so only an
  // administrator gets the filter; for anybody else the server answers
  // with their own department whatever is asked.
  const admin = canOversee(user);

  if (!publicSettings?.history_enabled) return <HistoryStatus title={t("history.title")} admin={user?.role === "admin"} />;

  if (id) return <ShipmentView id={Number(id)} language={i18n.language} />;
  return <ShipmentList language={i18n.language} admin={admin} dgsa={canUseDgsa(user, publicSettings)} />;
}

function ShipmentList({ language, admin, dgsa }: { language: string; admin: boolean; dgsa: boolean }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const toast = useToast();
  const [items, setItems] = useState<ShipmentSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [modality, setModality] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [loading, setLoading] = useState(true);
  const [department, setDepartment] = useState("");
  const [departments, setDepartments] = useState<Department[]>([]);
  // The entry this viewer is in the middle of. It is not a kept shipment and
  // the list does not hold it — but it is the thing they are most likely to
  // have come here for, so it stands above the list with the way back into it.
  const [draft, setDraft] = useState<ShipmentDetail | null>(null);
  // The shipments picked for a trip. Kept by id, so paging does not lose them.
  const [picked, setPicked] = useState<number[]>([]);

  useEffect(() => {
    if (!admin) return;
    api.departments().then(setDepartments).catch(() => setDepartments([]));
  }, [admin]);

  useEffect(() => {
    api.runningDraft().then(setDraft).catch(() => setDraft(null));
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const answer = await api.shipments({
        q,
        modality,
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
  }, [q, modality, from, to, page, department, admin]);

  // The search waits for the typing to stop; the other filters act at once.
  useEffect(() => {
    const handle = setTimeout(() => void load(), q ? 250 : 0);
    return () => clearTimeout(handle);
  }, [load, q]);

  const pages = Math.max(1, Math.ceil(total / PER_PAGE));
  const open = (shipment: ShipmentSummary) => navigate(`/shipments/${shipment.id}`);
  const toggle = (id: number) =>
    setPicked((current) => (current.includes(id) ? current.filter((one) => one !== id) : [...current, id]));
  const [busy, setBusy] = useState(false);
  const documentsAgain = async (shipment: ShipmentSummary) => {
    setBusy(true);
    try {
      await api.shipmentDocuments(shipment.id);
    } catch (e) {
      toast.error(String(e));
    } finally {
      setBusy(false);
    }
  };
  const reference = (s: ShipmentSummary) => s.reference || t("history.noReference");
  const parties = (s: ShipmentSummary) => [s.consignor_name, s.consignee_name].filter(Boolean).join(" → ") || "—";

  return (
    <div className="collection-page page-enter space-y-4 sm:space-y-6">
      <div className={`${panelClass} p-5 sm:p-8 flex flex-wrap items-start justify-between gap-3`}>
        <div>
          <h2 className="text-xl sm:text-2xl font-semibold text-slate-900 dark:text-slate-100">{t("history.title")}</h2>
          <p className="mt-2 text-sm text-slate-600 dark:text-slate-300 max-w-2xl">{t("history.intro")}</p>
        </div>
        {dgsa && <Link to="/shipments/report" className={buttonSecondary} title={t("dgsa.intro")}>
          {t("dgsa.title")}
        </Link>}
      </div>

      <div className={`${panelClass} p-4 sm:p-5 grid items-end gap-3 md:grid-cols-[2fr_1fr_1fr_1fr]`}>
        <input
          className={inputClass}
          placeholder={t("history.search")}
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setPage(1);
          }}
          aria-label={t("history.search")}
        />
        <select
          className={inputClass}
          value={modality}
          onChange={(e) => {
            setModality(e.target.value);
            setPage(1);
          }}
          aria-label={t("history.modality")}
        >
          <option value="">{t("history.allModalities")}</option>
          {MODALITIES.map((key) => (
            <option key={key} value={key}>
              {t(`modality.${key}`)}
            </option>
          ))}
        </select>
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
        <p className="text-xs text-slate-500 dark:text-slate-400 md:col-span-4">
          {t("history.count", { count: items.length, total })}
        </p>
      </div>

      {draft && (
        <div className={`${panelClass} flex flex-wrap items-center gap-x-3 gap-y-2 p-4`}>
          <Status shipment={draft} />
          <span className="min-w-0 truncate text-sm font-medium text-slate-900 dark:text-slate-100">
            {draft.reference || t("history.noReference")}
          </span>
          <span className="text-xs text-slate-500 dark:text-slate-400">
            {t(`modality.${draft.modality}`)} · {when(draft.updated_at, language)}
          </span>
          <Link to={wizardLinkFor(draft)} className={`${actionClass} ml-auto`}>
            {t("history.resumeDraft")}
          </Link>
        </div>
      )}

      {picked.length > 0 && (
        <div className={`${panelClass} flex flex-wrap items-center gap-3 p-4`}>
          <span className="text-sm text-slate-700 dark:text-slate-200">
            {t("history.picked", { count: picked.length })}
          </span>
          <Link to={`/groupage?shipments=${picked.join(",")}`} className={`${buttonPrimary} ml-auto`}>
            {t("history.toTrip", { count: picked.length })}
          </Link>
          <button type="button" className={buttonSecondary} onClick={() => setPicked([])}>
            {t("history.clearPicked")}
          </button>
        </div>
      )}

      {!loading && items.length === 0 && (
        <p className={`${panelClass} p-5 text-sm text-slate-600 dark:text-slate-300`}>{t("history.empty")}</p>
      )}

      {/* Phone: cards */}
      <div className="space-y-3 md:hidden">
        {items.map((s) => (
          <div key={s.id} className={`${panelClass} shadow-sm p-4 space-y-2`}>
            <button type="button" onClick={() => open(s)} className="w-full space-y-1 text-left">
              <div className="flex flex-wrap items-center gap-2">
                <span className="min-w-0 truncate font-semibold text-slate-900 dark:text-slate-100">{reference(s)}</span>
                <Status shipment={s} />
                <Badges shipment={s} />
              </div>
              <p className="text-sm text-slate-700 dark:text-slate-200 truncate">{parties(s)}</p>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                {t(`modality.${s.modality}`)} · {when(s.created_at, language)}
                {s.created_by ? ` · ${s.created_by}` : ""}
                {s.department ? ` · ${s.department}` : ""}
              </p>
            </button>
            <div className="flex flex-wrap items-center gap-3">
              <label className="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-300">
                <input
                  type="checkbox"
                  checked={picked.includes(s.id)}
                  onChange={() => toggle(s.id)}
                  // The same name the table's box carries. Without it every
                  // card on a phone offers "Select", five times over, with
                  // nothing saying which shipment each one selects — which is
                  // exactly what somebody using a screen reader would hear.
                  aria-label={`${t("history.pick")} — ${reference(s)}`}
                  className="h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
                />
                {t("history.pick")}
              </label>
              <RowActions shipment={s} onAgain={documentsAgain} busy={busy} />
            </div>
          </div>
        ))}
      </div>

      {/* Desktop: table */}
      {items.length > 0 && (
        <div className={`${panelClass} hidden overflow-x-auto md:block`}>
          <table className="w-full text-sm text-slate-800 dark:text-slate-200">
            <thead className="bg-slate-50 dark:bg-slate-800/80">
              <tr>
                <th className="px-3 py-2 text-left">
                  <span className="sr-only">{t("history.pick")}</span>
                </th>
                <th className="px-3 py-2 text-left">{t("history.reference")}</th>
                <th className="px-3 py-2 text-left">{t("history.parties")}</th>
                <th className="px-3 py-2 text-left">{t("history.modality")}</th>
                <th className="px-3 py-2 text-left">{t("history.kept")}</th>
                <th className="px-3 py-2 text-left">{t("history.by")}</th>
                {admin && departments.length > 0 && (
                  <th className="px-3 py-2 text-left">{t("departments.userDepartment")}</th>
                )}
                <th className="px-3 py-2 text-right">{t("history.goods")}</th>
                <th className="px-3 py-2 text-left">{t("history.actions")}</th>
              </tr>
            </thead>
            <tbody>
              {items.map((s) => (
                <tr
                  key={s.id}
                  onClick={() => open(s)}
                  className="border-t border-slate-100 dark:border-slate-800 cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800/60"
                >
                  <td className="px-3 py-2">
                    <input
                      type="checkbox"
                      checked={picked.includes(s.id)}
                      onChange={() => toggle(s.id)}
                      onClick={(e) => e.stopPropagation()}
                      aria-label={`${t("history.pick")} — ${reference(s)}`}
                      className="h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
                    />
                  </td>
                  <td className="px-3 py-2">
                    <span className="flex flex-wrap items-center gap-2">
                      <Link to={`/shipments/${s.id}`} className="font-medium text-brand-700 dark:text-brand-300 hover:underline" onClick={(e) => e.stopPropagation()}>
                        {reference(s)}
                      </Link>
                      <Status shipment={s} />
                      <Badges shipment={s} />
                    </span>
                  </td>
                  <td className="px-3 py-2">{parties(s)}</td>
                  <td className="px-3 py-2 whitespace-nowrap">{t(`modality.${s.modality}`)}</td>
                  <td className="px-3 py-2 whitespace-nowrap">{when(s.created_at, language)}</td>
                  <td className="px-3 py-2">{s.created_by || "—"}</td>
                  {admin && departments.length > 0 && <td className="px-3 py-2">{s.department || "—"}</td>}
                  <td className="px-3 py-2 text-right">{s.goods_count}</td>
                  <td className="px-3 py-2">
                    <RowActions shipment={s} onAgain={documentsAgain} busy={busy} />
                  </td>
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

/** What one does with a kept shipment, on the row it is about.
 *
 *  The baseline found no reuse action on the list at all: opening the detail
 *  page was compulsory before anything could be done. These are the same three
 *  things that page offers, where the shipment is. */
function RowActions({ shipment, onAgain, busy }: {
  shipment: ShipmentSummary;
  onAgain: (shipment: ShipmentSummary) => void;
  busy: boolean;
}) {
  const { t } = useTranslation();
  const stop = (event: { stopPropagation: () => void }) => event.stopPropagation();
  return (
    <span className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
      <Link to={wizardLinkFor(shipment)} onClick={stop} className={actionClass}>
        {t("history.edit")}
      </Link>
      <Link to={templateLinkFor(shipment)} onClick={stop} className={actionClass}>
        {t("history.useTemplate")}
      </Link>
      {shipment.has_documents && (
        <button
          type="button"
          disabled={busy}
          onClick={(event) => {
            stop(event);
            onAgain(shipment);
          }}
          className={actionClass}
        >
          {t("history.documents")}
        </button>
      )}
    </span>
  );
}

/** Draft, still to be filled in, or ready. What a row is, in one word.
 *
 *  "Ready" is what produced documents: the bundle was kept, so the papers can
 *  be handed out again. A shipment kept without them is not broken — it is
 *  entry that stopped before the documents — and says so rather than looking
 *  finished. */
function Status({ shipment }: { shipment: ShipmentSummary }) {
  const { t } = useTranslation();
  const [key, className] = shipment.is_draft
    ? ["history.stateDraft", "bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-200"]
    : shipment.has_documents
      ? ["history.stateReady", "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200"]
      : ["history.stateOpen", "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300"];
  return (
    <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${className}`}>{t(key)}</span>
  );
}

function Badges({ shipment }: { shipment: ShipmentSummary }) {
  const { t } = useTranslation();
  return (
    <>
      {shipment.has_dangerous_goods && (
        <span
          className="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-medium text-amber-800 dark:bg-amber-900/40 dark:text-amber-200"
          title={t("history.dg")}
        >
          {shipment.regulations.join("/") || "DG"}
        </span>
      )}
    </>
  );
}

function ShipmentView({ id, language }: { id: number; language: string }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const toast = useToast();
  const [shipment, setShipment] = useState<ShipmentDetail | null>(null);
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [confirmRemove, setConfirmRemove] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .shipment(id)
      .then((detail) => {
        if (!cancelled) setShipment(detail);
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
        <p className="text-sm text-slate-600 dark:text-slate-300">{t("history.loadFailed")}</p>
        <Link to="/shipments" className="text-sm text-brand-700 dark:text-brand-300 hover:underline">{t("history.back")}</Link>
      </div>
    );
  }
  if (!shipment) return null;

  const documents = Array.isArray(shipment.export.documents) ? (shipment.export.documents as string[]) : [];
  const downloadAgain = async () => {
    setBusy(true);
    try {
      await api.shipmentDocuments(shipment.id);
    } catch (e) {
      toast.error(String(e));
    } finally {
      setBusy(false);
    }
  };
  const remove = async () => {
    setConfirmRemove(false);
    setBusy(true);
    try {
      await api.forgetShipment(shipment.id);
      toast.success(t("history.removed"));
      navigate("/shipments");
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

  return (
    <div className="collection-page page-enter space-y-4 sm:space-y-6 max-w-3xl">
      <Link to="/shipments" className="text-sm text-brand-700 dark:text-brand-300 hover:underline">
        ← {t("history.back")}
      </Link>

      <div className={`${panelClass} p-5 sm:p-8 space-y-4`}>
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-xl sm:text-2xl font-semibold text-slate-900 dark:text-slate-100">
            {shipment.reference || t("history.noReference")}
          </h2>
          <Badges shipment={shipment} />
        </div>
        <div>
          {row(t("history.modality"), t(`modality.${shipment.modality}`))}
          {row(t("history.parties"), [shipment.consignor_name, shipment.consignee_name].filter(Boolean).join(" → ") || "—")}
          {row(t("history.goods"), shipment.goods_count)}
          {row(t("history.regulations"), shipment.regulations.join(", ") || "—")}
          {documents.length > 0 && row(t("history.documentsOf"), documents.join(", "))}
          {row(t("history.kept"), `${when(shipment.created_at, language)}${shipment.created_by ? ` · ${shipment.created_by}` : ""}`)}
          {shipment.department && row(t("departments.userDepartment"), shipment.department)}
          {shipment.updated_at !== shipment.created_at && row(t("history.updated"), when(shipment.updated_at, language))}
        </div>

        <div className="flex flex-wrap gap-2 pt-2">
          <Link to={wizardLinkFor(shipment)} className={buttonPrimary}>
            {t("history.open")}
          </Link>
          <Link to={templateLinkFor(shipment)} className={buttonSecondary} title={t("history.useTemplateHint")}>
            {t("history.useTemplate")}
          </Link>
          {shipment.has_documents ? (
            <button type="button" className={buttonSecondary} disabled={busy} onClick={downloadAgain}>
              {t("history.documents")}
            </button>
          ) : null}
          <a className={buttonSecondary} href={api.shipmentExportUrl(shipment.id)} download>
            {t("history.exportJson")}
          </a>
          <button type="button" className={buttonDanger} disabled={busy} onClick={() => setConfirmRemove(true)}>
            {t("history.remove")}
          </button>
        </div>
        <p className="text-xs text-slate-500 dark:text-slate-400">
          {shipment.has_documents ? t("history.documentsHint") : t("history.documentsNone")}
        </p>
      </div>

      <ConfirmDialog
        open={confirmRemove}
        title={t("history.remove")}
        body={t("history.confirmRemove")}
        confirmLabel={t("history.remove")}
        onConfirm={remove}
        onCancel={() => setConfirmRemove(false)}
      />
    </div>
  );
}
