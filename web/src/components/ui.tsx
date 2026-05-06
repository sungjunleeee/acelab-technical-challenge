// Shared visual primitives. shadcn/ui-style: copy-paste, no extra runtime deps.

import type { ReactNode } from 'react'

type DivProps = React.HTMLAttributes<HTMLDivElement>
type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'ghost'
}

function cn(...parts: (string | false | undefined | null)[]): string {
  return parts.filter(Boolean).join(' ')
}

export function Card({ className, ...rest }: DivProps) {
  return (
    <div
      className={cn(
        'rounded-lg border border-zinc-200 bg-white shadow-sm',
        className,
      )}
      {...rest}
    />
  )
}

export function CardHeader({ className, ...rest }: DivProps) {
  return <div className={cn('px-5 pt-5 pb-3', className)} {...rest} />
}

export function CardBody({ className, ...rest }: DivProps) {
  return <div className={cn('px-5 pb-5', className)} {...rest} />
}

export function Button({
  variant = 'primary',
  className,
  ...rest
}: ButtonProps) {
  const base =
    'inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50'
  const variants = {
    primary: 'bg-zinc-900 text-white hover:bg-zinc-800',
    secondary:
      'border border-zinc-200 bg-white text-zinc-900 hover:bg-zinc-50',
    ghost: 'text-zinc-700 hover:bg-zinc-100',
  } as const
  return <button className={cn(base, variants[variant], className)} {...rest} />
}

type ChipProps = {
  label: string
  selected: boolean
  suggested?: boolean
  onToggle: () => void
  onRemove?: () => void
}

export function Chip({ label, selected, suggested, onToggle, onRemove }: ChipProps) {
  const base =
    'inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition select-none'
  const cls = selected
    ? 'border-violet-300 bg-violet-50 text-violet-900 hover:bg-violet-100'
    : suggested
      ? 'border-dashed border-zinc-300 bg-white text-zinc-500 hover:border-zinc-400 hover:text-zinc-800'
      : 'border-zinc-200 bg-white text-zinc-700 hover:bg-zinc-50'
  return (
    <span className={cn(base, cls)}>
      <button type="button" onClick={onToggle} className="cursor-pointer">
        {selected ? '✓ ' : suggested ? '+ ' : ''}
        {label}
      </button>
      {selected && onRemove && (
        <button
          type="button"
          onClick={onRemove}
          aria-label={`remove ${label}`}
          className="cursor-pointer text-violet-500 hover:text-violet-700"
        >
          ×
        </button>
      )}
    </span>
  )
}

type BadgeProps = {
  children: ReactNode
  tone?: 'default' | 'success' | 'warning' | 'info'
  className?: string
}

export function Badge({ children, tone = 'default', className }: BadgeProps) {
  const tones = {
    default: 'border-zinc-200 bg-zinc-50 text-zinc-700',
    success: 'border-emerald-200 bg-emerald-50 text-emerald-800',
    warning: 'border-amber-200 bg-amber-50 text-amber-800',
    info: 'border-sky-200 bg-sky-50 text-sky-800',
  } as const
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium',
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  )
}

// Color-coded fit score bubble. Always 0..100. Tooltip shows the exact axes
// and the underlying decimal score.
export function FitScoreBadge({
  score,
  matchedAxes,
}: {
  score: number // 0..1
  matchedAxes: string[]
}) {
  const pct = Math.round(score * 100)
  const tone =
    pct >= 80
      ? 'bg-emerald-500 text-white'
      : pct >= 60
        ? 'bg-amber-400 text-white'
        : 'bg-rose-500 text-white'
  const tooltip =
    `Fit ${score.toFixed(3)}\n` +
    (matchedAxes.length
      ? `Matched axes:\n${matchedAxes.map((a) => `• ${a}`).join('\n')}`
      : 'No axis labels recorded')
  return (
    <span
      title={tooltip}
      className={cn(
        'inline-flex h-10 w-10 items-center justify-center rounded-full text-sm font-semibold tabular-nums shadow',
        tone,
      )}
    >
      {pct}
    </span>
  )
}

export function Spinner({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={cn('h-4 w-4 animate-spin', className)}
      fill="none"
    >
      <circle
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeOpacity="0.25"
        strokeWidth="3"
      />
      <path
        d="M22 12a10 10 0 0 1-10 10"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
      />
    </svg>
  )
}
