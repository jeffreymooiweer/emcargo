import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, type Department, type TripSummary } from "../../api/client";
import { SearchIcon, TripsIcon, WarningIcon } from "../../components/icons";
import { localDateFilters } from "../../utils/dateRanges";

export default function TripLibrary({ activeId, revision, oversee, disabled, onSelect }: {
  activeId: number | null; revision: number; oversee: boolean; disabled: boolean; onSelect: (id: number) => void;
}) {
  const { t, i18n } = useTranslation();
  const [q, setQ] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [department, setDepartment] = useState("");
  const [departments, setDepartments] = useState<Department[]>([]);
  const [page, setPage] = useState(1);
  const [rows, setRows] = useState<TripSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (!oversee) return;
    let cancelled = false;
    api.departments().then(values => { if (!cancelled) setDepartments(values); }).catch(() => {});
    return () => { cancelled = true; };
  }, [oversee]);
  useEffect(() => {
    let cancelled = false;
    setLoading(true); setFailed(false);
    const timer = setTimeout(() => {
      api.trips({ q, ...localDateFilters(from, to), department: oversee ? department : undefined, page, per_page: 10 }).then(answer => {
        if (!cancelled) {
          setRows(answer.items); setTotal(answer.total);
          if (page > 1 && !answer.items.length) setPage(1);
        }
      }).catch(() => { if (!cancelled) setFailed(true); }).finally(() => { if (!cancelled) setLoading(false); });
    }, q ? 250 : 0);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [q, from, to, department, oversee, page, revision, retry]);
  return <aside className="trip-library" aria-labelledby="trip-library-title">
    <h2 id="trip-library-title">{t("tripWorkspace.library")}<span>{total}</span></h2>
    <div className="trip-search"><SearchIcon /><input type="search" aria-label={t("trips.search")} placeholder={t("trips.search")} value={q} maxLength={120} onChange={event => { setQ(event.target.value); setPage(1); }} /></div>
    <details className="trip-filters"><summary>{t("tripWorkspace.filters")}</summary><div>
      <label>{t("history.from")}<input type="date" value={from} onChange={event => { setFrom(event.target.value); setPage(1); }} /></label>
      <label>{t("history.to")}<input type="date" value={to} onChange={event => { setTo(event.target.value); setPage(1); }} /></label>
      {oversee && departments.length > 0 && <label>{t("departments.userDepartment")}<select value={department} onChange={event => { setDepartment(event.target.value); setPage(1); }}><option value="">{t("departments.all")}</option><option value="none">{t("departments.unassigned")}</option>{departments.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}</select></label>}
    </div></details>
    {failed ? <div role="alert" className="trip-inline-error">{t("tripWorkspace.tripsFailed")}<button className="trip-text-button" type="button" onClick={() => setRetry(v => v + 1)}>{t("tripWorkspace.retry")}</button></div>
      : loading ? <p role="status" className="trip-muted">{t("trips.loading")}</p>
      : !rows.length ? <div className="trip-library-empty"><TripsIcon /><p>{t(q || from || to || department ? "tripWorkspace.noMatches" : "tripWorkspace.noTrips")}</p></div>
      : <ul>{rows.map(trip => <li key={trip.id}><button type="button" className={trip.id === activeId ? "is-current" : ""} disabled={disabled} aria-current={trip.id === activeId ? "true" : undefined} onClick={() => onSelect(trip.id)}>
        <strong>{trip.name || t("trips.noName")}{trip.exemption_lost && <WarningIcon aria-label={t("trips.exemptionLostShort")} />}</strong>
        <span>{t("trips.consignments", { count: trip.consignment_count })} · {new Date(trip.updated_at).toLocaleDateString(i18n.language, { day: "numeric", month: "short" })}</span>
        {oversee && trip.department && <span>{trip.department}</span>}
      </button></li>)}</ul>}
    {total > 10 && <div className="trip-pagination"><button type="button" disabled={page === 1 || loading} onClick={() => setPage(p => p - 1)}>{t("history.previous")}</button><span>{page} / {Math.ceil(total / 10)}</span><button type="button" disabled={page * 10 >= total || loading} onClick={() => setPage(p => p + 1)}>{t("history.next")}</button></div>}
  </aside>;
}
