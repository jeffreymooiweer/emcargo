/** Original compass mark: a guide towards the next useful action. */
export default function AiIcon({ className = "h-5 w-5" }: { className?: string }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className={className}>
    <circle className="assistant-compass-ring" cx="12" cy="12" r="9" strokeDasharray="42 4 7 4" />
    <path className="assistant-compass-needle" d="m16.8 7.2-2.9 6.7-6.7 2.9 2.9-6.7 6.7-2.9Z" />
    <path d="m10.1 10.1 3.8 3.8" />
  </svg>;
}
