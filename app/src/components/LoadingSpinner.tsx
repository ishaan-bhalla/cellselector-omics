interface Props {
  text?: string
  size?: 'sm' | 'md'
}

export default function LoadingSpinner({ text = 'Loading...', size = 'md' }: Props) {
  const ring = size === 'sm' ? 'w-4 h-4 border' : 'w-5 h-5 border-2'
  return (
    <div className="flex items-center gap-2.5">
      <div className={`${ring} border-[#E5E3DD] border-t-[#0F766E] rounded-full animate-spin`} />
      {text && <span className="text-[#6B6B6B] text-xs">{text}</span>}
    </div>
  )
}
