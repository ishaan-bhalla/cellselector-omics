import type { ReactNode } from 'react'

// AI justification text (Groq/gpt-oss-20b) uses markdown "**bold**" syntax
// that was previously rendered as literal asterisks (see Part 6 of the
// Phase 1 UI redesign task). Full markdown rendering is out of scope for a
// design-only task, so this handles just **bold** — the one construct
// actually observed in captured justification output — splitting on
// "**...**" pairs and wrapping the inner text in <strong>, leaving
// everything else (including a genuinely unpaired "**") as plain text.
export function renderBold(text: string): ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*)/g)
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
      return <strong key={i}>{part.slice(2, -2)}</strong>
    }
    return <span key={i}>{part}</span>
  })
}
