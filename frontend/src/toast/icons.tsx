/** Notifications use the same geometry as the rest of the interface. */
export { CheckIcon, CloseIcon as CircleXmarkIcon, WarningIcon as ExclamationIcon, InfoIcon } from "../components/icons";
export function QuestionIcon({ className }: { className?: string }) {
  return <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M21 11a9 9 0 0 1-9 9H3v-9a9 9 0 0 1 18 0Z M9 8a3 3 0 1 1 5 2c-1 1-2 1-2 3 M12 16h.01" /></svg>;
}
export function SpinnerIcon({ className }: { className?: string }) {
  return <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" aria-hidden="true"><circle cx="12" cy="12" r="9" opacity=".2" /><path d="M12 3a9 9 0 0 1 9 9" /></svg>;
}
