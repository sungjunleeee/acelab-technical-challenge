// Hand-mirrored from src/schemas.py. Kept in sync manually because the
// type surface is small (~10 types) and not worth pulling in openapi-typescript.

export interface SuggestedAdditions {
  performance_constraints: string[]
  certifications_required: string[]
  aesthetic_qualities: string[]
  material_categories: string[]
}

export interface CriteriaSpec {
  raw_brief: string
  space_type: string | null
  traffic_level: string | null
  budget_tier: string | null
  performance_constraints: string[]
  certifications_required: string[]
  aesthetic_qualities: string[]
  material_categories: string[]
  branded_preferences: string[]
  suggested_additions: SuggestedAdditions
}

export interface CertificationResolution {
  requested: string
  canonical_name: string
  issuer: string[] | null
  description: string | null
  score: number
}

export interface TaxonomyResolution {
  category: string
  canonical_label: string | null
  masterformat_code: string | null
  score: number
  matched: boolean
}

export interface BrandResolution {
  requested: string
  canonical_name: string | null
  website: string | null
  status: string | null
  score: number
  verified: boolean
}

export interface GroundedContext {
  certifications: CertificationResolution[]
  taxonomies: TaxonomyResolution[]
  brands: BrandResolution[]
}

export interface QueryMatch {
  query: string
  axis_label: string
  score: number
}

export interface ProductHit {
  product_id: string
  product_name: string
  supplier: string | null
  market_status: string | null
  matches: QueryMatch[]
}

export interface Recommendation {
  rank: number
  product_name: string
  supplier: string | null
  why_it_fits: string
  matched_axes: string[]
  fit_score: number // 0.0 to 1.0
  caveats: string[]
}

export interface Report {
  brief: string
  criteria: CriteriaSpec
  grounded: GroundedContext
  recommendations: Recommendation[]
  total_products_considered: number
}

// AgentEvent tagged union. The discriminator is the `type` field.
export type AgentEvent =
  | { type: 'criteria_extracted'; criteria: CriteriaSpec }
  | { type: 'grounding_resolved'; grounded: GroundedContext }
  | {
      type: 'search_progress'
      angles_explored: number
      products_found: number
      last_query: string | null
    }
  | { type: 'ranking_started' }
  | { type: 'done'; report: Report }
  | { type: 'search_done'; hits: ProductHit[] }
  | { type: 'error'; message: string }

// Validation endpoint response.
export interface ValidateCandidate {
  name: string
  score: number
  extra: string | null
}

export interface ValidateResponse {
  canonical: string | null
  score: number
  candidates: ValidateCandidate[]
  confidence: 'high' | 'medium' | 'low'
}

// 4 stages of the pipeline (used by the sidebar).
export type StageKey = 'understand' | 'ground' | 'search' | 'rank'

export type StageStatus = 'pending' | 'in_progress' | 'awaiting_user' | 'done'
