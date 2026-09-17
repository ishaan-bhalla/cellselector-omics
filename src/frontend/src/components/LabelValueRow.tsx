// Two-column label/value row for GENE CLASS / GENE ROLE (Part 1, PROBLEM
// A of the original redesign) — an uppercase, letter-spaced label on the
// left with a hover explanation (title attribute), plain value text on
// the right, each on its own line so the two concepts can never read as
// one run-together string. Shared by every result-card layout (LIST,
// GRID) that has room for a full row; COMPACT inlines its own condensed
// version instead (no vertical room for two lines there).
export default function LabelValueRow({ label, value, explanation }: { label: string; value: string; explanation: string }) {
  return (
    <div className="flex items-baseline gap-3 py-0.5">
      <span
        className="text-[11px] uppercase tracking-[0.08em] text-cso-body w-24 flex-shrink-0 cursor-help"
        title={explanation}
      >
        {label}
      </span>
      <span className="text-sm text-cso-heading">{value}</span>
    </div>
  )
}
