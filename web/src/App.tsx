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

import { useState } from 'react'
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

  return (
    <div className="flex min-h-screen bg-zinc-50">
      <StageSidebar stages={stages} searchProgress={searchProgress} />
      <main className="flex-1 px-8 py-10">
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
            onReset={reset}
          />
        </div>
      </main>
    </div>
  )
}

function Body({
  phase,
  onSubmit,
  onConfirmCriteria,
  onConfirmGrounded,
  onReset,
}: {
  phase: Phase
  onSubmit: (brief: string) => void
  onConfirmCriteria: (c: CriteriaSpec) => void
  onConfirmGrounded: (g: GroundedContext) => void
  onReset: () => void
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
        onBack={onReset}
      />
    )
  }

  if (phase.kind === 'searching') {
    return (
      <RunningPlaceholder>
        Decomposing your brief into orthogonal product searches. Watch the
        sidebar for live progress.
      </RunningPlaceholder>
    )
  }

  if (phase.kind === 'ranking') {
    return (
      <RunningPlaceholder>
        Synthesizing the final ranked recommendations…
      </RunningPlaceholder>
    )
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
