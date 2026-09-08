/**
 * Getting a list of goods in: pasting from Excel, and choosing a file.
 *
 * Both used to live behind one **Importeren** button that opened a dialog, and
 * inside that dialog the file chooser was an icon. The baseline measured the
 * import itself at three actions, which is cheap — but every one of them was
 * spent finding it. Here the two things somebody actually arrives with are on
 * the goods step: a paste area that opens in place, and a file chooser that is
 * a button with a name on it. The panel around the list takes a dropped file
 * as well.
 *
 * **Only asking when there is doubt.** The server says whether it recognised
 * the header row (`analysis.source === "header"`) or guessed the columns from
 * their order. A recognised file is imported straight away; a guessed one shows
 * the column mapping first, which is the one case where the guess can be wrong
 * in a way nobody would notice afterwards.
 *
 * **Add or replace.** A shipment with nothing in it is not asked: there is
 * nothing to replace, so the lines simply go in. Once there are lines, both are
 * offered by name, and whichever is chosen can be undone from the snackbar the
 * wizard raises — which is what makes replacing safe to offer at all.
 */
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, ImportAnalysis, ImportMapping } from "../api/client";
import { useToast } from "../toast/ToastProvider";
import ImportColumnMapping from "./ImportColumnMapping";
import { ImportIcon } from "./icons";

const buttonClass =
  "inline-flex min-h-[44px] shrink-0 items-center gap-2 rounded-lg border border-slate-200 dark:border-slate-700 px-3 text-sm font-medium " +
  "text-slate-700 transition-colors hover:bg-slate-50 disabled:opacity-50 " +
  "dark:text-slate-200 dark:hover:bg-slate-800";
const textareaClass =
  "w-full rounded-xl border border-slate-200 bg-white px-3 py-2 font-mono text-sm " +
  "text-slate-900 focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-500/20 " +
  "dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 min-h-[9rem]";
const primaryClass =
  "rounded-lg bg-brand-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50";
const secondaryClass =
  "rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-700 dark:border-slate-700 dark:text-slate-200";

function PasteIcon() {
  return (
    <svg className="h-4 w-4" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth={1.6} aria-hidden>
      <path d="M8 4H6a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2h-2" strokeLinecap="round" />
      <rect x="8" y="2.5" width="4" height="3" rx="1" />
      <path d="M7.5 10h5M7.5 13h3" strokeLinecap="round" />
    </svg>
  );
}

interface Props {
  /** Whether the shipment already holds a line worth replacing. */
  hasLines: boolean;
  initialPaste?: boolean;
  onImport: (text: string, mode: "append" | "replace") => void;
  /** A file dropped on the goods panel, handed over to be parsed here. */
  dropped?: File | null;
  onDroppedHandled?: () => void;
}

export default function GoodsImport({ hasLines, onImport, dropped, onDroppedHandled, initialPaste = false }: Props) {
  const { t } = useTranslation();
  const toast = useToast();
  const [open, setOpen] = useState(initialPaste);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [analysis, setAnalysis] = useState<ImportAnalysis | null>(null);
  const [rows, setRows] = useState<string[][]>([]);
  const area = useRef<HTMLTextAreaElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const lineCount = text.split(/\r?\n/).filter((line) => line.trim()).length;
  const readRows = rows.length - (analysis?.has_header ? 1 : 0);
  const skipped = rows.length > 0 ? Math.max(0, readRows - lineCount) : 0;

  const close = () => {
    setOpen(false);
    setText("");
    setAnalysis(null);
    setRows([]);
  };

  const takeFile = async (file: File | null) => {
    if (!file) return;
    setBusy(true);
    try {
      const result = await api.parseWizardImportFile(file);
      setText(result.text);
      setAnalysis(result.analysis);
      setRows(result.rows);
      // A recognised header leaves nothing to ask about: an empty shipment
      // takes the lines straight away. With lines already in it the choice
      // between adding and replacing is still the user's.
      if (result.analysis.source === "header" && !hasLines && result.text.trim()) {
        onImport(result.text, "replace");
        close();
        return;
      }
      setOpen(true);
    } catch (e) {
      toast.error(String(e));
    } finally {
      setBusy(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  };

  useEffect(() => {
    if (!dropped) return;
    void takeFile(dropped);
    onDroppedHandled?.();
    // takeFile is recreated every render; the file is what decides.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dropped]);

  const remap = async (mapping: ImportMapping, hasHeader: boolean) => {
    if (rows.length === 0) return;
    setBusy(true);
    try {
      const result = await api.remapWizardImport(rows, mapping, hasHeader);
      setText(result.text);
      setAnalysis(result.analysis);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const startPaste = () => {
    setAnalysis(null);
    setRows([]);
    setOpen(true);
    // The area is not there yet on this render; the effect below focuses it.
  };

  useEffect(() => {
    if (open && !analysis) area.current?.focus();
  }, [open, analysis]);

  const run = (mode: "append" | "replace") => {
    if (!text.trim()) return;
    onImport(text, mode);
    close();
  };

  return (
    <div className="w-full">
      <div className="flex flex-wrap items-center gap-1">
        <button type="button" onClick={startPaste} className={buttonClass} disabled={busy}>
          <PasteIcon />
          {t("review.importPaste")}
        </button>
        <label className={`${buttonClass} cursor-pointer ${busy ? "pointer-events-none opacity-50" : ""}`}>
          <ImportIcon />
          {busy ? t("import.parsingFile") : t("review.importFile")}
          <input
            ref={fileInput}
            type="file"
            accept=".xlsx,.csv,.txt"
            className="sr-only"
            onChange={(event) => void takeFile(event.target.files?.[0] ?? null)}
          />
        </label>
        <button
          type="button"
          onClick={() => void api.downloadWizardTemplate().catch((e) => toast.error(String(e)))}
          className={`${buttonClass} text-slate-500 dark:text-slate-400`}
        >
          {t("import.downloadTemplate")}
        </button>
      </div>

      {open && (
        <div className="mt-3 rounded-xl border border-slate-200 p-3 dark:border-slate-700">
          {analysis && <ImportColumnMapping analysis={analysis} onChange={remap} busy={busy} />}
          <textarea
            ref={area}
            className={`${textareaClass} mt-2`}
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder={t("wizard.paste")}
            aria-label={t("review.importPaste")}
          />
          <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
            {t("review.importRead", { count: lineCount })}
            {skipped > 0 && ` · ${t("review.importSkipped", { count: skipped })}`}
          </p>
          <div className="mt-3 flex flex-wrap justify-end gap-2">
            <button type="button" onClick={close} className={secondaryClass}>
              {t("review.cancel")}
            </button>
            {hasLines ? (
              <>
                <button type="button" onClick={() => run("replace")} disabled={!text.trim() || busy} className={secondaryClass}>
                  {t("review.importReplace")}
                </button>
                <button type="button" onClick={() => run("append")} disabled={!text.trim() || busy} className={primaryClass}>
                  {t("review.importAppend")}
                </button>
              </>
            ) : (
              <button type="button" onClick={() => run("replace")} disabled={!text.trim() || busy} className={primaryClass}>
                {t("review.importConfirm")}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
