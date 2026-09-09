import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { api, AssistantEvent, AssistantPending, AssistantReview, AssistantState } from "../api/client";
import { documentLanguage, localised } from "../i18n/language";
import { ArrowRightIcon, CheckIcon, CloseIcon } from "./icons";
import AiIcon from "./AiIcon";
import { AddressTextarea, LOCATION_FIELD_KEYS, LocationInput, MODALITY_LOCATION_TYPES } from "./GeoInputs";
import "./AssistantModal.css";

type Screen = "describe" | "question" | "ready";
type Action = "answer" | "revise" | "optional" | "add_goods";
interface Snapshot { state: AssistantState; pending: AssistantPending | null; review?: AssistantReview; screen: Screen; answer: string }
interface Props {
  open: boolean;
  onClose: () => void;
  buildState: () => AssistantState;
  onApplyState: (state: AssistantState) => void;
  onReview?: () => void;
  modality?: string;
}
const copy = <T,>(value: T): T => JSON.parse(JSON.stringify(value)) as T;

/** A focused shipment interview, with an inspectable working draft.
 * Successful turns are saved in the ordinary wizard. Failed interpretations
 * keep the original answer. Every history entry is a complete snapshot, and
 * late responses cannot overwrite the wizard after the panel closes.
 */
export default function AssistantModal({ open, onClose, buildState, onApplyState, onReview, modality }: Props) {
  const { t, i18n } = useTranslation();
  const lang = documentLanguage(i18n.language);
  const [pending, setPending] = useState<AssistantPending | null>(null);
  const [working, setWorking] = useState<AssistantState>({});
  const [review, setReview] = useState<AssistantReview>();
  const [history, setHistory] = useState<Snapshot[]>([]);
  const [screen, setScreen] = useState<Screen>("describe");
  const [input, setInput] = useState("");
  const [choice, setChoice] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [showInfo, setShowInfo] = useState(false);
  const dialog = useRef<HTMLDivElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const sequence = useRef(0);
  const inFlight = useRef(false);
  const callbacks = useRef({ buildState, onApplyState, onClose });
  callbacks.current = { buildState, onApplyState, onClose };
  const current = useRef({ working, pending, review, screen, input, choice });
  current.current = { working, pending, review, screen, input, choice };

  const L = (value: unknown) => typeof value === "string" ? value : localised(value as Record<string, string> | undefined, lang);
  const unitLabel = (value: unknown) => t(`units.name.${String(value ?? "pcs")}`, { defaultValue: String(value ?? "pcs") });
  const errorFor = (event: AssistantEvent) => {
    if (event.reason) return t(`assistant.problem.${String(event.reason)}`, { choice: L(event.option_label) || String(event.suggested_choice ?? "") });
    if (event.kind === "not_understood") return t("assistant.notUnderstood");
    return event.example ? t("assistant.clarify", { example: String(event.example) })
      : t("assistant.corrected", { attempt: String(event.attempt ?? "") });
  };

  async function send(message: string, action: Action = "answer", target?: AssistantPending, initial?: AssistantState) {
    if (inFlight.current) return;
    inFlight.current = true;
    const request = ++sequence.current;
    const view = current.current;
    const state = copy(initial ?? view.working);
    const question = target ?? (view.screen === "describe" ? null : view.pending);
    const snapshot: Snapshot = { state, pending: view.pending, review: view.review, screen: view.screen, answer: message };
    setBusy(true);
    setError("");
    try {
      const result = await api.assistantStep({ message, state, pending: question, language: lang, ...(action === "answer" ? {} : { action }) });
      if (sequence.current !== request) return;
      const failure = result.events.find(event => event.kind === "clarify" || event.kind === "not_understood");
      if (failure) {
        setError(errorFor(failure));
        // A stale question is the only failure that requires a new question.
        if (failure.reason === "stale") { setPending(result.pending); setScreen(result.pending?.scope === "goods_intake" ? "describe" : result.pending ? "question" : "ready"); }
        return;
      }
      if (!initial) setHistory(stack => [...stack, snapshot]);
      setWorking(copy(result.state));
      setReview(result.review);
      setPending(result.pending);
      setScreen(result.pending?.scope === "goods_intake" ? "describe" : result.pending ? "question" : "ready");
      if (action !== "revise") callbacks.current.onApplyState(copy(result.state));
      setInput("");
      setChoice("");
      setShowInfo(false);
      const answered = result.events.filter(event => event.kind === "answered");
      const added = result.events.find(event => event.kind === "lines_added");
      setNotice(added ? t("assistant.linesAdded", { count: Number(added.count) })
        : answered.length ? t("assistant.factsUpdated", { count: answered.length })
        : result.events.some(event => event.kind === "un_confirmed") ? t("assistant.unConfirmed", { un: String(result.events.find(e => e.kind === "un_confirmed")?.un) })
        : result.events.some(event => event.kind === "un_dismissed") ? t("assistant.unDismissed") : "");

    } catch {
      if (sequence.current === request) setError(t("assistant.problem.connection"));
    } finally {
      if (sequence.current === request) { inFlight.current = false; setBusy(false); }
    }
  }

  useLayoutEffect(() => {
    if (!open) return;
    const trigger = document.activeElement as HTMLElement | null;
    return () => trigger?.focus();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const before = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const initial = copy(callbacks.current.buildState());
    setWorking(initial); setHistory([]); setPending(null); setReview(undefined);
    setInput(""); setChoice(""); setError(""); setNotice(""); setShowInfo(false); setScreen("describe");
    if (initial.draft_lines?.length) void send("", "answer", undefined, initial);

    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); callbacks.current.onClose(); }
      if (event.key !== "Tab") return;
      const items = Array.from(dialog.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), textarea:not(:disabled), summary, [tabindex="0"]') ?? [])
        .filter(el => !el.closest("details:not([open])") || el.tagName === "SUMMARY");
      const first = items[0], last = items[items.length - 1];
      if (event.shiftKey && (document.activeElement === first || !items.includes(document.activeElement as HTMLElement))) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && (document.activeElement === last || !dialog.current?.contains(document.activeElement))) { event.preventDefault(); first?.focus(); }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      ++sequence.current; inFlight.current = false; setBusy(false);
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = before;
    };
    // A fresh opening deliberately reads the latest manual wizard edits.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  useLayoutEffect(() => {
    if (!open) return;
    // Focus before paint: a delayed focus callback could interrupt someone
    // already typing in the address suggestions of the next question.
    if (screen === "describe") dialog.current?.querySelector<HTMLTextAreaElement>("textarea")?.focus();
    else heading.current?.focus();
  }, [open, screen, pending?.scope, pending?.field, pending?.line_id]);

  function goBack() {
    const snapshot = history[history.length - 1];
    if (!snapshot || busy) return;
    setHistory(stack => stack.slice(0, -1)); setWorking(copy(snapshot.state));
    callbacks.current.onApplyState(copy(snapshot.state)); setPending(snapshot.pending);
    setScreen(snapshot.screen); setReview(snapshot.review); setInput(snapshot.answer);
    setChoice(""); setError(""); setNotice(""); setShowInfo(false);

  }

  if (!open) return null;
  const candidates = (pending?.candidates ?? []) as { un: string; name: string; class: string }[];
  const title = pending?.scope === "un_confirm"
    ? candidates.length === 1 ? t("assistant.unConfirmOne", candidates[0]) : t("assistant.unConfirmMany")
    : pending?.scope === "goods_weight_basis" ? t("assistant.weightBasisQuestion", { weight: pending.weight })
    : pending?.scope === "goods_quantity" ? t("assistant.quantityQuestion", { unit: unitLabel(pending.unit) })
    : L(pending?.simple) || t("assistant.question", { label: L(pending?.label) || pending?.field });
  const options = pending?.scope === "un_confirm"
    ? candidates.length === 1 ? [{ value: "ja", label: t("assistant.yes") }, { value: "nee", label: t("assistant.no") }]
      : [...candidates.map(c => ({ value: `UN ${c.un}`, label: `UN ${c.un} · ${c.name}` })), { value: "nee", label: t("assistant.noneOfThese") }]
    : pending?.scope === "goods_weight_basis" ? [{ value: "total", label: t("assistant.weightTotal") }, { value: "each", label: t("assistant.weightEach") }]
    : (pending?.options ?? []).map(value => ({ value, label: L(pending?.option_labels?.[value]) || value }));
  const answer = input.trim() || choice;
  const field = String(pending?.field ?? "");
  const isAddress = pending?.scope === "doc_question" && field.endsWith("_address");
  const isLocation = pending?.scope === "doc_question" && LOCATION_FIELD_KEYS.has(field);
  const goods = working.draft_lines ?? [];
  const description = goods.map(line => `${line.quantity_unconfirmed ? "?" : line.quantity ?? "?"} ${unitLabel(line.unit)} ${line.description ?? ""}`).join(" · ");
  const info = [L(pending?.label), L(pending?.help)].filter(Boolean).join(" — ");
  const section = screen === "describe" ? 0 : screen === "ready" ? 3 : pending?.scope === "doc_question" ? 2 : 1;
  const facts = review?.facts ?? [];
  const documentFacts = facts.filter(f => f.scope === "doc_question");
  const dgFacts = facts.filter(f => f.scope === "dg_question");
  const edit = (target: AssistantPending) => { void send("", "revise", target); };
  const summary = <div className="assistant-summary-content">
    <p className="assistant-eyebrow">{t("assistant.recorded")}</p>
    {!goods.length && <p className="assistant-empty">{t("assistant.summaryEmpty")}</p>}
    {goods.map(line => <div className="assistant-cargo" key={String(line.id)}>
      <div className="assistant-cargo-title"><span>{String(line.description ?? "")}</span>
        <button type="button" disabled={busy} className="assistant-edit" onClick={() => edit({ scope: "goods_quantity", field: "quantity", line_id: line.id })} aria-label={t("assistant.editQuantity", { goods: String(line.description ?? "") })}>{t("assistant.edit")}</button></div>
      <p>{line.quantity_unconfirmed ? t("assistant.quantityMissing") : `${line.quantity} ${unitLabel(line.unit)}`}</p>
      {line.weight_total_kg != null && <p className="assistant-measure">{Number(line.weight_total_kg).toLocaleString(i18n.language, { maximumFractionDigits: 3 })} kg <span>· {t(line.weight_each_kg != null ? "assistant.statedWeight" : "assistant.calculatedWeight")}</span></p>}
      {line.confirmed_un ? <span className="assistant-un">UN {String(line.confirmed_un)}</span> : null}
    </div>)}
    {documentFacts.length > 0 && <dl className="assistant-facts">{documentFacts.map(fact => <div key={fact.field}>
      <dt>{L(fact.label) || fact.field}</dt><dd><span>{String(fact.value)}</span><button type="button" disabled={busy} className="assistant-edit" aria-label={t("assistant.editField", { field: L(fact.label) || fact.field })} onClick={() => edit(fact)}>{t("assistant.edit")}</button></dd>
    </div>)}</dl>}
    {dgFacts.length > 0 && <details className="assistant-dg-facts"><summary>{t("assistant.dgDetails")}</summary><dl className="assistant-facts">{dgFacts.map((fact, i) => <div key={i}><dt>{L(fact.label) || fact.field}</dt><dd>{String(fact.value)}</dd></div>)}</dl></details>}
    {Boolean(review?.deferred_count) && <p className="assistant-deferred">{t("assistant.deferred", { count: review!.deferred_count })}</p>}
    {!!goods.length && <p className="assistant-saved"><CheckIcon className="h-3.5 w-3.5" />{t("assistant.savedInWizard")}</p>}
  </div>;

  return createPortal(<div className="assistant-backdrop" data-testid="assistant-backdrop" onClick={onClose}>
    <div ref={dialog} role="dialog" aria-modal="true" aria-labelledby="assistant-title" className="assistant-dialog" data-busy={busy} onClick={event => event.stopPropagation()}>
      <header className="assistant-header"><div className="assistant-mark"><AiIcon className="h-7 w-7" /></div><div><h2 id="assistant-title">{t("assistant.title")}</h2><p>{t("assistant.subtitle")}</p></div><button type="button" className="assistant-close" aria-label={t("assistant.close")} onClick={onClose}><CloseIcon className="h-5 w-5" /></button></header>
      <ol className="assistant-stages" aria-label={t("assistant.progress")}>{["brief", "cargo", "details", "review"].map((key, i) => <li key={key} data-active={i === section} data-complete={i < section} aria-current={i === section ? "step" : undefined}><span>{i < section ? <CheckIcon className="h-3 w-3" /> : i + 1}</span>{t(`assistant.stage.${key}`)}</li>)}</ol>
      <div className="assistant-layout">
        <div className="assistant-main">
          <details className="assistant-mobile-summary"><summary>{t("assistant.summary")}<span>{description || t("assistant.summaryEmptyShort")}</span></summary>{summary}</details>
          <div className="assistant-question" key={`${screen}:${pending?.scope}:${pending?.line_id}:${pending?.field}`}>
            {screen === "describe" ? <>
              <p className="assistant-eyebrow">{t("assistant.begin")}</p>
              <h3 ref={heading} tabIndex={-1}>{t("assistant.describeLabel")}</h3>
              <p className="assistant-intro">{t("assistant.describeHint")}</p>
              <label className="sr-only" htmlFor="assistant-description">{t("assistant.describeLabel")}</label>
              <textarea id="assistant-description" className="assistant-input assistant-description" value={input} onChange={e => setInput(e.target.value)} maxLength={4000} placeholder={t("assistant.describePlaceholder")} disabled={busy} aria-describedby={error ? "assistant-error" : "assistant-examples"} />
              <div id="assistant-examples" className="assistant-examples"><span>{t("assistant.tryExample")}</span>{["ordinaryExample", "dgExample"].map(key => <button type="button" key={key} disabled={busy} onClick={() => setInput(t(`assistant.${key}`))}>{t(`assistant.${key}Label`)}</button>)}</div>
            </> : screen === "ready" ? <>
              <div className="assistant-ready-mark"><CheckIcon className="h-7 w-7" /></div>
              <p className="assistant-eyebrow">{t("assistant.readyEyebrow")}</p>
              <h3 ref={heading} tabIndex={-1}>{t("assistant.readyTitle")}</h3><p className="assistant-intro">{t("assistant.ready")}</p>
              {review?.has_dangerous_goods && <p className="assistant-release-note">{t("assistant.dgReviewNotice")}</p>}
              {!!review?.optional_count && !working.include_optional && <button type="button" disabled={busy} className="assistant-optional" onClick={() => void send("", "optional")}>{t("assistant.optionalDetails", { count: review.optional_count })}<ArrowRightIcon className="h-4 w-4" /></button>}
              <button type="button" disabled={busy} className="assistant-text-button" onClick={() => { setScreen("describe"); setPending(null); setInput(""); setError(""); }}>{t("assistant.addGoods")}</button>
            </> : <>
              <div className="assistant-question-meta"><p className="assistant-eyebrow">{t(pending?.scope === "doc_question" ? "assistant.shipmentDetails" : "assistant.yourGoods")}</p><span>{t(pending?.required ? "assistant.required" : "assistant.optional")}</span></div>
              <h3 ref={heading} tabIndex={-1} id="assistant-question-title">{title}</h3>
              {pending?.goods ? <p className="assistant-for-goods">{String(pending.goods)}</p> : null}
              {options.length > 0 && <div className="assistant-options" role="radiogroup" aria-labelledby="assistant-question-title">{options.map(option => <label key={option.value} data-selected={choice === option.value && !input}>
                <input type="radio" name="assistant-choice" value={option.value} checked={choice === option.value && !input} disabled={busy} onChange={() => { setChoice(option.value); setInput(""); }} /><span>{option.label}</span><CheckIcon className="assistant-option-check h-4 w-4" />
              </label>)}</div>}
              <label className="assistant-answer-label" htmlFor="assistant-answer">{t(options.length ? "assistant.orDescribe" : "assistant.yourAnswer")}</label>
              <fieldset disabled={busy} className="assistant-answer-field">
                {isAddress ? <AddressTextarea value={input} onChange={setInput} textareaId="assistant-answer" textareaClassName="assistant-input" />
                  : isLocation ? <LocationInput id="assistant-answer" value={input} onChange={setInput} types={MODALITY_LOCATION_TYPES[modality ?? ""] ?? ["airport", "port", "station"]} className="assistant-input" />
                  : <input id="assistant-answer" className="assistant-input" type="text" inputMode={pending?.scope === "goods_quantity" ? "numeric" : "text"} value={input} onChange={e => { setInput(e.target.value); setChoice(""); }} placeholder={t(pending?.type === "date" ? "assistant.dateExample" : "assistant.answerPlaceholder")} maxLength={4000} aria-invalid={!!error} aria-describedby={error ? "assistant-error" : undefined} onKeyDown={event => { if (event.key === "Enter" && answer) { event.preventDefault(); void send(answer); } }} />}
                {pending?.type === "date" && <input className="assistant-date-picker" type="date" aria-label={t("assistant.chooseDate")} value={/^\d{4}-\d{2}-\d{2}$/.test(input) ? input : ""} onChange={e => setInput(e.target.value)} />}
              </fieldset>
              {info && <button type="button" className="assistant-text-button" onClick={() => setShowInfo(!showInfo)} aria-expanded={showInfo}>{t("assistant.info")}</button>}
              {showInfo && <p className="assistant-help">{info}</p>}
            </>}
            {error && <div id="assistant-error" role="alert" className="assistant-error"><strong>{t("assistant.needsClarification")}</strong><p>{error}</p>{pending?.required && <p>{t("assistant.requiredHelp")}</p>}</div>}
            <div className="assistant-status" role="status" aria-live="polite">{busy ? <span className="assistant-thinking"><AiIcon className="h-4 w-4" />{t("assistant.thinking")}</span> : !error && notice ? <span><CheckIcon className="h-4 w-4" />{notice}</span> : null}</div>
          </div>
        </div>
        <aside className="assistant-summary" aria-label={t("assistant.summary")}><h3>{t("assistant.summary")}</h3>{summary}</aside>
      </div>
      <footer className="assistant-footer"><div className="assistant-footer-left"><button type="button" disabled={busy || !history.length} className="assistant-secondary" onClick={goBack}>{t("assistant.previous")}</button>{screen === "question" && pending?.required === false && <button type="button" disabled={busy} className="assistant-text-button" onClick={() => void send("overslaan")}>{t("assistant.skip")}</button>}</div>
        {screen === "ready" ? <button type="button" disabled={busy} className="assistant-primary" onClick={() => { onClose(); onReview?.(); }}>{t("assistant.done")}<ArrowRightIcon className="h-4 w-4" /></button>
          : <button type="button" disabled={busy || !answer} className="assistant-primary" onClick={() => void send(answer)}>{t(screen === "describe" ? "assistant.start" : "assistant.next")}<ArrowRightIcon className="h-4 w-4" /></button>}
      </footer>
    </div>
  </div>, document.body);
}
