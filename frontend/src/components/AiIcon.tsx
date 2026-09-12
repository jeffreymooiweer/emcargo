/** A conversation bubble with a sparkle, matching the interface's line icons. */
export default function AiIcon({ className = "h-5 w-5" }: { className?: string }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className={className}>
    <path d="M6 3h12a3 3 0 0 1 3 3v10a3 3 0 0 1-3 3H9l-6 3V6a3 3 0 0 1 3-3Z" />
    <path d="m12 6 1.2 2.8L16 10l-2.8 1.2L12 14l-1.2-2.8L8 10l2.8-1.2L12 6Z" />
  </svg>;
}
