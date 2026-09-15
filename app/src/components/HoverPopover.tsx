import { useState, type ReactNode } from 'react'

// Generic hover/focus-triggered popover — appears on hover or focus of
// its trigger child, disappears when the pointer/focus leaves, per Item
// 2's "hover-triggered tooltip/popover ... appearing on hover/focus,
// disappearing when the pointer/focus leaves" spec. Used to anchor the
// Fit Score weight-breakdown content to the FitRing/numeral itself,
// replacing the old permanent panel.
interface Props {
  children: ReactNode
  content: ReactNode
  placement?: 'above' | 'below'
}

export default function HoverPopover({ children, content, placement = 'above' }: Props) {
  const [open, setOpen] = useState(false)

  return (
    <div
      className="relative inline-flex"
      tabIndex={0}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
    >
      {children}
      {open && (
        <div
          role="tooltip"
          className="absolute z-40 bg-cso-card border border-[var(--border)] rounded p-3 text-xs text-[var(--text-body)] leading-relaxed"
          style={{
            width: 280,
            left: '50%',
            transform: 'translateX(-50%)',
            pointerEvents: 'none',
            ...(placement === 'above' ? { bottom: '100%', marginBottom: 8 } : { top: '100%', marginTop: 8 }),
          }}
        >
          {content}
        </div>
      )}
    </div>
  )
}
