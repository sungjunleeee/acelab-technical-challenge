// Thin API client over the FastAPI backend. Uses native fetch + EventSource-
// style SSE parsing (no extra deps).

import type {
  AgentEvent,
  CriteriaSpec,
  GroundedContext,
  ProductHit,
  Report,
  ValidateResponse,
} from './types'

const BASE = '/api'

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`${path} ${res.status}: ${text}`)
  }
  return res.json()
}

export function understand(brief: string): Promise<CriteriaSpec> {
  return postJson('/understand', { brief })
}

export function ground(criteria: CriteriaSpec): Promise<GroundedContext> {
  return postJson('/ground', criteria)
}

export function rank(args: {
  criteria: CriteriaSpec
  grounded: GroundedContext
  hits: ProductHit[]
}): Promise<Report> {
  return postJson('/rank', args)
}

export function validate(args: {
  phrase: string
  kind: 'certification' | 'category' | 'brand'
}): Promise<ValidateResponse> {
  return postJson('/validate', args)
}

// SSE caller. The fetch + ReadableStream approach lets us POST a body, which
// the standard EventSource API doesn't allow.
export async function streamSse(
  path: string,
  body: unknown,
  onEvent: (event: AgentEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  })
  if (!res.ok || !res.body) {
    const text = res.body ? await res.text() : ''
    throw new Error(`${path} ${res.status}: ${text}`)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    // Process complete events (separator: blank line per SSE spec).
    let sep
    while ((sep = buffer.indexOf('\n\n')) !== -1) {
      const raw = buffer.slice(0, sep)
      buffer = buffer.slice(sep + 2)
      const dataLine = raw
        .split('\n')
        .filter((l) => l.startsWith('data: '))
        .map((l) => l.slice(6))
        .join('\n')
      if (!dataLine) continue
      try {
        const parsed = JSON.parse(dataLine) as AgentEvent
        onEvent(parsed)
      } catch (err) {
        console.warn('SSE parse error', err, dataLine)
      }
    }
  }
}

export function streamSearch(
  args: { criteria: CriteriaSpec; grounded: GroundedContext },
  onEvent: (event: AgentEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  return streamSse('/search', args, onEvent, signal)
}

export function streamRun(
  brief: string,
  onEvent: (event: AgentEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  return streamSse('/run', { brief }, onEvent, signal)
}
