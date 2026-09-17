import { useState, type ReactNode } from 'react'

// Generic hover/focus-triggered popover — appears on hover or focus of
// its trigger child, disappears when the pointer/focus leaves. Used for
// the Fit Score weight-breakdown (anchored to FitRing) AND, per Item 2's
// re-verification, per-metric explanations (MetricRow, ResultCardCompact)
// — those previously used the native `title` attribute, which has real,
// user-reported usability problems here (slow/inconsistent trigger delay,
// no styling, unreliable across browsers/devices). This is the same
// mechanism already proven working for Fit Score, reused rather than
// inventing a second tooltip system.
interface Props {
  children: ReactNode
  content: ReactNode
  placement?: 'above' | 'below'
  /** 'center' (default, used for FitRing) or 'left' (used for MetricRow's
   *  full-width rows, where centring under the whole row would land the
   *  popover far from the icon/label the user is actually hovering). */
  align?: 'center' | 'left'
  /** Trigger wrapper's own className — 'inline-flex' (default) suits a
   *  compact trigger like FitRing; MetricRow passes 'flex w-full' so the
   *  hover target covers its whole row, not just its intrinsic width. */
  className?: string
}

export default function HoverPopover({ children, content, placement = 'above', align = 'center', className = 'inline-flex' }: Props) {
  const [open, setOpen] = useState(false)

  return (
    <div
      className={`relative ${className}`}
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
            width: 240,
            pointerEvents: 'none',
            ...(align === 'center'
              ? { left: '50%', transform: 'translateX(-50%)' }
              : { left: 0 }),
            ...(placement === 'above' ? { bottom: '100%', marginBottom: 8 } : { top: '100%', marginTop: 8 }),
          }}
        >
          {content}
        </div>
      )}
    </div>
  )
}
