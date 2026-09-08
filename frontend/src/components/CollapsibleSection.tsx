import { ReactNode } from "react";
import { ChevronDownIcon } from "./icons";

/** A collapsible card with a summary line that is always visible.
 *
 * The dangerous goods step shows many findings at once; everything expanded is
 * unreadable, hiding everything is more dangerous. The compromise: the heading
 * carries the outcome (status chips, counts) and stays in view, while the
 * substantiation opens when the user needs it. Whatever is red should be open by
 * default — the caller decides that with `defaultOpen`.
 */
export default function CollapsibleSection({
  title,
  chips,
  defaultOpen = false,
  children,
}: {
  title: ReactNode;
  chips?: ReactNode;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  return (
    <details
      open={defaultOpen}
      className="disclosure group rounded-xl border border-slate-200 dark:border-slate-800"
    >
      <summary className="flex cursor-pointer select-none list-none flex-wrap items-center gap-2 rounded-xl px-3 py-2.5 hover:bg-slate-50 dark:hover:bg-slate-800/50 [&::-webkit-details-marker]:hidden">
        <ChevronDownIcon className="h-4 w-4 shrink-0 text-slate-400 -rotate-90 transition-transform group-open:rotate-0" />
        <span className="text-sm font-semibold text-slate-900 dark:text-slate-100">{title}</span>
        {chips}
      </summary>
      <div className="space-y-2 border-t border-slate-100 px-3 pb-3 pt-2.5 dark:border-slate-800">
        {children}
      </div>
    </details>
  );
}

export function SummaryChip({
  className = "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${className}`}>
      {children}
    </span>
  );
}
