import { CloseIcon } from "./icons";
/**
 * The what's-new card: shown once after an update, then never again.
 *
 * A self-hosted container updates silently — the operator pulls a newer image
 * and the next login is a different program with nothing said. This card
 * closes that gap. The rules it lives by:
 *
 * - it compares the *running* version (from the changelog endpoint) with the
 *   `last_seen_version` preference, which travels with the account, so a
 *   second device does not show the same notes twice;
 * - a user without a marker — a fresh account, or one from before this card
 *   existed — sees nothing: their first login is not an update, and showing
 *   159 releases of history would teach everyone to dismiss unread. The
 *   marker is written silently instead;
 * - the entries are the changelog's own text, in English by design (the
 *   repository's language); only the card's chrome is translated;
 * - dismissing *is* the acknowledgement: the marker is saved on close, and a
 *   failure to save just means the card returns next login — never a lost
 *   update note.
 */
import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { api, ChangelogResponse } from "../api/client";
import { usePreferences } from "../settings/preferences";

/** Inline markdown, minimally: bold, italics and code, which is all the
 *  changelog uses. A dependency-grade renderer for three token kinds would be
 *  the heavier mistake. */
export function renderInline(text: string): ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g);
  return parts.map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("*") && part.endsWith("*") && part.length > 2) {
      return <em key={index}>{part.slice(1, -1)}</em>;
    }
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
      return (
        <code key={index} className="rounded bg-slate-100 px-1 font-mono text-[0.85em] dark:bg-slate-800">
          {part.slice(1, -1)}
        </code>
      );
    }
    return part;
  });
}

interface Block {
  kind: "heading" | "item" | "paragraph";
  text: string;
}

/** The changelog's body shapes: `### Added` headings, `- ` list items that
 *  wrap over several lines, and the odd plain paragraph. */
export function parseBlocks(body: string): Block[] {
  const blocks: Block[] = [];
  // Only an unbroken run of lines continues a list item; a blank line ends
  // it, so a paragraph after a list stays a paragraph.
  let continuing = false;
  for (const line of body.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed) {
      continuing = false;
      continue;
    }
    if (trimmed.startsWith("### ")) {
      blocks.push({ kind: "heading", text: trimmed.slice(4) });
      continuing = false;
    } else if (trimmed.startsWith("- ")) {
      blocks.push({ kind: "item", text: trimmed.slice(2) });
      continuing = true;
    } else if (continuing && blocks.length > 0) {
      blocks[blocks.length - 1].text += ` ${trimmed}`;
    } else {
      blocks.push({ kind: "paragraph", text: trimmed });
      continuing = false;
    }
  }
  return blocks;
}

export default function WhatsNewModal() {
  const { t } = useTranslation();
  const { preferences, loaded, save } = usePreferences();
  const [notes, setNotes] = useState<ChangelogResponse | null>(null);
  const [open, setOpen] = useState(false);
  const checked = useRef(false);

  useEffect(() => {
    // Once per page load, and only after the account's own preferences have
    // answered — the cached EMPTY_PREFERENCES would read as "no marker" and
    // silently swallow the notes.
    if (!loaded || checked.current) return;
    checked.current = true;
    let cancelled = false;
    void (async () => {
      const seen = preferences.last_seen_version;
      const log = await api.changelog(seen).catch(() => null);
      if (!log || cancelled || seen === log.version) return;
      if (!seen || log.entries.length === 0) {
        // Nothing to show — a first login, or a changelog with no entries
        // between the versions. Mark quietly so the next update has a floor.
        await save({ ...preferences, last_seen_version: log.version }).catch(() => {});
        return;
      }
      setNotes(log);
      setOpen(true);
    })();
    return () => {
      cancelled = true;
    };
  }, [loaded, preferences, save]);

  if (!open || !notes) return null;

  const dismiss = () => {
    setOpen(false);
    void save({ ...preferences, last_seen_version: notes.version }).catch(() => {});
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={t("whatsNew.title")}
    >
      <div className="flex max-h-[85vh] w-full max-w-xl flex-col rounded-2xl border border-slate-200 bg-white shadow-xl dark:border-slate-700 dark:bg-slate-900">
        <div className="flex items-center gap-2 border-b border-slate-200 p-5 pb-3 dark:border-slate-700">
          <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100">
            {t("whatsNew.title")}
          </h3>
          <button
            type="button"
            onClick={dismiss}
            aria-label={t("whatsNew.close")}
            className="ml-auto rounded-lg px-2 py-1 text-slate-500 hover:bg-slate-100 hover:text-slate-800 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100"
          >
            <CloseIcon className="h-5 w-5" />
          </button>
        </div>
        <div className="overflow-y-auto p-5 pt-3">
          <p className="text-sm text-slate-600 dark:text-slate-300">
            {t("whatsNew.intro", { version: notes.version })}
          </p>
          {notes.entries.map((entry) => (
            <section key={entry.version} className="mt-4">
              <h4 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                {entry.version}
                <span className="ml-2 font-normal text-slate-400 dark:text-slate-500">{entry.date}</span>
              </h4>
              <div className="mt-1 space-y-1.5">
                {parseBlocks(entry.body).map((block, index) =>
                  block.kind === "heading" ? (
                    <p
                      key={index}
                      className="mt-2 text-xs font-medium uppercase tracking-wide text-slate-400 dark:text-slate-500"
                    >
                      {block.text}
                    </p>
                  ) : (
                    <p
                      key={index}
                      className={`text-sm text-slate-700 dark:text-slate-300 ${
                        block.kind === "item" ? "pl-4 -indent-2" : ""
                      }`}
                    >
                      {block.kind === "item" ? <>• </> : null}
                      {renderInline(block.text)}
                    </p>
                  ),
                )}
              </div>
            </section>
          ))}
          {notes.truncated ? (
            <p className="mt-4 text-xs text-slate-500 dark:text-slate-400">{t("whatsNew.truncated")}</p>
          ) : null}
        </div>
        <div className="border-t border-slate-200 p-4 text-right dark:border-slate-700">
          <button
            type="button"
            onClick={dismiss}
            className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-300"
          >
            {t("whatsNew.close")}
          </button>
        </div>
      </div>
    </div>
  );
}
