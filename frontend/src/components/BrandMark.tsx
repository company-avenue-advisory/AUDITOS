// Brand mark - seal-and-tick: a plain ring (the "seal") with a checkmark
// stroked in two colors (agent-teal for the short leg, accent-vermilion for
// the long leg). Self-contained - no background container needed.
export default function BrandMark({ size = 34 }: { size?: number }) {
  return (
    <svg viewBox="0 0 100 100" width={size} height={size} aria-hidden="true">
      <circle cx="50" cy="50" r="44" fill="none" stroke="var(--text-primary)" strokeWidth="4" />
      <path d="M28 53 L43 68" fill="none" stroke="var(--agent)" strokeWidth="9" strokeLinecap="round" />
      <path d="M43 68 L74 29" fill="none" stroke="var(--accent)" strokeWidth="6.5" strokeLinecap="round" />
    </svg>
  );
}
