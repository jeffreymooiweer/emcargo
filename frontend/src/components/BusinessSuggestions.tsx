import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api/client";

type Candidate = { name: string; address: string };

export default function BusinessSuggestions({ name, city, language, disabled, onPick }: {
  name: string; city: string; language: string; disabled: boolean;
  onPick: (candidate: Candidate) => void;
}) {
  const { t } = useTranslation();
  const [result, setResult] = useState<{ results: Candidate[]; available: boolean } | null>(null);
  const [dismissed, setDismissed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    setResult(null); setDismissed(false);
    void api.geoBusinesses(name, city, language).then(value => {
      if (active) setResult(value);
    }).catch(() => { if (active) setResult({ results: [], available: false }); });
    return () => { active = false; };
  }, [name, city, language, attempt]);
  if (dismissed) return null;
  return <section className="assistant-business" aria-label={t("assistant.business.title")}>
    <h4>{t("assistant.business.title")} · {name}, {city}</h4>
    {!result ? <p role="status">{t("assistant.business.searching")}</p> : <>
      <p>{t(!result.available ? "assistant.business.unavailable" : !result.results.length ? "assistant.business.empty" : result.results.length > 1 ? "assistant.business.choose" : "assistant.business.confirm")}</p>
      {result.results.map(candidate => <button type="button" className="assistant-business-option" key={candidate.address} disabled={disabled} onClick={() => onPick(candidate)}>
        <strong>{candidate.name}</strong><span>{candidate.address}</span><span className="assistant-business-use">{t("assistant.business.use")}</span>
      </button>)}
      {!!result.results.length && <p className="assistant-business-source">{t("assistant.business.source")}</p>}
      {!result.available && <button type="button" className="assistant-text-button" disabled={disabled} onClick={() => setAttempt(n => n + 1)}>{t("assistant.business.retry")}</button>}
    </>}
    <button type="button" className="assistant-text-button" disabled={disabled} onClick={() => setDismissed(true)}>{t("assistant.business.manual")}</button>
  </section>;
}
