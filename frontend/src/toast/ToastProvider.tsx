/** The one notification mechanism.
 *
 * Before this existed the application spoke through 87 inline notices in
 * eleven files, four native `confirm()` popups and one hand-built update
 * toast — three visual languages for one sentence: "that worked" (or it did
 * not). This provider replaces the transient half of that.
 *
 * What it does NOT replace is deliberate, and the list is complete as of the
 * audit in v1.159.0, so the next sweep does not have to rediscover it:
 *
 * - **Validation of what the user just supplied**, at the control they used:
 *   a field's own error, and the signature upload refusing a file that is the
 *   wrong type or too large. Told anywhere else, it is detached from which of
 *   several fields it is about.
 * - **Sign-in and password-reset errors**, on their form. The screen is
 *   nearly empty and the eye is already there.
 * - **Regulatory findings**, forever — a carriage prohibition, a compliance
 *   check's outcome, a document warning. A safety warning that slides away
 *   after four seconds is exactly the failure this application is built
 *   against.
 * - **The failure of the compliance check itself**, in the panel rather than
 *   in a toast: it says the findings below are absent rather than clear, and
 *   a notice the user can close would leave an empty panel reading as "all
 *   good". (What makes that safe is elsewhere: changing the input clears the
 *   previous result *before* re-checking, so a failed check never leaves the
 *   old substance's findings standing.)
 * - **The assistant's clarifications**, in its conversation. They are part of
 *   the exchange, not a system event; only a failed request is a toast.
 * - **A load failure that leaves a page unable to render**, in place of the
 *   page.
 *
 * One warning for whoever sweeps next: v1.153.0 matched on the *names* of the
 * state it replaced (`setError`, `setMessage`) and so walked straight past a
 * dialog whose state was called `setFileError` — its failures kept the old
 * visual language for four releases. Search for what renders, not for what it
 * is called.
 *
 * Six kinds, each with its own lifetime:
 *
 * - `success` / `info` dismiss themselves after four seconds;
 * - `error` stays until the user closes it — a missed network error is a
 *   document that silently never went out;
 * - `loading` stays until the caller resolves it into success or error, so a
 *   slow action holds exactly one toast from "working…" to its outcome;
 * - `question` stays until it is answered, because four seconds is not an
 *   answer, and closing it counts as one;
 * - `warning` stays as well: something is wrong and stays wrong until
 *   somebody acts, which is not the same as something having failed.
 *
 * `undoable` is the deferred-action pattern the delete flows use: the UI
 * updates immediately, the real API call fires only when the undo window
 * closes (timer, manual dismiss, or a sixth toast pushing the queue). Undo
 * within the window means the call never happens — which is why a deleted
 * user keeps their password: nothing was deleted yet. A full page reload
 * inside the window abandons the pending call and the item survives; that is
 * the accepted edge of the pattern, preferred over deleting behind the
 * user's back on their way out.
 *
 * Self-built rather than a dependency: the frontend carries five runtime
 * dependencies by policy, and this is ~150 lines of behaviour we can pin
 * with tests of our own.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactElement,
  type ReactNode,
} from "react";
import { useTranslation } from "react-i18next";
import { ErrorIcon } from "../components/icons";
import {
  CheckIcon,
  CircleXmarkIcon,
  ExclamationIcon,
  InfoIcon,
  QuestionIcon,
  SpinnerIcon,
} from "./icons";

export type ToastKind = "success" | "info" | "error" | "loading" | "question" | "warning";

export interface ToastAction {
  label: string;
  run: () => void;
}

export interface Toast {
  id: number;
  kind: ToastKind;
  message: string;
  /**
   * Buttons in the toast: the undo, or an answer to a question.
   *
   * Several of them because a question can have several right answers — two
   * sulphuric acids differing only in their qualifier are one recognition
   * with two UN numbers, and picking between them is the whole point.
   */
  actions?: ToastAction[];
  /** For undoable toasts: what to do when the window closes unused. */
  onExpire?: () => void;
  /** Fires only on the explicit × — not on timeout or eviction. The update
   * notice uses this to remember "seen" per version: being pushed out by
   * other toasts is not the admin saying they read it. */
  onDismiss?: () => void;
  /** Info toasts that must not auto-dismiss (the update notice). */
  sticky?: boolean;
}

interface UndoableOptions {
  /** Fires when the undo window closes without the undo being taken —
   * this is where the real API call lives. */
  execute: () => void;
  /** Fires when the user clicks undo — restore the optimistic UI. */
  restore: () => void;
  label?: string;
}

export interface ToastApi {
  success: (message: string) => number;
  info: (
    message: string,
    options?: { sticky?: boolean; actions?: ToastAction[]; onDismiss?: () => void },
  ) => number;
  error: (message: string) => number;
  /**
   * A question the user has to answer, with the answers as buttons.
   *
   * Always stays: a question that slides away after four seconds has not been
   * asked. Closing it with the × is itself an answer — "no" — which is what
   * `onDismiss` is for.
   */
  ask: (message: string, options: { actions: ToastAction[]; onDismiss?: () => void }) => number;
  /**
   * Something is wrong and stays wrong until someone acts — a policy this
   * account does not meet, say. Amber rather than red: nothing failed, and
   * nothing is broken. Sticky, because a warning that leaves on its own has
   * not warned anybody.
   */
  warn: (
    message: string,
    options?: { actions?: ToastAction[]; onDismiss?: () => void },
  ) => number;
  /** Returns a handle that resolves the loading toast into its outcome.
   * `progress` rewrites the message while still loading — one toast follows
   * a multi-phase action (pulling the image, restarting) instead of a new
   * toast per phase. */
  loading: (message: string) => {
    id: number;
    progress: (message: string) => void;
    success: (message: string) => void;
    error: (message: string) => void;
  };
  undoable: (message: string, options: UndoableOptions) => number;
  dismiss: (id: number) => void;
}

const AUTO_DISMISS_MS = 4000;
export const UNDO_WINDOW_MS = 6000;
/** More than this and the oldest dismissable one is closed first: a stack of
 * stale confirmations buries the one the user is looking for. */
const MAX_VISIBLE = 5;

const ToastContext = createContext<ToastApi | null>(null);

export function useToast(): ToastApi {
  const api = useContext(ToastContext);
  if (!api) throw new Error("useToast outside ToastProvider");
  return api;
}

let nextId = 1;

export function ToastProvider({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const [toasts, setToasts] = useState<Toast[]>([]);
  // Timers live outside state: a re-render must not reset a running window.
  const timers = useRef(new Map<number, {
    handle?: ReturnType<typeof setTimeout>;
    deadline: number;
    remaining: number | null;
    paused: Set<"pointer" | "focus">;
  }>());

  useEffect(() => () => {
    timers.current.forEach((timer) => clearTimeout(timer.handle));
    timers.current.clear();
  }, []);

  const remove = useCallback((id: number, reason: "undo" | "timeout" | "dismiss") => {
    const timer = timers.current.get(id);
    if (timer) clearTimeout(timer.handle);
    timers.current.delete(id);
    setToasts((current) => {
      const found = current.find((toast) => toast.id === id);
      // Closing an undoable toast in any way except the undo button means
      // "I don't need the undo": the deferred action fires now rather than
      // silently never.
      if (reason !== "undo") found?.onExpire?.();
      if (reason === "dismiss") found?.onDismiss?.();
      return current.filter((toast) => toast.id !== id);
    });
  }, []);

  const schedule = useCallback((id: number, lifetimeMs: number | null) => {
    const previous = timers.current.get(id);
    clearTimeout(previous?.handle);
    // Loading and persistent notices also retain pointer/focus state, so a
    // loading notice that finishes under the pointer stays readable.
    const timer = { remaining: lifetimeMs, deadline: Date.now() + (lifetimeMs ?? 0),
      paused: previous?.paused ?? new Set<"pointer" | "focus">(), handle: undefined as ReturnType<typeof setTimeout> | undefined };
    if (lifetimeMs !== null && !timer.paused.size) timer.handle = setTimeout(() => remove(id, "timeout"), lifetimeMs);
    timers.current.set(id, timer);
  }, [remove]);

  const pause = useCallback((id: number, cause: "pointer" | "focus", active: boolean) => {
    const timer = timers.current.get(id);
    if (!timer) return;
    if (active) {
      if (!timer.paused.size && timer.remaining !== null) {
        timer.remaining = Math.max(0, timer.deadline - Date.now());
        clearTimeout(timer.handle);
      }
      timer.paused.add(cause);
    } else if (timer.paused.delete(cause) && !timer.paused.size && timer.remaining !== null) {
      timer.deadline = Date.now() + timer.remaining;
      timer.handle = setTimeout(() => remove(id, "timeout"), timer.remaining);
    }
  }, [remove]);

  const push = useCallback(
    (toast: Omit<Toast, "id">, lifetimeMs: number | null) => {
      const id = nextId++;
      setToasts((current) => {
        const next = [...current, { ...toast, id }];
        if (next.length > MAX_VISIBLE) {
          // A loading toast is a promise to the user and only its own outcome
          // may close it, so it is never the one that gives way.
          const evictable = next.filter((candidate) => candidate.kind !== "loading");
          // Transient confirmations give way before anything that stays on
          // purpose. A sticky toast is either a question waiting for an answer
          // or a notice meant to be read; pushing one of those out to make
          // room for "saved" loses the more important of the two.
          const oldest =
            evictable.find((candidate) => !candidate.sticky) ?? evictable[0];
          if (oldest) {
            // Deferred actions still fire — being pushed out of view must not
            // cancel a delete the user asked for.
            oldest.onExpire?.();
            const timer = timers.current.get(oldest.id);
            if (timer) clearTimeout(timer.handle);
            timers.current.delete(oldest.id);
            return next.filter((candidate) => candidate.id !== oldest.id);
          }
        }
        return next;
      });
      schedule(id, lifetimeMs);
      return id;
    },
    [schedule],
  );

  const api = useMemo<ToastApi>(() => {
    const update = (id: number, patch: Partial<Toast>, lifetimeMs: number | null) => {
      setToasts((current) =>
        current.map((toast) => (toast.id === id ? { ...toast, ...patch } : toast)),
      );
      schedule(id, lifetimeMs);
    };
    return {
      success: (message) => push({ kind: "success", message }, AUTO_DISMISS_MS),
      info: (message, options) =>
        push(
          {
            kind: "info",
            message,
            sticky: options?.sticky,
            actions: options?.actions,
            onDismiss: options?.onDismiss,
          },
          options?.sticky ? null : AUTO_DISMISS_MS,
        ),
      error: (message) => push({ kind: "error", message }, null),
      ask: (message, { actions, onDismiss }) =>
        push({ kind: "question", message, sticky: true, actions, onDismiss }, null),
      warn: (message, options) =>
        push(
          {
            kind: "warning",
            message,
            sticky: true,
            actions: options?.actions,
            onDismiss: options?.onDismiss,
          },
          null,
        ),
      loading: (message) => {
        const id = push({ kind: "loading", message }, null);
        return {
          id,
          progress: (next: string) => update(id, { message: next }, null),
          success: (outcome: string) =>
            update(id, { kind: "success", message: outcome }, AUTO_DISMISS_MS),
          error: (outcome: string) => update(id, { kind: "error", message: outcome }, null),
        };
      },
      undoable: (message, { execute, restore, label }) => {
        let done = false;
        const once = (fn: () => void) => () => {
          if (done) return;
          done = true;
          fn();
        };
        const id: number = push(
          {
            kind: "info",
            message,
            onExpire: once(execute),
            actions: [
              {
                label: label ?? t("toast.undo"),
                run: once(() => {
                  restore();
                  remove(id, "undo");
                }),
              },
            ],
          },
          UNDO_WINDOW_MS,
        );
        return id;
      },
      dismiss: (id) => remove(id, "dismiss"),
    };
  }, [push, remove, schedule, t]);

  return (
    <ToastContext.Provider value={api}>
      {children}
      <ToastHost toasts={toasts} onDismiss={(id) => remove(id, "dismiss")} onPause={pause} />
    </ToastContext.Provider>
  );
}

const KIND_ICON: Record<ToastKind, (props: { className?: string }) => ReactElement> = {
  success: CheckIcon,
  info: InfoIcon,
  error: ErrorIcon,
  loading: SpinnerIcon,
  question: QuestionIcon,
  warning: ExclamationIcon,
};

/** Up to this many characters a single action sits beside the message, the
 *  way "Undo" always has. Past it the message wraps into a column, and a
 *  button floating top-right beside five lines of text — squeezing them
 *  narrower still — looks like a layout accident; the action goes under the
 *  text instead, where a question's answers already are. A character count
 *  rather than measuring the wrap, because it must render the same on the
 *  first paint and in a test. */
export const INLINE_ACTION_MAX_CHARS = 60;

/** And the action's own label has to be short, which the rule above forgot.
 *  An inline action does not wrap: it takes whatever width its words need and
 *  the message gets the rest. Beside "Bekijk de release-opmerkingen" on a
 *  390px phone, the rest is about 135px — a message broken mid-word, four
 *  characters to a line.
 *
 *  Sixteen is measured rather than picked. The labels that are commands come
 *  out at 4 to 16 characters in the four languages — *Undo*, *Ongedaan
 *  maken*, *Jetzt einrichten* — and the ones that are sentences at 22 to 29.
 *  The gap between them is where this sits. */
export const INLINE_ACTION_MAX_LABEL = 16;

function ToastHost({ toasts, onDismiss, onPause }: {
  toasts: Toast[];
  onDismiss: (id: number) => void;
  onPause: (id: number, cause: "pointer" | "focus", active: boolean) => void;
}) {
  const { t } = useTranslation();
  if (toasts.length === 0) return null;
  return (
    // Bottom sheet on mobile, bottom-right stack on desktop. Errors announce
    // assertively; the rest waits its turn — a screen reader user saving a
    // form should not be interrupted mid-sentence for "saved".
    <div className="toast-stack">
      {toasts.map((toast) => {
        const Icon = KIND_ICON[toast.kind];
        const actions = toast.actions ?? [];
        const inline =
          actions.length === 1 &&
          toast.message.length <= INLINE_ACTION_MAX_CHARS &&
          actions[0].label.length <= INLINE_ACTION_MAX_LABEL;
        const below = actions.length > 0 && !inline;
        // The row is top-aligned, and the kind icon is the one thing that is
        // not: it marks what sort of notice this is, so it belongs against the
        // whole message rather than against its first line, which shows as
        // soon as the text wraps. The close button stays in the corner where a
        // close button belongs, however tall the toast grows.
        return (
          <div
            key={toast.id}
            role={toast.kind === "error" ? "alert" : "status"}
            aria-live={toast.kind === "error" ? "assertive" : "polite"}
            className={`toast-message toast-${toast.kind}`}
            data-kind={toast.kind}
            onPointerEnter={() => onPause(toast.id, "pointer", true)}
            onPointerLeave={() => onPause(toast.id, "pointer", false)}
            onFocusCapture={() => onPause(toast.id, "focus", true)}
            onBlurCapture={(event) => {
              if (!event.currentTarget.contains(event.relatedTarget as Node | null)) onPause(toast.id, "focus", false);
            }}
          >
            <Icon
              className={`toast-icon h-5 w-5 shrink-0 ${toast.kind === "loading" ? "animate-spin" : ""}`}
            />
            {/* A question puts its answers under the text rather than beside
                it: two or three UN numbers on one line squeeze the sentence
                that says what is being asked. One short answer still sits
                alongside, where "Undo" has always been; one answer to a long
                message goes under it too, see INLINE_ACTION_MAX_CHARS. */}
            <div className={`min-w-0 flex-1 ${below ? "space-y-2" : ""}`}>
              <span className="block break-words">{toast.message}</span>
              {below && (
                <div className="flex flex-wrap gap-1.5" data-testid="toast-actions">
                  {actions.map((action) => (
                    <button
                      key={action.label}
                      type="button"
                      onClick={action.run}
                      className="rounded-md border border-current px-2.5 py-1 text-xs font-semibold hover:opacity-75"
                    >
                      {action.label}
                    </button>
                  ))}
                </div>
              )}
            </div>
            {inline && (
              <button
                type="button"
                onClick={actions[0].run}
                className="shrink-0 rounded-md px-2 py-0.5 font-semibold underline decoration-2 underline-offset-2 hover:opacity-75"
              >
                {actions[0].label}
              </button>
            )}
            {toast.kind !== "loading" && (
              <button
                type="button"
                onClick={() => onDismiss(toast.id)}
                aria-label={t("toast.dismiss")}
                className="toast-dismiss"
              >
                <CircleXmarkIcon className="h-4 w-4" />
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}
