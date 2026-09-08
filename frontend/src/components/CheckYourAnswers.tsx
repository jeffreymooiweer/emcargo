/**
 * The last look before the documents are made: what EMCargo is about to
 * put on paper, in the words the user gave it.
 *
 * The export step used to open with a form — total weight, a weight per line —
 * and the summary of the shipment was scattered over the panels below it. What
 * a person needs here is not another field but the answer to *is this right?*,
 * with one way back to each thing that is not.
 *
 * A row whose answer is missing says so rather than showing an empty space,
 * because "nothing there" and "nothing needed" look identical otherwise.
 */
import { useTranslation } from "react-i18next";

export interface AnswerRow {
  key: string;
  label: string;
  /** The answer as it stands. Empty means nothing was given. */
  value: string;
  /** Where to go to change it. A row without one is not something to change
   *  here — a derived figure, or an assessment. */
  onChange?: () => void;
  /** Whether an empty value is a problem worth colouring. */
  wanted?: boolean;
}

interface Props {
  rows: AnswerRow[];
  title: string;
}

export default function CheckYourAnswers({ rows, title }: Props) {
  const { t } = useTranslation();
  return (
    <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-4 sm:p-6">
      <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100">{title}</h3>
      <dl className="mt-3 divide-y divide-slate-100 dark:divide-slate-800">
        {rows.map((row) => (
          <div key={row.key} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 py-2">
            <dt className="w-full text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400 sm:w-48 sm:shrink-0">
              {row.label}
            </dt>
            <dd
              className={`min-w-0 flex-1 text-sm ${
                row.value
                  ? "text-slate-900 dark:text-slate-100"
                  : row.wanted
                    ? "text-amber-700 dark:text-amber-300"
                    : "text-slate-500 dark:text-slate-400"
              }`}
            >
              {row.value || t("check.nothingGiven")}
            </dd>
            {row.onChange && (
              <button
                type="button"
                onClick={row.onChange}
                className="text-xs font-medium text-brand-700 underline hover:text-brand-800 dark:text-brand-300"
              >
                {t("check.change")}
                <span className="sr-only"> — {row.label}</span>
              </button>
            )}
          </div>
        ))}
      </dl>
    </div>
  );
}
