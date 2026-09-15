import { useEffect, useRef, useState, type ReactNode, type ElementType } from 'react'

interface Props {
  children: ReactNode
  className?: string
  /** ms — staggers a group of Reveals entering together */
  delay?: number
  as?: ElementType
}

// Scroll-triggered fade + small translate, via IntersectionObserver and a
// plain CSS transition (no animation library). Fires once per element
// (unobserved immediately after triggering, per Part 2's "don't fire
// twice") — restrained by design: 350ms, 20px translate, not bouncy.
export default function Reveal({ children, className = '', delay = 0, as: Tag = 'div' }: Props) {
  const ref = useRef<HTMLElement>(null)
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    // Already in view on mount (e.g. a short page, or a reload scrolled
    // down) — reveal immediately rather than waiting for a scroll event
    // that may never come.
    const rect = el.getBoundingClientRect()
    if (rect.top < window.innerHeight && rect.bottom > 0) {
      setVisible(true)
      return
    }
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true)
          observer.unobserve(el)
        }
      },
      { threshold: 0.15, rootMargin: '0px 0px -40px 0px' }
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  return (
    <Tag
      ref={ref}
      className={className}
      style={{
        opacity: visible ? 1 : 0,
        transform: visible ? 'translateY(0)' : 'translateY(20px)',
        transition: `opacity 350ms ease ${delay}ms, transform 350ms ease ${delay}ms`,
        willChange: 'opacity, transform',
      }}
    >
      {children}
    </Tag>
  )
}
