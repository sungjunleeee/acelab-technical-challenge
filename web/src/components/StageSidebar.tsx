// Left rail showing the 4-stage pipeline progress. Each stage has a status
// chip (pending / in-progress / awaiting user / done) and an optional
// one-line summary of what it produced.

import {
  Brain,
  Compass,
  Search,
  ListOrdered,
  Check,
  Loader2,
  Pause,
} from 'lucide-react'
import type { ComponentType } from 'react'
import type { StageKey, StageStatus } from '../lib/types'

type StageView = {
  status: StageStatus
  summary?: string
}

type Props = {
  stages: Record<StageKey, StageView>
  searchProgress?: {
    angles: number
    products: number
    lastQuery: string | null
  } | null
}

const STAGES: Array<{
  key: StageKey
  label: string
  icon: ComponentType<{ className?: string }>
  description: string
}> = [
  { key: 'understand', label: '1. Understand', icon: Brain, description: 'Parse the brief' },
  { key: 'ground', label: '2. Ground', icon: Compass, description: 'Canonicalize via reference APIs' },
  { key: 'search', label: '3. Search', icon: Search, description: 'Decomposed product queries' },
  { key: 'rank', label: '4. Rank', icon: ListOrdered, description: 'Synthesize recommendations' },
]

function statusIcon(status: StageStatus) {
  if (status === 'done')
    return <Check className="h-4 w-4 text-emerald-600" />
  if (status === 'in_progress')
    return <Loader2 className="h-4 w-4 animate-spin text-violet-600" />
  if (status === 'awaiting_user')
    return <Pause className="h-4 w-4 text-amber-600" />
  return <span className="block h-2 w-2 rounded-full bg-zinc-300" />
}

export function StageSidebar({ stages, searchProgress }: Props) {
  return (
    <aside className="w-72 shrink-0 border-r border-zinc-200 bg-white">
      <div className="sticky top-0 px-5 py-6">
        <h2 className="mb-1 text-sm font-semibold tracking-wide text-zinc-900 uppercase">
          Pipeline
        </h2>
        <p className="mb-5 text-xs text-zinc-500">
          4 stages, you can edit between any two
        </p>

        <ol className="space-y-1">
          {STAGES.map((s, idx) => {
            const view = stages[s.key]
            const Icon = s.icon
            const active = view.status === 'in_progress' || view.status === 'awaiting_user'
            return (
              <li key={s.key} className="relative pb-4">
                {idx < STAGES.length - 1 && (
                  <span
                    className={`absolute top-8 left-[15px] h-full w-px ${
                      view.status === 'done'
                        ? 'bg-emerald-200'
                        : 'bg-zinc-200'
                    }`}
                  />
                )}
                <div className="flex gap-3">
                  <div
                    className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full border ${
                      view.status === 'done'
                        ? 'border-emerald-300 bg-emerald-50'
                        : active
                          ? 'border-violet-300 bg-violet-50'
                          : 'border-zinc-200 bg-white'
                    }`}
                  >
                    <Icon
                      className={`h-4 w-4 ${
                        view.status === 'done'
                          ? 'text-emerald-700'
                          : active
                            ? 'text-violet-700'
                            : 'text-zinc-400'
                      }`}
                    />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <span
                        className={`text-sm font-medium ${
                          view.status === 'pending'
                            ? 'text-zinc-400'
                            : 'text-zinc-900'
                        }`}
                      >
                        {s.label}
                      </span>
                      {statusIcon(view.status)}
                    </div>
                    <p className="text-xs text-zinc-500">{s.description}</p>
                    {view.summary && (
                      <p className="mt-1 line-clamp-2 text-xs text-zinc-600">
                        {view.summary}
                      </p>
                    )}
                    {s.key === 'search' &&
                      view.status === 'in_progress' &&
                      searchProgress && (
                        <div className="mt-2 rounded-md border border-zinc-100 bg-zinc-50 px-2.5 py-1.5">
                          <div className="text-xs tabular-nums text-zinc-700">
                            {searchProgress.products} products from{' '}
                            {searchProgress.angles} matches
                          </div>
                          {searchProgress.lastQuery && (
                            <div className="mt-1 line-clamp-2 text-[11px] text-zinc-500">
                              <span className="text-zinc-400">last:</span>{' '}
                              <span className="italic">
                                {searchProgress.lastQuery}
                              </span>
                            </div>
                          )}
                        </div>
                      )}
                  </div>
                </div>
              </li>
            )
          })}
        </ol>
      </div>
    </aside>
  )
}
