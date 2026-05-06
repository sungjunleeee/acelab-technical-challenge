// Top-level orchestrator. State machine:
//
//   idle ──Search──▶ understand ──▶ criteria_review ──Confirm──▶ ground
//                                                                  │
//                                              grounded_review ◀───┘
//                                                  │ Confirm
//                                                  ▼
//                                       search (SSE) ──▶ rank ──▶ done
//
// The user can drop back to idle at any point by clicking "Start over".

import { useEffect, useState } from 'react'
import {
  ground,
  rank,
  streamSearch,
  understand,
} from './lib/api'
import type {
  AgentEvent,
  CriteriaSpec,
  GroundedContext,
  ProductHit,
  Report,
  StageKey,
  StageStatus,
} from './lib/types'
import { SearchBox } from './components/SearchBox'
import { StageSidebar } from './components/StageSidebar'
import { CriteriaEditor } from './components/CriteriaEditor'
import { GroundingReview } from './components/GroundingReview'
import { RecommendationCard } from './components/RecommendationCard'
import { Button, Spinner } from './components/ui'

type Phase =
  | { kind: 'idle' }
  | { kind: 'understanding' }
  | { kind: 'criteria_review'; criteria: CriteriaSpec }
  | { kind: 'grounding'; criteria: CriteriaSpec }
  | { kind: 'grounded_review'; criteria: CriteriaSpec; grounded: GroundedContext }
  | {
      kind: 'searching'
      criteria: CriteriaSpec
      grounded: GroundedContext
    }
  | {
      kind: 'ranking'
      criteria: CriteriaSpec
      grounded: GroundedContext
      hits: ProductHit[]
    }
  | { kind: 'done'; report: Report }
  | { kind: 'error'; message: string }

type StageView = { status: StageStatus; summary?: string }

const INITIAL_STAGES: Record<StageKey, StageView> = {
  understand: { status: 'pending' },
  ground: { status: 'pending' },
  search: { status: 'pending' },
  rank: { status: 'pending' },
}

export default function App() {
  const [phase, setPhase] = useState<Phase>({ kind: 'idle' })
  const [stages, setStages] =
    useState<Record<StageKey, StageView>>(INITIAL_STAGES)
  const [searchProgress, setSearchProgress] = useState<{
    angles: number
    products: number
    lastQuery: string | null
  } | null>(null)

  function setStage(key: StageKey, status: StageStatus, summary?: string) {
    setStages((prev) => ({ ...prev, [key]: { status, summary } }))
  }

  function reset() {
    setPhase({ kind: 'idle' })
    setStages(INITIAL_STAGES)
    setSearchProgress(null)
  }

  function backToCriteria() {
    if (phase.kind !== 'grounded_review') return
    // Re-open the Stage 1 editor with the criteria the user already confirmed,
    // and reset Stage 2's status so the sidebar reflects the rewind.
    setStage('ground', 'pending')
    setPhase({ kind: 'criteria_review', criteria: phase.criteria })
  }

  async function handleSubmit(brief: string) {
    setStages(INITIAL_STAGES)
    setSearchProgress(null)
    setPhase({ kind: 'understanding' })
    setStage('understand', 'in_progress')
    try {
      const criteria = await understand(brief)
      setStage('understand', 'awaiting_user', summarizeCriteria(criteria))
      setPhase({ kind: 'criteria_review', criteria })
    } catch (err) {
      handleError(err)
    }
  }

  async function handleConfirmCriteria(edited: CriteriaSpec) {
    setStage('understand', 'done', summarizeCriteria(edited))
    setStage('ground', 'in_progress')
    setPhase({ kind: 'grounding', criteria: edited })
    try {
      const grounded = await ground(edited)
      setStage('ground', 'awaiting_user', summarizeGrounded(grounded))
      setPhase({ kind: 'grounded_review', criteria: edited, grounded })
    } catch (err) {
      handleError(err)
    }
  }

  async function handleConfirmGrounded(edited: GroundedContext) {
    if (phase.kind !== 'grounded_review') return
    const { criteria } = phase
    setStage('ground', 'done', summarizeGrounded(edited))
    setStage('search', 'in_progress')
    setSearchProgress({ angles: 0, products: 0, lastQuery: null })
    setPhase({ kind: 'searching', criteria, grounded: edited })

    let finalHits: ProductHit[] = []
    try {
      await streamSearch({ criteria, grounded: edited }, (e: AgentEvent) => {
        if (e.type === 'search_progress') {
          setSearchProgress({
            angles: e.angles_explored,
            products: e.products_found,
            lastQuery: e.last_query,
          })
        } else if (e.type === 'search_done') {
          finalHits = e.hits
        } else if (e.type === 'error') {
          throw new Error(e.message)
        }
      })
      setStage('search', 'done', `${finalHits.length} unique products surfaced`)
      setPhase({ kind: 'ranking', criteria, grounded: edited, hits: finalHits })
      setStage('rank', 'in_progress')
      const report = await rank({
        criteria,
        grounded: edited,
        hits: finalHits,
      })
      setStage(
        'rank',
        'done',
        `${report.recommendations.length} recommendations`,
      )
      setPhase({ kind: 'done', report })
    } catch (err) {
      handleError(err)
    }
  }

  function handleError(err: unknown) {
    const message = err instanceof Error ? err.message : String(err)
    setPhase({ kind: 'error', message })
  }

  // The idle / prompting page is the focal element: no sidebar, search box
  // vertically centered. As soon as the user submits a brief the sidebar
  // appears and the layout shifts to a left-rail + main-body view.
  const isIdle = phase.kind === 'idle'

  return (
    <div className="flex min-h-screen bg-zinc-50">
      {!isIdle && (
        <StageSidebar stages={stages} searchProgress={searchProgress} />
      )}
      <main className={isIdle ? 'flex flex-1 flex-col' : 'flex-1 px-8 py-10'}>
        {isIdle ? (
          <div className="flex flex-1 flex-col items-center justify-center px-4 py-12">
            <header className="mb-8 text-center">
              <h1 className="text-3xl font-semibold tracking-tight text-zinc-900">
                Material Recommendation Agent
              </h1>
              <p className="mt-2 text-sm text-zinc-600">
                Describe a project, review what the agent understood, then get
                ranked recommendations grounded in the Acelab catalog.
              </p>
            </header>
            <Body
              phase={phase}
              onSubmit={handleSubmit}
              onConfirmCriteria={handleConfirmCriteria}
              onConfirmGrounded={handleConfirmGrounded}
              onBackToCriteria={backToCriteria}
              onReset={reset}
              searchProgress={searchProgress}
            />
          </div>
        ) : (
          <div className="mx-auto max-w-3xl">
            <header className="mb-8">
              <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">
                Material Recommendation Agent
              </h1>
              <p className="mt-1 text-sm text-zinc-600">
                Describe a project, review what the agent understood, then get
                ranked recommendations grounded in the Acelab catalog.
              </p>
            </header>
            <Body
              phase={phase}
              onSubmit={handleSubmit}
              onConfirmCriteria={handleConfirmCriteria}
              onConfirmGrounded={handleConfirmGrounded}
              onBackToCriteria={backToCriteria}
              onReset={reset}
              searchProgress={searchProgress}
            />
          </div>
        )}
      </main>
    </div>
  )
}

function Body({
  phase,
  onSubmit,
  onConfirmCriteria,
  onConfirmGrounded,
  onBackToCriteria,
  onReset,
  searchProgress,
}: {
  phase: Phase
  onSubmit: (brief: string) => void
  onConfirmCriteria: (c: CriteriaSpec) => void
  onConfirmGrounded: (g: GroundedContext) => void
  onBackToCriteria: () => void
  onReset: () => void
  searchProgress: {
    angles: number
    products: number
    lastQuery: string | null
  } | null
}) {
  if (phase.kind === 'idle') {
    return <SearchBox onSubmit={onSubmit} />
  }

  if (phase.kind === 'understanding') {
    return (
      <RunningPlaceholder>
        Parsing your brief into structured criteria…
      </RunningPlaceholder>
    )
  }

  if (phase.kind === 'criteria_review') {
    return (
      <CriteriaEditor
        initial={phase.criteria}
        onConfirm={onConfirmCriteria}
        onCancel={onReset}
      />
    )
  }

  if (phase.kind === 'grounding') {
    return (
      <RunningPlaceholder>
        Canonicalizing certs, categories, and brands against the catalog…
      </RunningPlaceholder>
    )
  }

  if (phase.kind === 'grounded_review') {
    return (
      <GroundingReview
        initial={phase.grounded}
        onConfirm={onConfirmGrounded}
        onBack={onBackToCriteria}
      />
    )
  }

  if (phase.kind === 'searching') {
    return <SearchingPanel searchProgress={searchProgress} />
  }

  if (phase.kind === 'ranking') {
    return <RankingPanel />
  }

  if (phase.kind === 'done') {
    return <DoneView report={phase.report} onReset={onReset} />
  }

  return (
    <div className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900">
      <div className="font-semibold">Something went wrong</div>
      <div className="mt-1 font-mono text-xs">{phase.message}</div>
      <div className="mt-3">
        <Button variant="secondary" onClick={onReset}>
          Start over
        </Button>
      </div>
    </div>
  )
}

function RunningPlaceholder({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-zinc-200 bg-white p-5 text-sm text-zinc-700 shadow-sm">
      <Spinner className="text-violet-600" />
      <span>{children}</span>
    </div>
  )
}

function SearchingPanel({
  searchProgress,
}: {
  searchProgress: {
    angles: number
    products: number
    lastQuery: string | null
  } | null
}) {
  const angles = searchProgress?.angles ?? 0
  const products = searchProgress?.products ?? 0
  const lastQuery = searchProgress?.lastQuery
  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-6 shadow-sm">
      <div className="flex items-center gap-3">
        <Spinner className="text-violet-600" />
        <h2 className="text-lg font-semibold text-zinc-900">
          Searching the Acelab catalog
        </h2>
      </div>
      <p className="mt-1 text-sm text-zinc-600">
        Decomposing your brief into orthogonal product searches across
        category, performance, certification, and aesthetic axes.
      </p>

      <div className="mt-5 grid grid-cols-2 gap-3">
        <Stat label="unique products" value={products} />
        <Stat label="search-axis matches" value={angles} />
      </div>

      {lastQuery && (
        <div className="mt-4 rounded-md border border-zinc-100 bg-zinc-50 px-3 py-2">
          <div className="text-[11px] font-semibold tracking-wide text-zinc-500 uppercase">
            current query
          </div>
          <div className="mt-0.5 text-sm italic text-zinc-700">{lastQuery}</div>
        </div>
      )}
    </div>
  )
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border border-zinc-100 bg-zinc-50 px-3 py-2">
      <div className="text-2xl font-semibold tabular-nums text-zinc-900">
        {value}
      </div>
      <div className="text-xs text-zinc-500">{label}</div>
    </div>
  )
}

// Stage 4 is one LLM call (typically 20 to 30 seconds for the rank step) so
// there's no real progress signal to stream. We show a psychological bar
// that eases toward 95% over the median observed time, plus a rotating
// status line so the user sees the page is alive. The bar completes when
// the request actually returns.
const RANKING_STATUS_LINES = [
  'Reviewing the candidate pool against your criteria…',
  'Cross-referencing match provenance with your axis priorities…',
  'Drafting why-it-fits explanations…',
  'Compiling spec-sheet verification caveats…',
  'Finalizing the ranked list…',
]
// Median observed wall time for the rank stage with the Haiku 4.5 default
// (Sonnet 4.6 takes ~30s, Haiku ~15s). Bar eases toward 95% over this window
// then holds; the actual response completes the transition.
const RANKING_EXPECTED_MS = 14000

function RankingPanel() {
  const [pct, setPct] = useState(0)
  const [statusIdx, setStatusIdx] = useState(0)

  useEffect(() => {
    const start = Date.now()
    const target = 95
    const id = setInterval(() => {
      const elapsed = Date.now() - start
      const t = Math.min(1, elapsed / RANKING_EXPECTED_MS)
      // Ease-out cubic toward target.
      const next = target * (1 - Math.pow(1 - t, 3))
      setPct(next)
      if (t >= 1) clearInterval(id)
    }, 100)
    return () => clearInterval(id)
  }, [])

  useEffect(() => {
    const id = setInterval(() => {
      setStatusIdx((i) => (i + 1) % RANKING_STATUS_LINES.length)
    }, 4500)
    return () => clearInterval(id)
  }, [])

  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-6 shadow-sm">
      <div className="flex items-center gap-3">
        <Spinner className="text-violet-600" />
        <h2 className="text-lg font-semibold text-zinc-900">
          Synthesizing recommendations
        </h2>
      </div>
      <p className="mt-1 min-h-[1.25rem] text-sm text-zinc-600 transition-opacity">
        {RANKING_STATUS_LINES[statusIdx]}
      </p>
      <div className="mt-5 h-2 overflow-hidden rounded-full bg-zinc-100">
        <div
          className="h-full rounded-full bg-violet-500 transition-[width] duration-200 ease-out"
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="mt-2 flex items-center justify-between text-[11px] tabular-nums text-zinc-400">
        <span>typically 12-18 seconds</span>
        <span>{Math.round(pct)}%</span>
      </div>
    </div>
  )
}

function DoneView({
  report,
  onReset,
}: {
  report: Report
  onReset: () => void
}) {
  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between border-b border-zinc-200 pb-3">
        <div>
          <h2 className="text-xl font-semibold tracking-tight text-zinc-900">
            {report.recommendations.length} recommendations
          </h2>
          <p className="text-xs text-zinc-500">
            from {report.total_products_considered} unique products
          </p>
        </div>
        <Button variant="secondary" onClick={onReset}>
          New search
        </Button>
      </div>
      {report.recommendations.map((r) => (
        <RecommendationCard key={`${r.rank}-${r.product_name}`} rec={r} />
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Sidebar summary helpers
// ---------------------------------------------------------------------------

function summarizeCriteria(c: CriteriaSpec): string {
  const parts: string[] = []
  if (c.material_categories.length)
    parts.push(`categories: ${c.material_categories.join(', ')}`)
  if (c.certifications_required.length)
    parts.push(`certs: ${c.certifications_required.join(', ')}`)
  return parts.join(' · ') || 'minimal criteria'
}

function summarizeGrounded(g: GroundedContext): string {
  const parts: string[] = []
  if (g.certifications.length) parts.push(`${g.certifications.length} cert(s)`)
  if (g.taxonomies.length) parts.push(`${g.taxonomies.length} taxonomy term(s)`)
  if (g.brands.length) parts.push(`${g.brands.length} brand(s)`)
  return parts.join(', ') || 'no canonical matches'
}
