interface Props {
  label: string
  value: number
}

export default function ScoreBar({ label, value }: Props) {
  const pct = Math.round(Math.min(1, Math.max(0, value || 0)) * 100)
  return (
    <div className="flex items-center gap-3 py-1">
      <span className="text-[#6B6B6B] text-xs w-20 flex-shrink-0 truncate">{label}</span>
      <div className="flex-1 h-1 rounded-sm overflow-hidden" style={{ background: '#E5E3DD' }}>
        <div
          className="h-full transition-all duration-500"
          style={{ width: `${pct}%`, background: '#0F766E' }}
        />
      </div>
      <span className="text-[#1A1A1A] font-mono text-xs w-10 text-right flex-shrink-0">
        {(value || 0).toFixed(2)}
      </span>
    </div>
  )
}
