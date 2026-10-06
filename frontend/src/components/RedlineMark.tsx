/** The deck cover's mark: a curve rising toward a red line, with a red dot where they meet. */
export function RedlineMark({ className = 'logo' }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 32 22" aria-hidden="true">
      <path d="M2 20 C 9 20, 13 16, 17 11 S 24 6.6, 26 6.4" fill="none" stroke="var(--muted)" strokeWidth="2.4" strokeLinecap="round" />
      <line x1="11" y1="6" x2="30" y2="6" stroke="var(--red)" strokeWidth="2.6" strokeLinecap="round" />
      <circle cx="26" cy="6.2" r="2.6" fill="var(--red)" />
    </svg>
  )
}
