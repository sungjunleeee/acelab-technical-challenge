// Stage 1 review: editable form. Each multi-valued axis is a row of chips,
// pre-checked for what the LLM extracted plus pre-unchecked suggestions.
// Users can toggle, remove, or add custom items (which get typo-validated
// against the appropriate Acelab reference endpoint).

import { useState } from 'react'
import { Plus, AlertTriangle, Check } from 'lucide-react'
import type { CriteriaSpec } from '../lib/types'
import { validate } from '../lib/api'
import { Button, Card, CardBody, CardHeader, Chip } from './ui'

type Props = {
  initial: CriteriaSpec
  onConfirm: (edited: CriteriaSpec) => void
  onCancel: () => void
}

const AXES: Array<{
  key: keyof Pick<
    CriteriaSpec,
    | 'performance_constraints'
    | 'certifications_required'
    | 'aesthetic_qualities'
    | 'material_categories'
  >
  label: string
  validateAs: 'certification' | 'category' | null
  customPlaceholder: string
}> = [
  {
    key: 'material_categories',
    label: 'Material categories',
    validateAs: 'category',
    customPlaceholder: 'add a category…',
  },
  {
    key: 'certifications_required',
    label: 'Certifications',
    validateAs: 'certification',
    customPlaceholder: 'add a certification…',
  },
  {
    key: 'performance_constraints',
    label: 'Performance',
    validateAs: null,
    customPlaceholder: 'add a constraint…',
  },
  {
    key: 'aesthetic_qualities',
    label: 'Aesthetic',
    validateAs: null,
    customPlaceholder: 'add an aesthetic…',
  },
]

export function CriteriaEditor({ initial, onConfirm, onCancel }: Props) {
  // Edited copy.
  const [c, setC] = useState<CriteriaSpec>(structuredClone(initial))

  function toggle(
    axis: (typeof AXES)[number]['key'],
    value: string,
    fromSuggestions: boolean,
  ) {
    setC((prev) => {
      const list = prev[axis]
      const sugList = prev.suggested_additions[axis]
      const inMain = list.includes(value)
      const next = structuredClone(prev)
      if (inMain) {
        // Remove from main; if it came from suggestions originally, add back.
        next[axis] = list.filter((v) => v !== value)
        if (
          fromSuggestions &&
          !next.suggested_additions[axis].includes(value)
        ) {
          next.suggested_additions[axis].push(value)
        }
      } else {
        next[axis] = [...list, value]
        next.suggested_additions[axis] = sugList.filter((v) => v !== value)
      }
      return next
    })
  }

  function remove(axis: (typeof AXES)[number]['key'], value: string) {
    setC((prev) => ({ ...prev, [axis]: prev[axis].filter((v) => v !== value) }))
  }

  function addCustom(axis: (typeof AXES)[number]['key'], value: string) {
    const v = value.trim()
    if (!v) return
    setC((prev) => {
      if (prev[axis].includes(v)) return prev
      return { ...prev, [axis]: [...prev[axis], v] }
    })
  }

  return (
    <div className="space-y-5">
      <header>
        <h2 className="text-xl font-semibold tracking-tight text-zinc-900">
          Confirm what we understood
        </h2>
        <p className="mt-1 text-sm text-zinc-600">
          Toggle to deselect, click suggestions to add, or type your own.
          Anything you confirm here drives the catalog search.
        </p>
      </header>

      {/* Top-line single-value fields */}
      <div className="grid grid-cols-3 gap-3">
        <SingleField
          label="Space"
          value={c.space_type}
          onChange={(v) => setC((p) => ({ ...p, space_type: v || null }))}
        />
        <SingleField
          label="Traffic"
          value={c.traffic_level}
          onChange={(v) => setC((p) => ({ ...p, traffic_level: v || null }))}
        />
        <SingleField
          label="Budget"
          value={c.budget_tier}
          onChange={(v) => setC((p) => ({ ...p, budget_tier: v || null }))}
        />
      </div>

      {AXES.map((axis) => {
        const main = c[axis.key]
        const suggested = c.suggested_additions[axis.key].filter(
          (s) => !main.includes(s),
        )
        return (
          <Card key={axis.key}>
            <CardHeader>
              <div className="flex items-baseline justify-between">
                <h3 className="text-sm font-semibold text-zinc-900">
                  {axis.label}
                </h3>
                <span className="text-xs text-zinc-500 tabular-nums">
                  {main.length} selected
                </span>
              </div>
            </CardHeader>
            <CardBody>
              <div className="flex flex-wrap gap-2">
                {main.map((v) => (
                  <Chip
                    key={`m-${v}`}
                    label={v}
                    selected
                    onToggle={() => toggle(axis.key, v, false)}
                    onRemove={() => remove(axis.key, v)}
                  />
                ))}
                {suggested.map((v) => (
                  <Chip
                    key={`s-${v}`}
                    label={v}
                    selected={false}
                    suggested
                    onToggle={() => toggle(axis.key, v, true)}
                  />
                ))}
              </div>
              <CustomAdder
                placeholder={axis.customPlaceholder}
                validateAs={axis.validateAs}
                onAdd={(v) => addCustom(axis.key, v)}
              />
            </CardBody>
          </Card>
        )
      })}

      {/* Branded preferences (different shape: only validation needed, no
          suggestions because the brief is the source of truth on brands). */}
      <Card>
        <CardHeader>
          <h3 className="text-sm font-semibold text-zinc-900">
            Branded preferences
          </h3>
        </CardHeader>
        <CardBody>
          <div className="flex flex-wrap gap-2">
            {c.branded_preferences.length === 0 && (
              <span className="text-xs text-zinc-500">
                No brands named. Add one if you want to bias toward a vendor.
              </span>
            )}
            {c.branded_preferences.map((b) => (
              <Chip
                key={b}
                label={b}
                selected
                onToggle={() =>
                  setC((p) => ({
                    ...p,
                    branded_preferences: p.branded_preferences.filter(
                      (v) => v !== b,
                    ),
                  }))
                }
                onRemove={() =>
                  setC((p) => ({
                    ...p,
                    branded_preferences: p.branded_preferences.filter(
                      (v) => v !== b,
                    ),
                  }))
                }
              />
            ))}
          </div>
          <CustomAdder
            placeholder="add a brand…"
            validateAs="brand"
            onAdd={(v) =>
              setC((p) => ({
                ...p,
                branded_preferences: p.branded_preferences.includes(v)
                  ? p.branded_preferences
                  : [...p.branded_preferences, v],
              }))
            }
          />
        </CardBody>
      </Card>

      <div className="flex items-center justify-between border-t border-zinc-200 pt-4">
        <Button variant="ghost" onClick={onCancel}>
          Start over
        </Button>
        <Button onClick={() => onConfirm(c)}>Confirm and continue →</Button>
      </div>
    </div>
  )
}

function SingleField({
  label,
  value,
  onChange,
}: {
  label: string
  value: string | null
  onChange: (v: string) => void
}) {
  return (
    <div>
      <label className="block text-xs font-medium text-zinc-500">{label}</label>
      <input
        value={value ?? ''}
        placeholder="—"
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 w-full rounded-md border border-zinc-200 bg-white px-2.5 py-1.5 text-sm focus:border-zinc-400 focus:outline-none"
      />
    </div>
  )
}

function CustomAdder({
  placeholder,
  validateAs,
  onAdd,
}: {
  placeholder: string
  validateAs: 'certification' | 'category' | 'brand' | null
  onAdd: (value: string) => void
}) {
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [hint, setHint] = useState<{
    kind: 'ok' | 'warn'
    message: string
    canonical?: string
  } | null>(null)

  async function commit() {
    const v = text.trim()
    if (!v) return
    if (!validateAs) {
      onAdd(v)
      setText('')
      setHint(null)
      return
    }
    setBusy(true)
    setHint(null)
    try {
      const res = await validate({ phrase: v, kind: validateAs })
      if (res.confidence === 'high' && res.canonical) {
        onAdd(res.canonical)
        setText('')
        setHint({
          kind: 'ok',
          message: `added "${res.canonical}"`,
          canonical: res.canonical,
        })
      } else if (res.confidence === 'medium' && res.canonical) {
        // Soft-confirm: surface canonical, let user pick whether to use it
        // or their literal text.
        setHint({
          kind: 'warn',
          message: `closest match: "${res.canonical}" (${(res.score * 100).toFixed(0)}%). Click again to use as typed, or pick from suggestions.`,
          canonical: res.canonical,
        })
      } else {
        setHint({
          kind: 'warn',
          message: `no good match in catalog. Click again to add as typed.`,
        })
      }
    } finally {
      setBusy(false)
    }
  }

  function commitWithCanonical(canonical: string) {
    onAdd(canonical)
    setText('')
    setHint(null)
  }

  function commitAsTyped() {
    onAdd(text.trim())
    setText('')
    setHint(null)
  }

  return (
    <div className="mt-3">
      <div className="flex items-center gap-2">
        <input
          value={text}
          onChange={(e) => {
            setText(e.target.value)
            setHint(null)
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault()
              if (hint?.kind === 'warn') commitAsTyped()
              else commit()
            }
          }}
          placeholder={placeholder}
          className="flex-1 rounded-md border border-zinc-200 bg-white px-2.5 py-1.5 text-sm placeholder:text-zinc-400 focus:border-zinc-400 focus:outline-none"
        />
        <Button
          variant="secondary"
          onClick={() => {
            if (hint?.kind === 'warn') commitAsTyped()
            else commit()
          }}
          disabled={!text.trim() || busy}
        >
          <Plus className="h-3.5 w-3.5" />
          {busy ? 'checking…' : 'add'}
        </Button>
      </div>
      {hint && (
        <div
          className={`mt-2 flex items-start gap-2 rounded-md px-2.5 py-1.5 text-xs ${
            hint.kind === 'ok'
              ? 'bg-emerald-50 text-emerald-800'
              : 'bg-amber-50 text-amber-900'
          }`}
        >
          {hint.kind === 'ok' ? (
            <Check className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          ) : (
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          )}
          <div className="flex-1">{hint.message}</div>
          {hint.canonical && hint.kind === 'warn' && (
            <button
              onClick={() => commitWithCanonical(hint.canonical!)}
              className="cursor-pointer rounded border border-amber-300 bg-white px-2 py-0.5 text-[11px] font-medium text-amber-900 hover:bg-amber-100"
            >
              use match
            </button>
          )}
        </div>
      )}
    </div>
  )
}
