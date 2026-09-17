interface Props {
  text?: string
  size?: 'sm' | 'md'
}

export default function LoadingSpinner({ text = 'Loading...', size = 'md' }: Props) {
  const ring = size === 'sm' ? 'w-4 h-4 border' : 'w-5 h-5 border-2'
  return (
    <div className="flex items-center gap-2.5">
      <div className={`${ring} border-[var(--border)] border-t-[var(--text-heading)] rounded-full animate-spin`} />
      {text && <span className="text-[var(--text-body)] text-xs">{text}</span>}
    </div>
  )
}
