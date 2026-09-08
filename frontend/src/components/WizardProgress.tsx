import { useTranslation } from "react-i18next";

export type WizardStepKey = "forms" | "lines" | "questions" | "dg" | "details" | "export";
interface Step { n: number; key: WizardStepKey; label: string }
interface Props {
  steps: Step[];
  currentStep: number;
  visited?: WizardStepKey[];
  onGoTo?: (key: WizardStepKey) => void;
}

/** Visited steps remain direct links; pending checks cannot be skipped. */
export default function WizardProgress({ steps, currentStep, visited = [], onGoTo }: Props) {
  const { t } = useTranslation();
  const currentIndex = Math.max(0, steps.findIndex((step) => step.n === currentStep));
  return (
    <nav aria-label={t("wizard.progressLabel")}>
      <ol className="wizard-steps">
        {steps.map((step, index) => {
          const active = index === currentIndex;
          const done = visited.includes(step.key) && !active;
          const reachable = done && !!onGoTo;
          const content = <>
            <span className="wizard-step-number" aria-hidden="true">{index + 1}</span>
            <span className="min-w-0 break-words wizard-step-long">{step.label}</span>
            <span className="min-w-0 break-words wizard-step-short">{t(`review.shortStep.${step.key}`, { defaultValue: step.label })}</span>
          </>;
          return (
            <li key={step.key} aria-current={active ? "step" : undefined} className={done ? "wizard-step-done" : undefined}>
              {reachable ? (
                <button type="button" className="wizard-step" onClick={() => onGoTo(step.key)} aria-label={step.label}>{content}</button>
              ) : (
                <span className="wizard-step" aria-label={step.label}>{content}</span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
