import { CloseIcon } from "./icons";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, AssistantEvent, AssistantPending, AssistantState } from "../api/client";
import { documentLanguage, localised } from "../i18n/language";
import { useToast } from "../toast/ToastProvider";
import AiIcon from "./AiIcon";
import {
  AddressTextarea,
  LOCATION_FIELD_KEYS,
  LocationInput,
  MODALITY_LOCATION_TYPES,
} from "./GeoInputs";

interface Snapshot {
  state: AssistantState;
  pending: AssistantPending | null;
}

interface Props {
  open: boolean;
  onClose: () => void;
  /** The wizard state as the assistant sees it; built by the wizard page. */
  buildState: () => AssistantState;
  /** The patched state coming back; the wizard page maps it onto its own. */
  onApplyState: (state: AssistantState) => void;
  /** Transport mode, deciding which locations are suggested (✈/⚓/🚆). */
  modality?: string;
}

/** The assistant as a survey in a modal: one question per screen, a previous
 *  button that really goes back, and no chat transcript.
 *
 * Every question is still a translation of something the backend produced —
 * a substance the name recognition offered, an open question `dg/prepare`
 * named, a document field the registry requires. Going back restores the
 *  snapshot taken before that answer was applied: the server is stateless,
 *  so the history is the client's to keep, and re-answering a question is
 *  simply replaying from an earlier state.
 */
export default function AssistantModal({ open, onClose, buildState, onApplyState, modality }: Props) {
  const { t, i18n } = useTranslation();
  const lang = documentLanguage(i18n.language);
  const [pending, setPending] = useState<AssistantPending | null>(null);
  const [history, setHistory] = useState<Snapshot[]>([]);
  const [screen, setScreen] = useState<"describe" | "question" | "ready">("describe");
  const [describe, setDescribe] = useState("");
  const [choice, setChoice] = useState("");
  const [freeText, setFreeText] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [showInfo, setShowInfo] = useState(false);
  const toast = useToast();

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const noticeFor = (events: AssistantEvent[]): string => {
    const lines: string[] = [];
    for (const event of events) {
      if (event.kind === "lines_added") {
        lines.push(t("assistant.linesAdded", { count: Number(event.count ?? 0) }));
      }
      if (event.kind === "un_confirmed") {
        lines.push(t("assistant.unConfirmed", { un: String(event.un ?? "") }));
      }
      if (event.kind === "un_dismissed") lines.push(t("assistant.unDismissed"));
    }
    return lines.join(" ");
  };

  const send = async (message: string) => {
    if (busy) return;
    setBusy(true);
    setError("");
    const snapshot: Snapshot = { state: buildState(), pending };
    try {
      const result = await api.assistantStep({
        message,
        state: snapshot.state,
        pending,
        language: lang,
      });
      const clarify = result.events.find((event) => event.kind === "clarify");
      const misunderstood = result.events.some((event) => event.kind === "not_understood");
      if (clarify) {
        // A correction or a follow-up: nothing was written, the question
        // stays — with either what was tried or an example of a full answer.
        setError(
          clarify.example
            ? t("assistant.clarify", { example: String(clarify.example) })
            : t("assistant.corrected", { attempt: String(clarify.attempt ?? "") }),
        );
      } else if (misunderstood) {
        setError(t("assistant.notUnderstood"));
      } else {
        setHistory((stack) => [...stack, snapshot]);
        onApplyState(result.state);
        setNotice(noticeFor(result.events));
      }
      setPending(result.pending ?? null);
      setScreen(result.pending ? "question" : "ready");
      setChoice("");
      setFreeText("");
      setShowInfo(false);
    } catch (e) {
      // Unlike a clarification — which is part of the conversation and stays
      // at the question — a failed request is a system event: toast.
      toast.error(String(e));
    } finally {
      setBusy(false);
    }
  };

  const goBack = () => {
    const previous = history[history.length - 1];
    if (!previous) return;
    setHistory((stack) => stack.slice(0, -1));
    onApplyState(previous.state);
    setPending(previous.pending);
    setScreen(previous.pending ? "question" : "describe");
    setNotice("");
    setError("");
    setChoice("");
    setFreeText("");
    setShowInfo(false);
  };

  const questionTitle = (): string => {
    if (!pending) return "";
    if (pending.scope === "un_confirm") {
      const candidates = (pending.candidates ?? []) as {
        un: string; name: string; class: string;
      }[];
      if (candidates.length === 1) {
        const c = candidates[0];
        return t("assistant.unConfirmOne", { un: c.un, name: c.name, class: c.class });
      }
      return t("assistant.unConfirmMany");
    }
    // The lay phrasing first — a question a first-time consignor understands.
    // The formal label stays behind the info mark, next to the help text.
    const simple = localised(pending.simple as Record<string, string> | undefined, lang);
    if (simple) return simple;
    const label =
      localised(pending.label as Record<string, string> | undefined, lang) ||
      String(pending.field ?? "");
    return t("assistant.question", { label });
  };

  /** The formal label and the help with its article references, shown when
   *  the info mark is open. */
  const infoText = (): string => {
    if (!pending || pending.scope === "un_confirm") return "";
    const label =
      typeof pending.label === "string"
        ? pending.label
        : localised(pending.label as Record<string, string> | undefined, lang);
    const help =
      typeof pending.help === "string"
        ? pending.help
        : localised(pending.help as Record<string, string> | undefined, lang);
    return [label, help].filter(Boolean).join(" — ");
  };

  const questionReason = (): string => {
    const key = `dgopen.${String(pending?.reason ?? "")}`;
    if (!pending?.reason) return "";
    const text = t(key as "dgopen.sp274");
    return text === key ? "" : text;
  };

  /** The selectable answers of the current question, as value/label pairs. */
  const answerOptions = (): { value: string; label: string }[] => {
    if (!pending) return [];
    if (pending.scope === "un_confirm") {
      const candidates = (pending.candidates ?? []) as {
        un: string; name: string; class: string;
      }[];
      if (candidates.length === 1) {
        return [
          { value: "ja", label: t("assistant.yes") },
          { value: "nee", label: t("assistant.no") },
        ];
      }
      return [
        ...candidates.map((c) => ({
          value: `UN ${c.un}`,
          label: `UN ${c.un} — ${c.name.slice(0, 60)}`,
        })),
        { value: "nee", label: t("assistant.noneOfThese") },
      ];
    }
    const labels = (pending.option_labels ?? {}) as Record<string, unknown>;
    return (pending.options ?? []).map((option) => {
      const label = labels[option];
      return {
        value: option,
        label:
          (label && typeof label === "object"
            ? localised(label as Record<string, string>, lang)
            : (label as string)) || option,
      };
    });
  };

  const options = answerOptions();
  const answer = options.length > 0 ? choice : freeText.trim();
  const skippable = pending?.scope !== "un_confirm" && pending?.required === false;

  // Address and location questions get the same suggestions the wizard's own
  // fields have: addresses from the address API, and airports, ports and
  // stations from the location catalogue — filtered by the transport mode.
  const docField = String(pending?.field ?? "");
  const isAddressField =
    pending?.scope === "doc_question" && pending?.type === "textarea" && docField.endsWith("_address");
  const isLocationField = pending?.scope === "doc_question" && LOCATION_FIELD_KEYS.has(docField);
  const locationTypes = MODALITY_LOCATION_TYPES[modality ?? ""] ?? ["airport", "port", "station"];

  const submit = () => {
    if (screen === "describe") {
      if (describe.trim()) void send(describe.trim());
      return;
    }
    if (answer) void send(answer);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
      data-testid="assistant-backdrop"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={t("assistant.title")}
        className="w-full max-w-lg rounded-2xl border border-slate-200 bg-white p-5 shadow-xl dark:border-slate-700 dark:bg-slate-900"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center gap-2">
          <AiIcon className="h-6 w-6 text-slate-900 dark:text-slate-100" />
          <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100">
            {t("assistant.title")}
          </h3>
          <button
            type="button"
            onClick={onClose}
            aria-label={t("assistant.close")}
            className="ml-auto rounded-lg px-2 py-1 text-slate-500 hover:bg-slate-100 hover:text-slate-800 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100"
          >
            <CloseIcon className="h-5 w-5" />
          </button>
        </div>

        {notice && (
          <p className="mt-3 rounded-lg bg-emerald-50 px-3 py-2 text-xs text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300">
            {notice}
          </p>
        )}

        {screen === "describe" && (
          <div className="mt-4 space-y-3">
            <label
              htmlFor="assistant-describe"
              className="text-sm font-medium text-slate-800 dark:text-slate-200"
            >
              {t("assistant.describeLabel")}
            </label>
            <textarea
              id="assistant-describe"
              className="min-h-[80px] w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
              placeholder={t("assistant.describePlaceholder")}
              value={describe}
              onChange={(event) => setDescribe(event.target.value)}
            />
            <p className="text-xs text-slate-500 dark:text-slate-400">{t("assistant.describeHint")}</p>
          </div>
        )}

        {screen === "question" && pending && (
          <div className="mt-4 space-y-3">
            {typeof pending.goods === "string" && pending.goods && (
              <p className="text-xs font-medium uppercase tracking-wide text-slate-400 dark:text-slate-500">
                {pending.goods}
              </p>
            )}
            <div className="flex items-start gap-2">
              <p className="text-sm font-medium text-slate-900 dark:text-slate-100">{questionTitle()}</p>
              {infoText() && (
                <button
                  type="button"
                  onClick={() => setShowInfo((value) => !value)}
                  aria-label={t("assistant.info")}
                  aria-expanded={showInfo}
                  className="mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-slate-300 text-[11px] font-semibold text-slate-500 hover:border-slate-400 hover:text-slate-700 dark:border-slate-600 dark:text-slate-400 dark:hover:text-slate-200"
                >
                  i
                </button>
              )}
            </div>
            {showInfo && infoText() && (
              <p className="rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                {infoText()}
              </p>
            )}
            {questionReason() && (
              <p className="text-xs text-slate-500 dark:text-slate-400">{questionReason()}</p>
            )}
            {options.length > 0 ? (
              <div className="space-y-1.5" role="radiogroup" aria-label={questionTitle()}>
                {options.map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    role="radio"
                    aria-checked={choice === option.value}
                    onClick={() => setChoice(option.value)}
                    className={`block w-full rounded-lg border px-3 py-2 text-left text-sm transition ${
                      choice === option.value
                        ? "border-brand-500 bg-brand-50 text-brand-800 ring-1 ring-brand-500 dark:bg-brand-950/50 dark:text-brand-200"
                        : "border-slate-200 text-slate-700 hover:border-slate-300 dark:border-slate-700 dark:text-slate-200 dark:hover:border-slate-600"
                    }`}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            ) : isAddressField ? (
              <AddressTextarea
                value={freeText}
                onChange={setFreeText}
                textareaClassName="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 min-h-[64px]"
              />
            ) : isLocationField ? (
              <LocationInput
                value={freeText}
                onChange={setFreeText}
                types={locationTypes}
                includeAddresses={modality === "road" || modality === "multimodal"}
              />
            ) : pending.type === "date" ? (
              <input
                type="date"
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
                value={freeText}
                onChange={(event) => setFreeText(event.target.value)}
              />
            ) : (
              <input
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
                value={freeText}
                placeholder={t("assistant.answerPlaceholder")}
                onChange={(event) => setFreeText(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") submit();
                }}
              />
            )}
          </div>
        )}

        {screen === "ready" && (
          <p className="mt-4 rounded-lg bg-emerald-50 px-3 py-3 text-sm text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300">
            {t("assistant.ready")}
          </p>
        )}

        {error && <p className="mt-3 text-sm text-red-600 dark:text-red-400">{error}</p>}

        <div className="mt-5 flex items-center gap-2">
          <button
            type="button"
            onClick={goBack}
            disabled={busy || history.length === 0}
            className="rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-40 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            {t("assistant.previous")}
          </button>
          {skippable && screen === "question" && (
            <button
              type="button"
              onClick={() => void send("skip")}
              disabled={busy}
              className="rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
            >
              {t("assistant.skip")}
            </button>
          )}
          {screen === "ready" ? (
            <button
              type="button"
              onClick={onClose}
              className="ml-auto rounded-lg bg-brand-600 px-5 py-2 text-sm font-medium text-white hover:bg-brand-700"
            >
              {t("assistant.done")}
            </button>
          ) : (
            <button
              type="button"
              onClick={submit}
              disabled={busy || (screen === "describe" ? !describe.trim() : !answer)}
              className="ml-auto rounded-lg bg-brand-600 px-5 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
            >
              {screen === "describe" ? t("assistant.start") : t("assistant.next")}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
