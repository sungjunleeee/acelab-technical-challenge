// Stage 2 review: confirm or unselect canonical certs / taxonomy mappings /
// brand verifications before they go into Stage 3's product searches. Wrong
// canonicalizations bias the entire search space, so this is the cheapest
// place to catch them.

import { Check, X, ExternalLink } from 'lucide-react'
import { useState } from 'react'
import type { GroundedContext } from '../lib/types'
import { Badge, Button, Card, CardBody } from './ui'

type Props = {
  initial: GroundedContext
  onConfirm: (edited: GroundedContext) => void
  onBack: () => void
}

function confidenceTone(score: number) {
  if (score >= 0.85) return 'success' as const
  if (score >= 0.7) return 'info' as const
  return 'warning' as const
}

export function GroundingReview({ initial, onConfirm, onBack }: Props) {
  const [keepCert, setKeepCert] = useState<boolean[]>(
    initial.certifications.map(() => true),
  )
  const [keepTax, setKeepTax] = useState<boolean[]>(
    initial.taxonomies.map(() => true),
  )
  const [keepBrand, setKeepBrand] = useState<boolean[]>(
    initial.brands.map(() => true),
  )

  function emit() {
    onConfirm({
      certifications: initial.certifications.filter((_, i) => keepCert[i]),
      taxonomies: initial.taxonomies.filter((_, i) => keepTax[i]),
      brands: initial.brands.filter((_, i) => keepBrand[i]),
    })
  }

  const isEmpty =
    initial.certifications.length === 0 &&
    initial.taxonomies.length === 0 &&
    initial.brands.length === 0

  return (
    <div className="space-y-5">
      <header>
        <h2 className="text-xl font-semibold tracking-tight text-zinc-900">
          Confirm what we matched in the catalog
        </h2>
        <p className="mt-1 text-sm text-zinc-600">
          The agent looked up every cert, category, and brand against the
          Acelab reference endpoints. Drop anything that mismatches before we
          search for products.
        </p>
      </header>

      {isEmpty && (
        <Card>
          <CardBody className="pt-5">
            <p className="text-sm text-zinc-600">
              Nothing to canonicalize. Continuing straight to product search.
            </p>
          </CardBody>
        </Card>
      )}

      {initial.certifications.length > 0 && (
        <section className="space-y-2">
          <h3 className="text-sm font-semibold tracking-wide text-zinc-700 uppercase">
            Certifications
          </h3>
          {initial.certifications.map((cert, i) => (
            <Card key={`cert-${i}`} className={!keepCert[i] ? 'opacity-50' : ''}>
              <CardBody className="pt-5">
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline gap-2">
                      <span className="text-xs text-zinc-500">you said</span>
                      <span className="text-sm font-medium text-zinc-700">
                        "{cert.requested}"
                      </span>
                      <span className="text-zinc-300">→</span>
                      <span className="text-sm font-semibold text-zinc-900">
                        {cert.canonical_name}
                      </span>
                      <Badge tone={confidenceTone(cert.score)}>
                        {Math.round(cert.score * 100)}% match
                      </Badge>
                    </div>
                    {cert.issuer && cert.issuer.length > 0 && (
                      <div className="mt-1 text-xs text-zinc-500">
                        issued by {cert.issuer.join(', ')}
                      </div>
                    )}
                    {cert.description && (
                      <p className="mt-2 line-clamp-2 text-xs text-zinc-600">
                        {cert.description}
                      </p>
                    )}
                  </div>
                  <ToggleKeep
                    keep={keepCert[i]}
                    onChange={(v) =>
                      setKeepCert((prev) => prev.map((p, j) => (j === i ? v : p)))
                    }
                  />
                </div>
              </CardBody>
            </Card>
          ))}
        </section>
      )}

      {initial.taxonomies.length > 0 && (
        <section className="space-y-2">
          <h3 className="text-sm font-semibold tracking-wide text-zinc-700 uppercase">
            MasterFormat categories
          </h3>
          {initial.taxonomies.map((t, i) => (
            <Card key={`tax-${i}`} className={!keepTax[i] ? 'opacity-50' : ''}>
              <CardBody className="pt-5">
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline gap-2">
                      <span className="text-xs text-zinc-500">you said</span>
                      <span className="text-sm font-medium text-zinc-700">
                        "{t.category}"
                      </span>
                      <span className="text-zinc-300">→</span>
                      <span className="text-sm font-semibold text-zinc-900">
                        {t.canonical_label}
                      </span>
                      <Badge tone={confidenceTone(t.score)}>
                        {Math.round(t.score * 100)}% match
                      </Badge>
                      {t.matched ? (
                        <Badge tone="success">matched</Badge>
                      ) : (
                        <Badge tone="warning">candidate only</Badge>
                      )}
                    </div>
                    {t.masterformat_code && (
                      <div className="mt-1 font-mono text-xs text-zinc-500">
                        MasterFormat {t.masterformat_code}
                      </div>
                    )}
                  </div>
                  <ToggleKeep
                    keep={keepTax[i]}
                    onChange={(v) =>
                      setKeepTax((prev) => prev.map((p, j) => (j === i ? v : p)))
                    }
                  />
                </div>
              </CardBody>
            </Card>
          ))}
        </section>
      )}

      {initial.brands.length > 0 && (
        <section className="space-y-2">
          <h3 className="text-sm font-semibold tracking-wide text-zinc-700 uppercase">
            Brands
          </h3>
          {initial.brands.map((b, i) => (
            <Card key={`brand-${i}`} className={!keepBrand[i] ? 'opacity-50' : ''}>
              <CardBody className="pt-5">
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline gap-2">
                      <span className="text-xs text-zinc-500">you said</span>
                      <span className="text-sm font-medium text-zinc-700">
                        "{b.requested}"
                      </span>
                      <span className="text-zinc-300">→</span>
                      <span className="text-sm font-semibold text-zinc-900">
                        {b.canonical_name}
                      </span>
                      {b.verified ? (
                        <Badge tone="success">verified</Badge>
                      ) : (
                        <Badge tone="warning">name mismatch</Badge>
                      )}
                    </div>
                    <div className="mt-1 flex items-center gap-3 text-xs text-zinc-500">
                      {b.status && <span>{b.status}</span>}
                      {b.website && (
                        <a
                          href={
                            b.website.startsWith('http')
                              ? b.website
                              : `https://${b.website}`
                          }
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-1 text-violet-700 hover:underline"
                        >
                          {b.website}
                          <ExternalLink className="h-3 w-3" />
                        </a>
                      )}
                    </div>
                  </div>
                  <ToggleKeep
                    keep={keepBrand[i]}
                    onChange={(v) =>
                      setKeepBrand((prev) =>
                        prev.map((p, j) => (j === i ? v : p)),
                      )
                    }
                  />
                </div>
              </CardBody>
            </Card>
          ))}
        </section>
      )}

      <div className="flex items-center justify-between border-t border-zinc-200 pt-4">
        <Button variant="ghost" onClick={onBack}>
          ← Back to criteria
        </Button>
        <Button onClick={emit}>Confirm and search →</Button>
      </div>
    </div>
  )
}

function ToggleKeep({
  keep,
  onChange,
}: {
  keep: boolean
  onChange: (v: boolean) => void
}) {
  return (
    <button
      onClick={() => onChange(!keep)}
      title={keep ? 'drop this match' : 'keep this match'}
      className={`flex h-8 w-8 shrink-0 cursor-pointer items-center justify-center rounded-md border transition ${
        keep
          ? 'border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-100'
          : 'border-zinc-200 bg-white text-zinc-400 hover:bg-zinc-50'
      }`}
    >
      {keep ? <Check className="h-4 w-4" /> : <X className="h-4 w-4" />}
    </button>
  )
}
