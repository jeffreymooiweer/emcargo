import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useToast } from "../toast/ToastProvider";
import NumberInput from "../components/NumberInput";
import { ImportIcon, DownloadIcon, DocumentIcon, PenIcon as PencilIcon, CopyIcon, TrashIcon, PlusIcon, ChevronDownIcon } from "../components/icons";
import { api, EquipmentItem } from "../api/client";
import EquipmentImportDialog from "../components/EquipmentImportDialog";

const inputClass =
  "border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-950 text-slate-900 dark:text-slate-100 rounded-lg px-3 py-2 text-sm";
const panelClass = "bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800";

function CardAction({
  label,
  onClick,
  icon,
  danger,
}: {
  label: string;
  onClick: () => void;
  icon: React.ReactNode;
  danger?: boolean;
}) {
  const tone = danger
    ? "text-slate-500 hover:bg-red-50 hover:text-red-600 dark:text-slate-400 dark:hover:bg-red-950/40 dark:hover:text-red-400"
    : "text-slate-500 hover:bg-slate-100 hover:text-slate-800 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100";
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      className={`inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg transition-colors ${tone}`}
    >
      {icon}
    </button>
  );
}

function CardRow({ label, children }: { label: string; children: React.ReactNode }) {
  const rowRef = useRef<HTMLDivElement>(null);
  const labelProbeRef = useRef<HTMLSpanElement>(null);
  const valueProbeRef = useRef<HTMLSpanElement>(null);
  const [stacked, setStacked] = useState(false);

  useLayoutEffect(() => {
    const row = rowRef.current;
    const labelProbe = labelProbeRef.current;
    const valueProbe = valueProbeRef.current;
    if (!row || !labelProbe || !valueProbe) return;
    const measure = () => {
      const gap = 16;
      const available = row.clientWidth - labelProbe.offsetWidth - gap;
      setStacked(valueProbe.offsetWidth > available);
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(row);
    return () => observer.disconnect();
  }, [label, children]);

  return (
    <div className="border-t border-slate-100 px-4 py-2.5 text-sm first:border-t-0 dark:border-slate-800">
      <div ref={rowRef} className="relative">
        {/* Invisible probes measure the natural width on one line. */}
        <span ref={labelProbeRef} aria-hidden className="pointer-events-none invisible absolute left-0 top-0 whitespace-nowrap">
          {label}
        </span>
        <span ref={valueProbeRef} aria-hidden className="pointer-events-none invisible absolute left-0 top-0 whitespace-nowrap font-medium">
          {children}
        </span>
        {stacked ? (
          <div className="flex flex-col gap-1">
            <span className="text-slate-500 dark:text-slate-400">{label}</span>
            <span className="break-words text-right font-medium text-slate-900 dark:text-slate-100">{children}</span>
          </div>
        ) : (
          <div className="flex items-start justify-between gap-4">
            <span className="shrink-0 text-slate-500 dark:text-slate-400">{label}</span>
            <span className="text-right font-medium text-slate-900 dark:text-slate-100">{children}</span>
          </div>
        )}
      </div>
    </div>
  );
}

const emptyForm = (): EquipmentItem => ({
  specifications: "",
  length_cm: null,
  width_cm: null,
  height_cm: null,
  wall_thickness_mm: null,
  weight_kg: 0,
  aliases: [],
  language_labels: {},
  active: true,
});

export default function MaterieelPage() {
  const { t } = useTranslation();
  const [items, setItems] = useState<EquipmentItem[]>([]);
  const [search, setSearch] = useState("");
  const [form, setForm] = useState<EquipmentItem>(emptyForm());
  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const toast = useToast();
  const [importOpen, setImportOpen] = useState(false);

  const load = () => api.listEquipment().then(setItems).catch((e) => toast.error(String(e)));
  useEffect(() => { load(); }, []);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return items;
    return items.filter((item) => {
      const hay = [
        item.specifications,
        ...(item.aliases || []),
        ...Object.values(item.language_labels || {}),
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return hay.includes(q);
    });
  }, [items, search]);

  const resetForm = () => {
    setFormOpen(false);
    setForm(emptyForm());
    setEditingId(null);
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    const payload = {
      ...form,
      aliases: (form.aliases as string[] | undefined) || [],
      language_labels: form.language_labels || {},
      weight_kg: Number(form.weight_kg),
      length_cm: form.length_cm ? Number(form.length_cm) : null,
      width_cm: form.width_cm ? Number(form.width_cm) : null,
      height_cm: form.height_cm ? Number(form.height_cm) : null,
      wall_thickness_mm: form.wall_thickness_mm ? Number(form.wall_thickness_mm) : null,
    };
    try {
      if (editingId) {
        await api.updateEquipment(editingId, payload);
      } else {
        await api.createEquipment(payload);
      }
      resetForm();
      load();
    } catch (err) {
      setError(String(err));
    }
  };

  const startEdit = (item: EquipmentItem) => {
    setFormOpen(true);
    setEditingId(item.id!);
    setForm({ ...item, aliases: item.aliases || [] });
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const duplicate = (item: EquipmentItem) => {
    setFormOpen(true);
    setEditingId(null);
    setForm({ ...emptyForm(), ...item, id: undefined, aliases: item.aliases || [] });
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const remove = (item: EquipmentItem) => {
    // Deferred delete with undo: the card disappears now, the DELETE fires
    // when the six-second window closes. Undo means no call was ever made.
    const id = item.id!;
    if (editingId === id) resetForm();
    setItems((current) => current.filter((candidate) => candidate.id !== id));
    toast.undoable(t("toast.deletedItem", { name: item.specifications }), {
      execute: () => {
        api.deleteEquipment(id).then(load).catch((e) => {
          toast.error(String(e));
          void load();
        });
      },
      restore: () => setItems((current) =>
        current.some((candidate) => candidate.id === id) ? current : [...current, item]),
    });
  };

  return (
    <div className="collection-page page-enter space-y-6">
      <header>
        <h2 className="text-2xl font-semibold">{t("nav.materieel")}</h2>
        <p className="min-w-0 flex-1 text-sm text-slate-600 dark:text-slate-400">{t("materieel.intro")}</p>
        <div className="mt-5 flex flex-wrap gap-2">
          <button className="action-secondary" onClick={() => api.downloadEquipmentTemplate().catch((e) => toast.error(String(e)))}><DocumentIcon />{t("import.downloadTemplate")}</button>
          <button className="action-secondary" onClick={() => api.exportEquipmentLibrary().catch((e) => toast.error(String(e)))}><DownloadIcon />{t("materieel.exportLibrary")}</button>
          <button className="action-secondary" onClick={() => setImportOpen(true)}><ImportIcon />{t("materieel.import")}</button>
        </div>
      </header>

      <details className="surface collection-form" open={formOpen} onToggle={(event) => setFormOpen(event.currentTarget.open)}>
        <summary><PlusIcon /><span>{editingId ? t("materieel.edit") : t("materieel.add")}</span><ChevronDownIcon /></summary>
        <form onSubmit={submit} className="collection-form-body grid md:grid-cols-2 gap-4">
        <label className="equipment-field md:col-span-2">{t("materieel.specifications")}<input className={`${inputClass} md:col-span-2`} required placeholder={t("materieel.specifications")} value={form.specifications} onChange={(e) => setForm({ ...form, specifications: e.target.value })} /></label>
        <label className="equipment-field">{t("materieel.length")}<NumberInput className={inputClass} step="0.1" placeholder={t("materieel.length")} value={form.length_cm ?? ""} onChange={(e) => setForm({ ...form, length_cm: e.target.value ? Number(e.target.value) : null })} /></label>
        <label className="equipment-field">{t("materieel.width")}<NumberInput className={inputClass} step="0.1" placeholder={t("materieel.width")} value={form.width_cm ?? ""} onChange={(e) => setForm({ ...form, width_cm: e.target.value ? Number(e.target.value) : null })} /></label>
        <label className="equipment-field">{t("materieel.height")}<NumberInput className={inputClass} step="0.1" placeholder={t("materieel.height")} value={form.height_cm ?? ""} onChange={(e) => setForm({ ...form, height_cm: e.target.value ? Number(e.target.value) : null })} /></label>
        <label className="equipment-field">{t("materieel.wallThickness")}<NumberInput className={inputClass} step="0.1" placeholder={t("materieel.wallThickness")} value={form.wall_thickness_mm ?? ""} onChange={(e) => setForm({ ...form, wall_thickness_mm: e.target.value ? Number(e.target.value) : null })} /></label>
        <label className="equipment-field">{t("materieel.weight")}<NumberInput className={inputClass} step="0.1" required placeholder={t("materieel.weight")} value={form.weight_kg || ""} onChange={(e) => setForm({ ...form, weight_kg: Number(e.target.value) })} /></label>
        <label className="equipment-field md:col-span-2">{t("materieel.aliases")}
        <input
          className={`${inputClass} md:col-span-2`}
          placeholder={t("materieel.aliases")}
          value={(form.aliases || []).join(", ")}
          onChange={(e) => setForm({ ...form, aliases: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })}
        />
        </label>
        <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
          <input type="checkbox" checked={form.active !== false} onChange={(e) => setForm({ ...form, active: e.target.checked })} />
          {t("materieel.active")}
        </label>
        <div className="flex gap-2 md:col-span-2">
          <button type="submit" className="bg-brand-600 text-white rounded-lg px-4 py-2 text-sm">
            {editingId ? t("materieel.save") : t("materieel.create")}
          </button>
          {editingId && (
            <button type="button" onClick={resetForm} className="border border-slate-200 dark:border-slate-700 rounded-lg px-4 py-2 text-sm">
              {t("materieel.cancel")}
            </button>
          )}
        </div>
        </form>
      </details>

      <div className={`${panelClass} p-4`}>
        <input
          className={`${inputClass} w-full max-w-md`}
          placeholder={t("materieel.search")}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <p className="text-xs text-slate-500 dark:text-slate-400 mt-2">
          {t("materieel.count", { count: filtered.length, total: items.length })}
        </p>
      </div>

      {/* Cards on narrow screens. */}
      <div className="space-y-3 md:hidden">
        {filtered.map((item) => (
          <div key={item.id} className={`${panelClass} shadow-sm`}>
            <div className="flex items-center gap-2 border-b border-slate-100 px-4 py-3 dark:border-slate-800">
              <span className="min-w-0 truncate font-semibold text-slate-900 dark:text-slate-100">
                {item.specifications}
              </span>
              {item.active === false && (
                <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500 dark:bg-slate-800 dark:text-slate-400">
                  {t("materieel.inactive")}
                </span>
              )}
              <div className="ml-auto flex items-center gap-0.5">
                <CardAction label={t("materieel.edit")} onClick={() => startEdit(item)} icon={<PencilIcon />} />
                <CardAction label={t("materieel.duplicate")} onClick={() => duplicate(item)} icon={<CopyIcon />} />
                <CardAction label={t("materieel.delete")} onClick={() => remove(item)} icon={<TrashIcon />} danger />
              </div>
            </div>
            <div>
              <CardRow label={t("materieel.dimensions")}>
                {[item.length_cm, item.width_cm, item.height_cm].filter((v) => v != null).join(" × ") || "—"}
              </CardRow>
              {item.wall_thickness_mm != null && (
                <CardRow label={t("materieel.wallThickness")}>{item.wall_thickness_mm} mm</CardRow>
              )}
              <CardRow label={t("materieel.weight")}>{item.weight_kg} kg</CardRow>
              {item.aliases && item.aliases.length > 0 && (
                <CardRow label={t("materieel.aliases")}>{item.aliases.join(", ")}</CardRow>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Desktop: tabel */}
      <div className={`${panelClass} hidden overflow-x-auto max-h-[32rem] overflow-y-auto md:block`}>
        <table className="w-full text-sm text-slate-800 dark:text-slate-200">
          <thead className="bg-slate-50 dark:bg-slate-800/80 sticky top-0">
            <tr>
              <th className="px-3 py-2 text-left">{t("materieel.specifications")}</th>
              <th className="px-3 py-2 text-left">L×B×H</th>
              <th className="px-3 py-2 text-left">{t("materieel.wallThickness")}</th>
              <th className="px-3 py-2 text-left">{t("materieel.weight")}</th>
              <th className="px-3 py-2 text-left"></th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((item) => (
              <tr key={item.id} className="border-t border-slate-100 dark:border-slate-800">
                <td className="px-3 py-2">{item.specifications}</td>
                <td className="px-3 py-2 whitespace-nowrap">
                  {[item.length_cm, item.width_cm, item.height_cm].filter((v) => v != null).join(" × ") || "—"}
                </td>
                <td className="px-3 py-2 whitespace-nowrap">
                  {item.wall_thickness_mm != null ? `${item.wall_thickness_mm} mm` : "—"}
                </td>
                <td className="px-3 py-2 whitespace-nowrap">{item.weight_kg} kg</td>
                <td className="px-3 py-2 whitespace-nowrap">
                  <div className="flex items-center gap-0.5">
                    <CardAction label={t("materieel.edit")} onClick={() => startEdit(item)} icon={<PencilIcon />} />
                    <CardAction label={t("materieel.duplicate")} onClick={() => duplicate(item)} icon={<CopyIcon />} />
                    <CardAction label={t("materieel.delete")} onClick={() => remove(item)} icon={<TrashIcon />} danger />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {error && <p className="text-red-600 dark:text-red-400 text-sm">{error}</p>}

      <EquipmentImportDialog open={importOpen} onClose={() => setImportOpen(false)} onComplete={load} />
    </div>
  );
}
