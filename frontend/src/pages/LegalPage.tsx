import { useTranslation } from "react-i18next";

const panelClass = "bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800";

export default function LegalPage() {
  const { t } = useTranslation();
  const sections = t("legal.sections", { returnObjects: true }) as { heading: string; body: string }[];

  return (
    <div className="collection-page page-enter space-y-4 sm:space-y-6">
      <div className={`${panelClass} p-5 sm:p-8`}>
        <h2 className="text-xl sm:text-2xl font-semibold text-slate-900 dark:text-slate-100">{t("legal.title")}</h2>
        <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">{t("legal.updated")}</p>
        <p className="mt-4 max-w-3xl text-sm leading-relaxed text-slate-700 dark:text-slate-300">{t("legal.intro")}</p>
      </div>

      <div className={`${panelClass} divide-y divide-slate-100 dark:divide-slate-800`}>
        {Array.isArray(sections) &&
          sections.map((section, i) => (
            <section key={i} className="p-5 sm:p-6">
              <h3 className="font-semibold text-slate-900 dark:text-slate-100">{section.heading}</h3>
              <p className="mt-2 max-w-3xl whitespace-pre-line text-sm leading-relaxed text-slate-600 dark:text-slate-300">
                {section.body}
              </p>
            </section>
          ))}
      </div>

      {/* Credits belong where the people using the application can see them,
          not only in a file in the repository: the icon set is free to use on
          the condition that it is named, and a licence condition met only in
          a developer's markdown is not met. The link is part of the required
          form and therefore hard-coded rather than translated — only the
          sentence around it changes language. */}
      <div className={`${panelClass} p-5 sm:p-6`}>
        <h3 className="font-semibold text-slate-900 dark:text-slate-100">{t("legal.creditsHeading")}</h3>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-slate-600 dark:text-slate-300">
          {t("legal.creditsBody")}
        </p>
        {/* Two lines, not one, because they are two sets. The first eight came
            from the Uicons set and were confirmed against it. The twenty-one
            added in v1.202.0 for the shell did not: their exported markup does
            not match a Uicons export, so naming them as Uicons would be a
            statement nobody checked. What is certain about them is where they
            were downloaded from, and that is what this says. */}
        <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
          Uicons by{" "}
          <a
            href="https://www.flaticon.com/uicons"
            target="_blank"
            rel="noreferrer"
            className="text-sky-700 underline dark:text-sky-400"
          >
            Flaticon
          </a>
        </p>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
          Icons by{" "}
          <a
            href="https://www.flaticon.com/"
            target="_blank"
            rel="noreferrer"
            className="text-sky-700 underline dark:text-sky-400"
          >
            Flaticon
          </a>
        </p>
      </div>
    </div>
  );
}
