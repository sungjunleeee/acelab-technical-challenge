// Collapsible recommendation card. Always visible: rank, name, supplier,
// fit score with color coding, top-2 axes as chips, market_status. Click to
// expand: full why_it_fits, all matched axes, all caveats.
//
// Category icon is mapped from the most prominent axis (since the SDK doesn't
// expose product images).

import { useState } from 'react'
import {
  ChevronDown,
  ChevronUp,
  Layers3,
  Square,
  PaintBucket,
  Tag,
  AlertCircle,
  Box,
} from 'lucide-react'
import type { ComponentType, ReactNode } from 'react'
import type { Recommendation } from '../lib/types'
import { Badge, Card, FitScoreBadge } from './ui'

type Props = {
  rec: Recommendation
}

function escapeRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

// Highlights key terms in `why_it_fits` so the eye lands on what matters:
// the axis labels the product matched, similarity scores, MasterFormat codes,
// supplier name, and the "Live on Acelab" status string. Pure regex split,
// no innerHTML, no XSS surface.
function highlightWhyItFits(
  text: string,
  matchedAxes: string[],
  supplier: string | null,
): ReactNode[] {
  // Literal patterns. Sort longest first so e.g. "category: flooring" matches
  // before plain "flooring" leaks through and creates partial overlaps.
  const literals = [...matchedAxes]
  if (supplier) literals.push(supplier)
  literals.push('Live on Acelab')
  literals.sort((a, b) => b.length - a.length)

  const literalPattern = literals.map(escapeRegex).join('|')
  // Decimal similarity scores (0.83), integer percentages (83%),
  // MasterFormat-style codes (09 65 00).
  const dynamicPattern =
    String.raw`\b\d{1,3}%|\b[01]\.\d{1,3}\b|\b\d{2}\s\d{2}\s\d{2}\b`
  const combined = literalPattern
    ? `${literalPattern}|${dynamicPattern}`
    : dynamicPattern
  const re = new RegExp(`(${combined})`, 'g')

  const parts = text.split(re)
  return parts.map((p, i) =>
    i % 2 === 1 ? (
      <strong key={i} className="font-semibold text-zinc-900">
        {p}
      </strong>
    ) : (
      p
    ),
  )
}

function pickIcon(matchedAxes: string[]): ComponentType<{ className?: string }> {
  const blob = matchedAxes.join(' ').toLowerCase()
  if (blob.includes('flooring') || blob.includes('tile')) return Layers3
  if (blob.includes('wall')) return Square
  if (blob.includes('ceiling')) return Box
  if (blob.includes('aesthetic')) return PaintBucket
  if (blob.includes('brand:')) return Tag
  return Box
}

export function RecommendationCard({ rec }: Props) {
  const [open, setOpen] = useState(false)
  const Icon = pickIcon(rec.matched_axes)

  // Display helpers.
  const supplier = rec.supplier ?? '(supplier unknown)'
  const headlineAxes = rec.matched_axes.slice(0, 2)
  const moreCount = rec.matched_axes.length - headlineAxes.length

  return (
    <Card>
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full cursor-pointer text-left"
      >
        <div className="flex items-center gap-4 px-5 py-4">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-zinc-100 text-zinc-500">
            <Icon className="h-6 w-6" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-baseline gap-2">
              <span className="font-mono text-xs text-zinc-400 tabular-nums">
                #{rec.rank}
              </span>
              <h3 className="truncate text-base font-semibold text-zinc-900">
                {rec.product_name}
              </h3>
            </div>
            <div className="mt-0.5 truncate text-xs text-zinc-500">
              {supplier}
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              {headlineAxes.map((a) => (
                <Badge key={a} tone="info">
                  {a}
                </Badge>
              ))}
              {moreCount > 0 && (
                <span className="text-[11px] text-zinc-400">
                  +{moreCount} more
                </span>
              )}
            </div>
          </div>
          <FitScoreBadge score={rec.fit_score} matchedAxes={rec.matched_axes} />
          {open ? (
            <ChevronUp className="h-4 w-4 shrink-0 text-zinc-400" />
          ) : (
            <ChevronDown className="h-4 w-4 shrink-0 text-zinc-400" />
          )}
        </div>
      </button>

      {open && (
        <div className="border-t border-zinc-100 px-5 py-4 text-sm">
          <div className="space-y-3">
            <div>
              <div className="mb-1 text-xs font-semibold tracking-wide text-zinc-500 uppercase">
                Why it fits
              </div>
              <p className="text-zinc-800">
                {highlightWhyItFits(
                  rec.why_it_fits,
                  rec.matched_axes,
                  rec.supplier,
                )}
              </p>
            </div>

            {rec.matched_axes.length > 0 && (
              <div>
                <div className="mb-1 text-xs font-semibold tracking-wide text-zinc-500 uppercase">
                  All matched axes
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {rec.matched_axes.map((a) => (
                    <Badge key={a} tone="info">
                      {a}
                    </Badge>
                  ))}
                </div>
              </div>
            )}

            {rec.caveats.length > 0 && (
              <div>
                <div className="mb-1 flex items-center gap-1.5 text-xs font-semibold tracking-wide text-amber-700 uppercase">
                  <AlertCircle className="h-3.5 w-3.5" />
                  Verify on the manufacturer spec sheet
                </div>
                <ul className="space-y-1 text-xs text-zinc-700">
                  {rec.caveats.map((c, i) => (
                    <li
                      key={i}
                      className="rounded-md border border-amber-100 bg-amber-50 px-2 py-1"
                    >
                      {c}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      )}
    </Card>
  )
}
