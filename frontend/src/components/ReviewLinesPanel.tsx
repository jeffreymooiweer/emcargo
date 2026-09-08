/**
 * The goods step: one compact line per goods line, edited where it stands.
 *
 * Until v1.192.0 every line was a read-only card and everything changeable
 * lived behind an edit icon, in a dialog. That shape was the right answer to
 * the wrong question. It replaced a table of thirteen input fields — which
 * genuinely did not fit any screen — but it charged three actions and a window
 * for changing a number: the baseline measured five quantity corrections at
 * fifteen actions and five dialogs, none of which was the number itself.
 *
 * What is here now is the middle the two shapes missed. Four things live on the
 * line, because they are what a consignment is made of and what people come
 * back to change: the description, the quantity, the unit, and — read-only —
 * what EMCargo worked out from them. The thirteen fields are not back:
 * dimensions, wall thickness, cargo form, own weights and the article stay in
 * the detail dialog, one click away, exactly as they were.
 *
 * The row wraps rather than switching layouts. On a phone the description takes
 * the width and the quantity, the unit and the outcome fall underneath it; on a
 * laptop it is one line. One implementation, so the validation, the focus order
 * and the keyboard are the same everywhere — a second layout is a second set of
 * bugs.
 *
 * **Getting a list in.** Pasting from Excel and choosing a file are actions on
 * this panel rather than a dialog to find, and the panel takes a dropped file —
 * see ``GoodsImport``. What came out is said above the list: how many lines are
 * settled, how many want looking at, and a filter that narrows to those. Fifty
 * imported lines with one that needs attention used to be fifty cards of
 * scrolling with nothing pointing at it.
 *
 * **Derived figures while the calculation runs.** Typing clears the result, and
 * the wizard recalculates six-tenths of a second after the typing stops. A line
 * whose own text has not changed keeps showing what was worked out for it,
 * dimmed and marked *to be rechecked*; the line being edited shows no figures at
 * all, because a weight that belongs to the previous description is not a
 * weight. Nothing on this screen shows a number for input it was not computed
 * from.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { LineItem, UnitCatalogue, api, ArticleRef } from "../api/client";
import { useToast } from "../toast/ToastProvider";
import EquipmentCombobox from "./EquipmentCombobox";
import GoodsImport from "./GoodsImport";
import LineDetails, { ROUND_TYPES, WALL_PROFILE_TYPES, isDangerous } from "./LineDetails";
import NumberInput from "./NumberInput";
import UnitSelect from "./UnitSelect";

export interface DraftLine {
  id: number;
  description: string;
  quantity: number | "";
  unit: string;
  /** The form this commodity travels in: solid, stacked, loose bulk. Determines
   *  how much of a cubic metre is actually material. */
  cargo_form?: string;
  /** Wall thickness in millimetres. Only meaningful with a cross-section that
   *  has a wall — an angle or a hollow section. For a plate or a beam the three
   *  outside measurements already describe the material completely. */
  wall_thickness_mm?: number | "";
  /** Dimensions the user fills in themselves, in centimetres. They no longer
   *  have to be hidden in the description to count. */
  length_cm?: number | "";
  width_cm?: number | "";
  height_cm?: number | "";
  dangerous_goods?: boolean;
  /** UN number the user confirmed from a name suggestion. Carries through to
   *  the DG step so nothing recognised has to be typed again. */
  confirmed_un?: string;
  /** The suggestion was rejected for this line; it must not come back. Kept
   *  because the assistant and older saved shipments speak it; what the screen
   *  reads is ``dg_decision``, which this maps onto. */
  dg_dismissed?: boolean;
  /** What the user answered to the substance recognition: they took the
   *  suggested UN number, they said it is a different substance, or they said
   *  the suggestion is wrong. Undefined means nobody has answered yet — which
   *  is not the same as "no", and is why closing something cannot set it. */
  dg_decision?: "confirmed" | "other" | "rejected";
  /** Net content of one package as the description said it ("25 L"); the DG
   *  derivation fills the per-package quantity from it. */
  package_content?: string;
  /**
   * The substance's identity, stated on the line it is about.
   *
   * Until v1.203.0 these lived only on the dangerous-goods step, which meant
   * the goods step recognised UN 1203 on a line and then the next step asked
   * what the substance was — the same question, one step further on. They are
   * answered here now and seeded into the step's product, so the step is left
   * with what it is actually for: the assessment.
   *
   * The class is deliberately not among them. It follows from the UN number
   * through Table A, and a field for it is an invitation to state something
   * the tables will contradict.
   */
  proper_shipping_name?: string;
  packing_group?: string;
  type_of_package?: string;
  /** The library article this line was picked from, if any. Its UN number
   *  travels as `confirmed_un`; the rest seeds the DG product. */
  article?: ArticleRef;
  /** Weight of one item or package the consignor stated themselves, for goods
   *  the catalogue cannot weigh. Never a computed value. */
  weight_each_kg?: number | "";
}

const panelClass = "bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800";
const fieldClass =
  "border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-950 text-slate-900 " +
  "dark:text-slate-100 rounded-lg px-3 py-2.5 text-sm min-h-[44px]";
const labelClass = "text-[11px] uppercase tracking-wide text-slate-500 dark:text-slate-400";

interface Props {
  draftLines: DraftLine[];
  resultLines?: LineItem[];
  onDraftChange: (lines: DraftLine[]) => void;
  onRemoveLine: (id: number) => void;
  onDuplicateLine: (id: number) => void;
  onAddLine: () => void;
  onImport?: (text: string, mode: "append" | "replace") => void;
  onLineWeightChange?: (lineId: number, field: "weight_each_kg" | "weight_total_kg", value: number | null) => void;
  initialPaste?: boolean;
  translateMessage: (msg: string) => string;
}

function statusColor(status: string) {
  if (status === "ok") return "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300";
  if (status === "error") return "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300";
  if (status === "needs_review") return "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300";
  return "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300";
}

/** What was answered to a line's substance question, if anything.
 *
 *  ``dg_decision`` is what the screen writes. The two older fields are read as
 *  well, so a shipment saved before v1.195.0 — or one the assistant filled in —
 *  opens with its answers intact rather than asking everything again. */
function decisionOf(line: DraftLine): DraftLine["dg_decision"] | undefined {
  if (line.dg_decision) return line.dg_decision;
  if (line.confirmed_un) return "confirmed";
  if (line.dg_dismissed) return "rejected";
  return undefined;
}

/** Whether this line is still waiting for an answer about its substance. */
export function hasOpenQuestion(line: DraftLine, item: LineItem | null | undefined): boolean {
  return !!item && (item.dg_name_candidates?.length ?? 0) > 0 && !decisionOf(line);
}

/** How many lines are still waiting, for whoever has to say so elsewhere. */
export function openQuestions(lines: DraftLine[], items?: LineItem[]): number {
  return lines.filter((line, index) => hasOpenQuestion(line, items?.[index])).length;
}

/** A line the calculation could not settle: no weight came out, or it wants
 *  looking at. These are what the filter above the list narrows to. */
function needsAttention(item: LineItem | null): boolean {
  return !!item && item.status !== "ok";
}

/** What a line's derived figures were computed from. Two lines with the same
 *  signature have the same answer; a line whose signature moved has none yet. */
function signatureOf(line: DraftLine): string {
  return JSON.stringify([
    line.description.trim(), line.quantity, line.unit, line.cargo_form ?? "",
    line.length_cm ?? "", line.width_cm ?? "", line.height_cm ?? "", line.wall_thickness_mm ?? "",
  ]);
}

function PlusIcon() {
  return (
    <svg className="h-4 w-4" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth={1.8} aria-hidden>
      <path d="M10 4v12M4 10h12" strokeLinecap="round" />
    </svg>
  );
}

/** The disclosure arrow. It points down when the line is closed and up when it
 *  is open, so the glyph says what pressing it will do. */
function DetailsIcon({ open }: { open: boolean }) {
  return (
    <svg
      className={`h-4 w-4 transition-transform duration-200 motion-reduce:transition-none ${open ? "rotate-180" : ""}`}
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      aria-hidden
    >
      <path d="m5 8 5 5 5-5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function CopyIcon() {
  return (
    <svg className="h-4 w-4" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth={1.6} aria-hidden>
      <rect x="7" y="7" width="9" height="9" rx="2" />
      <path d="M13 7V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h2" />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg className="h-4 w-4" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth={1.6} aria-hidden>
      <path d="M4 6h12M8 6V4.5A1.5 1.5 0 0 1 9.5 3h1A1.5 1.5 0 0 1 12 4.5V6m-6 0v9a2 2 0 0 0 2 2h4a2 2 0 0 0 2-2V6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function RowAction({ label, onClick, icon, danger, disabled, expanded, controls }: {
  label: string;
  onClick: () => void;
  icon: React.ReactNode;
  danger?: boolean;
  disabled?: boolean;
  /** Set on a disclosure, so the button says whether the line is open. */
  expanded?: boolean;
  controls?: string;
}) {
  const tone = danger
    ? "text-slate-500 hover:bg-red-50 hover:text-red-600 dark:text-slate-400 dark:hover:bg-red-950/40 dark:hover:text-red-400"
    : "text-slate-500 hover:bg-slate-100 hover:text-slate-800 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100";
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      aria-expanded={expanded}
      aria-controls={controls}
      title={label}
      className={`inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg transition-colors disabled:opacity-40 disabled:pointer-events-none ${tone}`}
    >
      {icon}
    </button>
  );
}

export default function ReviewLinesPanel({
  draftLines,
  resultLines,
  onDraftChange,
  onRemoveLine,
  onDuplicateLine,
  onAddLine,
  onImport,
  onLineWeightChange,
  translateMessage,
  initialPaste,
}: Props) {
  const { t } = useTranslation();
  const toast = useToast();
  const canRemove = draftLines.length > 1;

  // Which line is open, by id rather than by index: a line can be removed or
  // duplicated while it stands open, and an index would then quietly point at
  // another line.
  //
  // One at a time. The panel is a screenful of fields, and two of them open
  // means the row you are comparing against has scrolled off — which is the
  // problem the dialog had, in a different shape.
  const [openId, setOpenId] = useState<number | null>(null);
  // A file dropped on the panel, handed to the import; and whether something is
  // being dragged over it, so the panel can say it will take it.
  const [dropped, setDropped] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  // Fifty imported lines with one that needs looking at is fifty cards of
  // scrolling to find it. This narrows the list to those, and says how many.
  const [onlyAttention, setOnlyAttention] = useState(false);
  const hasLines = draftLines.some((line) => line.description.trim());

  const updateDraft = (id: number, patch: Partial<DraftLine>) => {
    onDraftChange(draftLines.map((line) => (line.id === id ? { ...line, ...patch } : line)));
  };

  // A toast button is pressed long after the render that created it, so it
  // must not patch the lines as they were then. This ref is what "the lines"
  // means at the moment the user answers.
  const latest = useRef({ draftLines, onDraftChange });
  latest.current = { draftLines, onDraftChange };

  const patchLine = (id: number, patch: Partial<DraftLine>) => {
    const { draftLines: lines, onDraftChange: change } = latest.current;
    change(lines.map((line) => (line.id === id ? { ...line, ...patch } : line)));
  };

  /**
   * The name recognition, answered on the line it is about.
   *
   * It used to be a snackbar: a question that floated at the bottom right of
   * the screen, away from the line it was about, and whose close button was an
   * answer. That last part is what made it wrong. Closing something is not a
   * decision — but the × set ``dg_dismissed``, so "not now" was stored as "not
   * this substance", and the line then showed no trace of the question at all.
   * The decision could not be found again, let alone revised, which the
   * baseline recorded as a task that cannot be completed.
   *
   * Here the question sits under its own line, with three answers spelled out:
   * take the UN number, say it is a different substance, or say the suggestion
   * is wrong. Rejecting one candidate says nothing about whether the goods are
   * dangerous — it says this suggestion is not them — so it touches neither the
   * dangerous-goods tick nor anything the compliance check reads. An answer can
   * be changed afterwards, because the line keeps saying what was answered.
   */
  const answer = (line: DraftLine, patch: Partial<DraftLine>) => updateDraft(line.id, patch);

  // The unit catalogue comes from the backend, so the list is maintained in one
  // place. If that fails, UnitSelect falls back to a text field and the step
  // stays usable.
  const [catalogue, setCatalogue] = useState<UnitCatalogue | null>(null);
  useEffect(() => {
    let alive = true;
    api.unitCatalogue()
      .then((result) => alive && setCatalogue(result))
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, []);

  // What was last worked out per line, and for which text. Kept so that the
  // figures do not blink away on every keystroke; only shown for a line whose
  // own signature has not moved since.
  const computed = useRef(new Map<number, { signature: string; item: LineItem }>());
  if (resultLines && resultLines.length > 0) {
    const next = new Map<number, { signature: string; item: LineItem }>();
    draftLines.forEach((line, index) => {
      const item = resultLines[index];
      if (item) next.set(line.id, { signature: signatureOf(line), item });
    });
    computed.current = next;
  }

  function outcomeFor(line: DraftLine, index: number): { item: LineItem | null; stale: boolean } {
    const fresh = resultLines?.[index];
    if (fresh) return { item: fresh, stale: false };
    const remembered = computed.current.get(line.id);
    if (remembered && remembered.signature === signatureOf(line)) {
      return { item: remembered.item, stale: true };
    }
    return { item: null, stale: true };
  }

  // A new line gets the cursor. Detected here rather than passed in, because
  // adding is the wizard's action and focusing is this panel's business: the
  // one id that was not there a render ago is the one to type in.
  const seen = useRef<number[]>(draftLines.map((line) => line.id));
  const inputs = useRef(new Map<number, HTMLInputElement>());
  useEffect(() => {
    const ids = draftLines.map((line) => line.id);
    const added = ids.filter((id) => !seen.current.includes(id));
    seen.current = ids;
    // Exactly one new line is somebody adding or duplicating one. A handful at
    // once is an import, and an import should not drag the page to its last row.
    if (added.length === 1) {
      const input = inputs.current.get(added[0]);
      input?.focus();
      // jsdom has no layout, so it has no scrollIntoView either.
      input?.scrollIntoView?.({ block: "nearest" });
    }
  }, [draftLines]);

  function onFieldKeyDown(event: React.KeyboardEvent, index: number) {
    if (event.key !== "Enter") return;
    event.preventDefault();
    if (index === draftLines.length - 1) {
      onAddLine();
      return;
    }
    inputs.current.get(draftLines[index + 1].id)?.focus();
  }

  // How the calculation judged the lines, for the summary above the list. A
  // line still being rechecked is neither settled nor a problem yet.
  const { settled, attention, unanswered } = useMemo(() => {
    let settledCount = 0;
    let attentionCount = 0;
    let unansweredCount = 0;
    draftLines.forEach((line, index) => {
      const { item, stale } = outcomeFor(line, index);
      if (!item || stale) return;
      settledCount += 1;
      if (needsAttention(item)) attentionCount += 1;
      if (hasOpenQuestion(line, item)) unansweredCount += 1;
    });
    return { settled: settledCount, attention: attentionCount, unanswered: unansweredCount };
    // outcomeFor reads the refs, which change with the results.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draftLines, resultLines]);

  // Nothing to narrow to any more: leaving the filter on would show an empty
  // list and look like the lines had gone.
  useEffect(() => {
    if (attention + unanswered === 0 && onlyAttention) setOnlyAttention(false);
  }, [attention, unanswered, onlyAttention]);

  const anyStale = useMemo(
    () => draftLines.some((line, index) => outcomeFor(line, index).stale && line.description.trim()),
    // outcomeFor reads the refs, which change with the results.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [draftLines, resultLines],
  );

  return (
    <div
      className={`${panelClass} goods-panel ${dragging ? "ring-2 ring-brand-400" : ""}`}
      onDragOver={onImport ? (event) => {
        if (!event.dataTransfer.types.includes("Files")) return;
        event.preventDefault();
        setDragging(true);
      } : undefined}
      onDragLeave={onImport ? (event) => {
        if (event.currentTarget.contains(event.relatedTarget as Node)) return;
        setDragging(false);
      } : undefined}
      onDrop={onImport ? (event) => {
        const file = event.dataTransfer.files?.[0];
        if (!file) return;
        event.preventDefault();
        setDragging(false);
        setDropped(file);
      } : undefined}
    >
      <div className="border-b border-slate-100 px-4 py-4 dark:border-slate-800 sm:px-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h3 className="text-2xl font-semibold text-slate-900 dark:text-slate-100">{t("review.linesTitle")}</h3>
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{t("review.intro")}</p>
          </div>
          {onImport && (
            <div className="shrink-0">
              <GoodsImport
                initialPaste={initialPaste}
                hasLines={hasLines}
                onImport={onImport}
                dropped={dropped}
                onDroppedHandled={() => setDropped(null)}
              />
            </div>
          )}
        </div>
        {dragging && (
          <p className="mt-2 rounded-lg border border-dashed border-brand-300 bg-brand-50 px-3 py-2 text-xs text-brand-800 dark:border-brand-700 dark:bg-brand-950/40 dark:text-brand-200">
            {t("review.importDrop")}
          </p>
        )}
      </div>

      <div className="p-3 sm:p-4">
        {/* Column names for the row below, on the widths where the row is one
            line. Every control carries its own name for a screen reader, so
            this is the sighted reader's half of the same labelling. */}
        <div className="hidden gap-2 px-2 pb-1 lg:flex">
          <span className="w-6" />
          <span className={`${labelClass} min-w-[14rem] flex-1`}>{t("review.description")}</span>
          <span className={`${labelClass} w-20`}>{t("review.quantity")}</span>
          <span className={`${labelClass} w-32`}>{t("review.unit")}</span>
          <span className={`${labelClass} w-28 text-right`}>{t("review.weightTotal")}</span>
          <span className={`${labelClass} w-28`}>{t("review.status")}</span>
          <span className="w-[7.5rem]" />
        </div>

        {attention + unanswered > 0 && (
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 dark:border-amber-900/50 dark:bg-amber-950/30">
            <span className="text-xs text-amber-900 dark:text-amber-200">
              {t("review.attentionSummary", { ok: settled - attention, attention })}
              {unanswered > 0 && ` · ${t("review.unansweredSummary", { count: unanswered })}`}
            </span>
            <button
              type="button"
              onClick={() => setOnlyAttention((on) => !on)}
              className="rounded-lg border border-amber-300 px-2.5 py-1 text-xs font-medium text-amber-900 dark:border-amber-800 dark:text-amber-200"
            >
              {onlyAttention ? t("review.showAllLines") : t("review.onlyAttention")}
            </button>
          </div>
        )}

        <ul className="space-y-2">
          {draftLines.map((line, index) => {
            const { item, stale } = outcomeFor(line, index);
            if (onlyAttention && !needsAttention(item) && !hasOpenQuestion(line, item)) return null;
            const open = openId === line.id;
            const panelId = `line-panel-${line.id}`;
            return (
              <li
                key={line.id}
                className={`goods-row rounded-xl border px-2 py-2 ${
                  open
                    ? "border-brand-300 dark:border-brand-800"
                    : "border-slate-200 dark:border-slate-700"
                }`}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-slate-100 text-xs font-semibold text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                    {index + 1}
                  </span>
                  <div className="goods-description min-w-0 basis-[14rem] flex-1">
                    <EquipmentCombobox
                      value={line.description}
                      onChange={(value) => updateDraft(line.id, { description: value })}
                      inputRef={(element) => {
                        if (element) inputs.current.set(line.id, element);
                        else inputs.current.delete(line.id);
                      }}
                      onKeyDown={(event) => onFieldKeyDown(event, index)}
                      aria-label={t("review.descriptionOfLine", { number: index + 1 })}
                    />
                  </div>
                  <NumberInput
                    className={`${fieldClass} w-20`}
                    inputMode="decimal"
                    value={line.quantity}
                    aria-label={t("review.quantityOfLine", { number: index + 1 })}
                    onKeyDown={(event) => onFieldKeyDown(event, index)}
                    onChange={(event) =>
                      updateDraft(line.id, {
                        quantity: event.target.value === "" ? "" : Number(event.target.value),
                      })
                    }
                  />
                  <div className="w-32">
                    <UnitSelect
                      value={line.unit}
                      onChange={(unit) => updateDraft(line.id, { unit })}
                      category={item?.material_category}
                      catalogue={catalogue}
                      className={`${fieldClass} w-full`}
                      aria-label={t("review.unitOfLine", { number: index + 1 })}
                    />
                  </div>
                  <div
                    className={`w-28 text-right text-sm tabular-nums ${
                      stale ? "text-slate-400 dark:text-slate-500" : "text-slate-800 dark:text-slate-100"
                    }`}
                  >
                    {item?.weight_total_kg != null ? (
                      <>
                        {item.weight_total_kg}
                        <span className="ml-1 text-xs text-slate-500 dark:text-slate-400">kg</span>
                      </>
                    ) : (
                      <span className="text-slate-400">—</span>
                    )}
                  </div>
                  <div className="w-28">
                    {stale ? (
                      <span className="inline-block rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                        {t("review.toBeRechecked")}
                      </span>
                    ) : item ? (
                      <span className={`inline-block rounded-full px-2 py-0.5 text-xs ${statusColor(item.status)}`}>
                        {t(`status.${item.status}` as "status.ok")}
                      </span>
                    ) : (
                      <span className="text-slate-400">—</span>
                    )}
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
                    <RowAction
                      // A dangerous line has more behind the arrow than a
                      // plain one — its substance — and the button says so
                      // rather than leaving somebody to find out.
                      label={
                        open
                          ? t("review.closeDetails")
                          : isDangerous(line, item)
                            ? t("review.lineDetailsDg")
                            : t("review.lineDetails")
                      }
                      onClick={() => setOpenId(open ? null : line.id)}
                      icon={<DetailsIcon open={open} />}
                      expanded={open}
                      controls={panelId}
                    />
                    <details className="goods-menu relative">
                      <summary className="flex h-11 w-11 cursor-pointer list-none items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800" aria-label={t("review.moreActions")}><span aria-hidden="true">•••</span></summary>
                      <div className="absolute right-0 top-12 z-20 min-w-40 rounded-lg border border-slate-200 bg-white p-1 shadow-lg dark:border-slate-700 dark:bg-slate-900">
                        <button type="button" onClick={(event) => { event.currentTarget.closest("details")?.removeAttribute("open"); onDuplicateLine(line.id); }} className="flex min-h-[44px] w-full items-center gap-2 rounded px-3 text-left text-sm hover:bg-slate-100 dark:hover:bg-slate-800"><CopyIcon />{t("review.duplicateLine")}</button>
                        <button type="button" disabled={!canRemove} onClick={(event) => { event.currentTarget.closest("details")?.removeAttribute("open"); onRemoveLine(line.id); }} className="flex min-h-[44px] w-full items-center gap-2 rounded px-3 text-left text-sm text-red-600 hover:bg-red-50 disabled:opacity-40 dark:text-red-300 dark:hover:bg-red-950"><TrashIcon />{t("review.removeLine")}</button>
                      </div>
                    </details>
                  </div>
                </div>
                <Derived
                  line={line}
                  item={item}
                  stale={stale}
                  translateMessage={translateMessage}
                />
                <SubstanceQuestion line={line} item={item} onAnswer={(patch) => answer(line, patch)} />
                {open && (
                  <LineDetails
                    line={line}
                    result={item}
                    position={index + 1}
                    catalogue={catalogue}
                    id={panelId}
                    onChange={(patch) => updateDraft(line.id, patch)}
                    onWeightChange={
                      onLineWeightChange && item
                        ? (weightField, value) => onLineWeightChange(item.line_id, weightField, value)
                        : undefined
                    }
                  />
                )}
              </li>
            );
          })}
        </ul>

        <button
          type="button"
          onClick={onAddLine}
          className="goods-add mt-3 flex min-h-[48px] w-full items-center justify-center gap-2 rounded-xl border border-dashed border-slate-300 text-sm font-medium text-slate-600 dark:border-slate-700 dark:text-slate-300"
        >
          <PlusIcon />
          {t("review.addLine")}
        </button>
        <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
          {anyStale ? t("review.recheckingHint") : t("review.keyboardHint")}
        </p>
      </div>
    </div>
  );
}

/**
 * The substance question, on the line it is about.
 *
 * Three answers, each said in words. **Take UN 1203** ticks the line as
 * dangerous goods and carries the number to the dangerous goods step. **A
 * different substance** ticks it too but leaves the number to that step, where
 * a substance is actually established. **The suggestion is wrong** rejects the
 * candidate and nothing else: it does not say the goods are safe, and it leaves
 * the dangerous-goods tick exactly as the user left it.
 *
 * An answered line says what was answered, with a way back to the question. A
 * decision you cannot find again is a decision you cannot check.
 */
function SubstanceQuestion({ line, item, onAnswer }: {
  line: DraftLine;
  item: LineItem | null;
  onAnswer: (patch: Partial<DraftLine>) => void;
}) {
  const { t } = useTranslation();
  const candidates = item?.dg_name_candidates ?? [];
  if (candidates.length === 0) return null;
  const decision = decisionOf(line);

  const chip = "rounded-lg border px-2.5 py-1 text-xs font-medium transition-colors";

  if (decision) {
    const said = decision === "confirmed"
      ? t("review.dgAnsweredConfirmed", { un: line.confirmed_un ?? candidates[0].un })
      : decision === "other"
        ? t("review.dgAnsweredOther")
        : t("review.dgAnsweredRejected");
    return (
      <div className="mt-1 flex flex-wrap items-center gap-2 pl-8 pr-2">
        <span className="text-xs text-slate-500 dark:text-slate-400">{said}</span>
        <button
          type="button"
          onClick={() => onAnswer({ dg_decision: undefined, dg_dismissed: undefined, confirmed_un: undefined })}
          className="text-xs font-medium text-brand-700 underline-offset-2 hover:underline dark:text-brand-300"
        >
          {t("review.dgChangeAnswer")}
        </button>
      </div>
    );
  }

  return (
    <div className="mt-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 dark:border-amber-900/50 dark:bg-amber-950/30">
      <p className="text-xs text-amber-900 dark:text-amber-200">
        {candidates.length === 1
          ? t("review.dgAskOne", {
              un: candidates[0].un, class: candidates[0].class, name: candidates[0].name,
            })
          : t("review.dgAskMany")}
      </p>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {candidates.slice(0, 3).map((candidate) => (
          <button
            key={candidate.un}
            type="button"
            onClick={() => onAnswer({
              dangerous_goods: true, confirmed_un: candidate.un, dg_decision: "confirmed",
              dg_dismissed: undefined,
            })}
            className={`${chip} border-amber-300 bg-white text-amber-900 hover:bg-amber-100 dark:border-amber-800 dark:bg-slate-900 dark:text-amber-200`}
            title={candidates.length > 1 ? candidate.name : undefined}
          >
            {t("review.dgTake", { un: candidate.un })}
          </button>
        ))}
        <button
          type="button"
          onClick={() => onAnswer({ dangerous_goods: true, dg_decision: "other", dg_dismissed: undefined })}
          className={`${chip} border-amber-300 text-amber-900 hover:bg-amber-100 dark:border-amber-800 dark:text-amber-200`}
        >
          {t("review.dgOther")}
        </button>
        <button
          type="button"
          onClick={() => onAnswer({ dg_decision: "rejected", dg_dismissed: true })}
          className={`${chip} border-amber-300 text-amber-900 hover:bg-amber-100 dark:border-amber-800 dark:text-amber-200`}
        >
          {t("review.dgWrong")}
        </button>
      </div>
      <p className="mt-1.5 text-[11px] text-amber-800 dark:text-amber-300">{t("review.dgWrongHint")}</p>
    </div>
  );
}

/**
 * Under the row: what was worked out and what is worth knowing about the line,
 * as text rather than as fields. This is where the card's "show more" went —
 * the same facts, without a second tap to reach them.
 */
function Derived({ line, item, stale, translateMessage }: {
  line: DraftLine;
  item: LineItem | null;
  stale: boolean;
  initialPaste?: boolean;
  translateMessage: (msg: string) => string;
}) {
  const { t } = useTranslation();
  const parts: string[] = [];

  const measure = (field: "length_cm" | "width_cm" | "height_cm") => {
    const own = line[field];
    if (own !== undefined && own !== "") return own;
    return item?.[field] ?? null;
  };
  const round = ROUND_TYPES.has(item?.product_type ?? "");
  const length = measure("length_cm");
  const width = measure("width_cm");
  const height = round ? null : measure("height_cm");
  if (length != null || width != null || height != null) {
    const show = (value: number | null) => (value == null ? "?" : String(value));
    parts.push(round
      ? `${show(length)} × ⌀ ${show(width)} cm`
      : `${[length, width, height].map(show).join(" × ")} cm`);
  }
  if (item?.weight_each_kg != null) parts.push(`${item.weight_each_kg} kg/${t("review.each")}`);
  if (item?.transport_volume_m3 != null) parts.push(`${item.transport_volume_m3.toFixed(3)} m³`);
  const form = line.cargo_form ?? item?.cargo_form;
  if (form) parts.push(t(`forms.${form}`, form));
  const type = item?.product_type;
  if (type && WALL_PROFILE_TYPES.has(type) && line.wall_thickness_mm !== undefined && line.wall_thickness_mm !== "") {
    parts.push(`${line.wall_thickness_mm} mm`);
  }

  const messages = item?.messages ?? [];
  const chips = (
    <>
      {item?.dangerous_goods && !line.dangerous_goods && (item.dg_name_candidates?.length ?? 0) === 0 && (
        <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-medium text-amber-800 dark:bg-amber-900/40 dark:text-amber-300">
          {t("review.dgDetected")}
        </span>
      )}
      {line.dangerous_goods && !line.confirmed_un && (
        <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-medium text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300">
          {t("review.dgYes")}
        </span>
      )}
      {line.confirmed_un && (
        <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-medium text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300">
          UN {line.confirmed_un}
        </span>
      )}
      {line.article?.code && (
        <span
          className="rounded-full bg-sky-100 px-2 py-0.5 text-[11px] font-medium text-sky-800 dark:bg-sky-900/40 dark:text-sky-300"
          title={t("articles.onLine")}
        >
          {line.article.code}
        </span>
      )}
    </>
  );

  if (parts.length === 0 && messages.length === 0 && !line.confirmed_un && !line.dangerous_goods
      && !line.article?.code && !item?.dangerous_goods) {
    return null;
  }

  return (
    <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 pl-8 pr-2">
      {parts.length > 0 && (
        <span className={`text-xs ${stale ? "text-slate-400 dark:text-slate-500" : "text-slate-500 dark:text-slate-400"}`}>
          {parts.join(" · ")}
        </span>
      )}
      {chips}
      {messages.length > 0 && (
        <span className="text-xs text-amber-700 dark:text-amber-300">
          {messages.map(translateMessage).join(", ")}
        </span>
      )}
    </div>
  );
}

export function draftToText(lines: DraftLine[]): string {
  return lines
    .filter((l) => l.description.trim())
    .map((l) => `${l.description.trim()} | ${l.quantity || 1} | ${l.unit || "stuks"}`)
    .join("\n");
}

export function textToDraftLines(text: string, startId = 1): DraftLine[] {
  const rows = text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  if (rows.length === 0) return [{ id: startId, description: "", quantity: 1, unit: "stuks" }];
  return rows.map((row, i) => {
    const parts = row.split(/[|\t]/).map((p) => p.trim());
    return {
      id: startId + i,
      description: parts[0] || row,
      quantity: parts[1] ? Number(parts[1]) || 1 : 1,
      unit: parts[2] || "stuks",
    };
  });
}
