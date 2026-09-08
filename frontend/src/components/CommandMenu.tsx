import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { useTranslation } from "react-i18next";

interface Destination { to: string; label: string }

/** A local navigation index; it never searches or exposes another user's data. */
export default function CommandMenu({ destinations }: { destinations: Destination[] }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const dialog = useRef<HTMLDialogElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const [query, setQuery] = useState("");
  const filtered = destinations.filter(item => item.label.toLocaleLowerCase().includes(query.toLocaleLowerCase()));
  function open() { setQuery(""); dialog.current?.showModal(); input.current?.focus(); }
  function close() { dialog.current?.close(); trigger.current?.focus(); }
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        if (dialog.current?.open) dialog.current.close();
        else { setQuery(""); dialog.current?.showModal(); input.current?.focus(); }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  return <>
    <button ref={trigger} className="workspace-search" onClick={open} aria-haspopup="dialog"><span>{t("studio.quickFind")}</span><kbd>⌘ / Ctrl K</kbd></button>
    <dialog ref={dialog} className="command-dialog" aria-label={t("studio.quickFind")} onClick={event => { if (event.target === event.currentTarget) close(); }} onKeyDown={event => {
      if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
      const buttons = Array.from(dialog.current?.querySelectorAll<HTMLButtonElement>(".command-results button") ?? []);
      if (!buttons.length) return;
      event.preventDefault();
      const current = buttons.indexOf(document.activeElement as HTMLButtonElement);
      const next = current < 0 ? (event.key === "ArrowDown" ? 0 : buttons.length - 1) : (current + (event.key === "ArrowDown" ? 1 : -1) + buttons.length) % buttons.length;
      buttons[next]?.focus();
    }}>
      <div className="command-search"><input ref={input} value={query} onChange={event => setQuery(event.target.value)} placeholder={t("studio.findPlaceholder")} aria-label={t("studio.quickFind")} onKeyDown={event => { if (event.key === "Enter" && filtered[0]) { event.preventDefault(); close(); navigate(filtered[0].to); } }} /><button onClick={close} aria-label={t("nav.closeMenu")}>Esc</button></div>
      <div className="command-results">{filtered.map(item => <button key={item.to} onClick={() => { close(); navigate(item.to); }}><span>{item.label}</span><span aria-hidden="true">↵</span></button>)}{!filtered.length && <p className="command-empty">{t("overview.noResults")}</p>}</div>
    </dialog>
  </>;
}
