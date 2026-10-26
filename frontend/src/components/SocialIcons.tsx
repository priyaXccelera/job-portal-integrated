interface IconProps {
  className?: string
}

function Glyph({ text, className }: IconProps & { text: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
      <text x="12" y="17" textAnchor="middle" fontSize="14" fontWeight="700" fill="currentColor" fontFamily="Arial, sans-serif">
        {text}
      </text>
    </svg>
  )
}

export function Facebook({ className }: IconProps) {
  return <Glyph text="f" className={className} />
}

export function Linkedin({ className }: IconProps) {
  return <Glyph text="in" className={className} />
}

export function Twitter({ className }: IconProps) {
  return <Glyph text="X" className={className} />
}

export function Youtube({ className }: IconProps) {
  return <Glyph text="▶" className={className} />
}
