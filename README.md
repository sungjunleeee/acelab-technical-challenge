# Material Recommendation Agent

A CLI agent that turns a free-text architect brief into ranked, grounded material recommendations against the Acelab catalog.

## Brief (the take-home prompt)

> Build an agent that takes a natural language description of a project or space and returns ranked material recommendations with reasoning.
>
> **Example input:** "High-traffic hospital corridor that needs to meet infection control standards, LEED Silver minimum, and a calming aesthetic. Budget is mid-range."
>
> The agent should (1) analyze the request and identify what to search for, (2) make multiple, targeted calls to the Acelab SDK, and (3) synthesize results into ranked recommendations that explain *why* each product fits. The key differentiator is **multi-step reasoning**: decompose, search across multiple dimensions, cross-reference, and synthesize.

The full original prompt is preserved in git history (`6ce1480 chore: take-home repo as provided`).

## Quickstart

Prereqs: Python 3.12+, [uv](https://docs.astral.sh/uv/).

```bash
# 1. Create .env with the three required keys (see .env.example)
cp .env.example .env
#    Then fill in: OPENROUTER_API_KEY, ACELAB_API_KEY, ACELAB_BASE_URL

# 2. Install
uv sync

# 3. Run
uv run python -m src.cli "High-traffic hospital corridor that needs to meet infection control standards, LEED Silver minimum, and a calming aesthetic. Budget is mid-range."
```

Output is markdown by default. Pass `--json` to dump the full structured `Report` (parseable for grading or piping into another tool):

```bash
uv run python -m src.cli "..." --json > report.json
```

Stage progress is streamed to stderr while results go to stdout, so `--json` output stays clean for piping.

The optional `MODEL` env var overrides the default LLM (`anthropic/claude-sonnet-4.6`) for any OpenRouter-supported model.

## Approach

A **4-stage hybrid pipeline**: a deterministic shell around an autonomous LLM tool-calling loop. Pure tool-calling skips grounding and rambles; a pure pipeline doesn't show real reasoning. The hybrid gets both: structured checkpoints for trust and reproducibility, autonomous decomposition where it actually matters.

```mermaid
flowchart TD
    A[brief] --> B["Stage 1 UNDERSTAND<br/>LLM, structured output"]
    B --> C["CriteriaSpec<br/><i>space, certs, perf, aesthetics, categories, brands</i>"]
    C --> D["Stage 2 GROUND<br/>async fan-out, no LLM"]
    D --> E["GroundedContext<br/><i>canonical certs, MasterFormat codes, verified brands</i>"]
    E --> F["Stage 3 SEARCH<br/>LLM tool-calling loop, &le;8 iterations"]
    F --> G["list of ProductHit<br/><i>each hit carries match provenance</i>"]
    G --> H["Stage 4 RANK<br/>LLM, structured output"]
    H --> I["Report<br/><i>top-8 Recommendations, grounded why_it_fits, caveats</i>"]
    I --> J["Stage 5 RENDER<br/>pure function"]
    J --> K[markdown / JSON]

    classDef llm fill:#e1f5ff,stroke:#0277bd,color:#01579b
    classDef pure fill:#f1f8e9,stroke:#558b2f,color:#33691e
    classDef data fill:#fff8e1,stroke:#f9a825,color:#f57f17
    class B,F,H llm
    class D,J pure
    class C,E,G,I data
```

**Stage 1 Understand.** A single structured-output LLM call parses the brief into a `CriteriaSpec`: space type, traffic level, budget tier, plus arrays for performance constraints, certifications required, aesthetic qualities, material categories, and branded preferences. Jargon (`IIC > 50`, `ASTM E84 Class A`) is preserved verbatim so Stage 2 can canonicalize it; silently dropping acronyms is the failure mode here. Architects aren't prompt engineers; the brief might be terse, vague, or RFP-prose.

**Stage 2 Ground.** Deterministic parallel fan-out (no LLM): each criterion is looked up against the appropriate Acelab reference endpoint via `asyncio.gather`. Cert phrases hit `certifications.search`, categories hit `taxonomy.search` (yielding MasterFormat codes like `09 65 16`), brands hit `companies.search` with a name-substring sanity check (the embedding endpoint will happily return `"Object Carpet"` for `"Interface"`). Empirical similarity thresholds (derived from `examples/probe.py`) keep noisy near-misses from contaminating Stage 3's prompt. The grounded context becomes the canonical vocabulary downstream.

**Stage 3 Search.** An autonomous LLM tool-calling loop (≤8 iterations, ~12 calls) with three tools: `search_products`, `search_companies`, and `finish_searches`. The system prompt seeds with the `CriteriaSpec` plus `GroundedContext` and instructs decomposition along `{category × use-case × constraint}` axes. **Every** `search_products` call must carry an `axis_label` argument naming which `CriteriaSpec` axis the query derives from. That axis label is what gives every product hit its provenance trail (which queries surfaced it, at what score, for what reason). When the same product is hit by multiple queries, the entries accumulate. Stage 4 reasons over that provenance.

**Stage 4 Rank & Explain.** A single structured-output LLM call takes the `CriteriaSpec` plus `GroundedContext` plus top-30 deduplicated `ProductHit`s and emits ranked `Recommendation`s. The prompt is the load-bearing hallucination guard: the LLM is instructed to cite matched axes and scores from the provenance data, **not** to claim certifications, materials, or specs the SDK never returned. A baseline `caveats[]` list is auto-derived from the brief so the architect always sees what to verify off-platform, even if the LLM forgets to add anything.

## Key design decisions

### Hybrid pipeline over pure tool-calling

Pure tool-calling lets the model wander and skips grounding. A pure pipeline doesn't demonstrate the multi-step reasoning the rubric grades. Bookending one autonomous loop (Stage 3) with three deterministic stages gets both: the structured stages keep the run reproducible and explainable, while Stage 3 still demonstrates real decomposition. The stage boundaries are also where a future UI inserts user edits cheaply (more on that below).

### Match-provenance grounding for `why_it_fits`

The `ProductSearchResult` only exposes `(name, supplier, status, similarity_score)`. There is no `products.get()`, no per-product attribute API, no certification list per product. Any `why_it_fits` text that says "GREENGUARD Gold certified" or "low-VOC" is therefore a **hallucination**: the model has no source for that claim.

The recommendation reasoning is grounded **only** in:

1. Which decomposed queries surfaced the product, with their similarity scores.
2. The `CriteriaSpec` axes those queries derived from (the `axis_label` from Stage 3).
3. Supplier `status_name` (e.g. "Live on Acelab") from companies enrichment.
4. Taxonomy classification of the product's apparent category.

Every `Recommendation` ships with a `caveats[]` list that explicitly enumerates what the architect must verify on the manufacturer spec sheet. Stage 4's system prompt forbids attribute claims and includes negative examples ("not GREENGUARD Gold certified", etc.). Honesty over impressiveness.

### No web-search models for v1

OpenRouter `:online` and Perplexity sonar variants would let the model verify cert claims via web search. Considered and rejected for v1:

- Cert details live in **PDF spec sheets**, not HTML. Web search lands on marketing pages and misses what we'd want.
- Latency cost: 5 to 15 seconds per call, multiplied across the top N picks, on top of the ~20s baseline.
- The rubric grades how well we use the **Acelab SDK**; bolting on external sources risks looking like we're routing around the actual challenge.

Kept as a stretch flag (`--verify-top-3`), not a v1 dependency.

### Stage-level API plus event stream for forward compatibility

Each stage is a plain typed async function:

```python
async def understand(brief) -> CriteriaSpec
async def ground(criteria) -> GroundedContext
async def search(criteria, grounded, on_event=None) -> list[ProductHit]
async def rank(criteria, grounded, hits) -> Report
```

`run_agent()` is a 20-line wrapper that chains them and emits `AgentEvent`s. A future UI (e.g. a "search-bar" web app) can call the stages individually, interpose user edits between any two (editable keyword chips after Stage 1, cert-canonicalization checkboxes after Stage 2), and consume the same event stream for a live progress view, with no agent refactor needed. Interruption is free: the UI just doesn't call the next stage until the user clicks Continue.

### Honesty over impressiveness

Every recommendation comes with verification caveats. The Stage 4 prompt explicitly forbids attribute claims it can't ground in the API response. A recommendation that admits "this product surfaced for queries derived from your *infection-control* and *flooring* axes; verify GREENGUARD Gold and antimicrobial coating on the manufacturer spec sheet" is more useful to an architect than one that confidently invents certifications.

## Repository tour

| Path | Purpose |
|---|---|
| `acelab/` | Vendor SDK (do not modify). |
| `src/schemas.py` | Pydantic types: the only data structures that flow between stages. |
| `src/llm.py` | OpenRouter client, structured-output and tool-calling helpers. |
| `src/stages/understand.py` | Stage 1: brief to `CriteriaSpec` (1 LLM call). |
| `src/stages/ground.py` | Stage 2: parallel fan-out to `certifications`, `taxonomy`, `companies` (no LLM). |
| `src/stages/search.py` | Stage 3: autonomous tool-calling loop with provenance tracking. |
| `src/stages/rank.py` | Stage 4: ranked recommendations with grounded `why_it_fits`. |
| `src/render.py` | `Report` to markdown (deterministic, pure function). |
| `src/agent.py` | Stage-level API plus `run_agent()` convenience wrapper plus event emission. |
| `src/cli.py` | `python -m src.cli "<brief>" [--json]` entry point. |
| `tests/` | Validation set (`validation_set.py`, 10 `BriefCase`s spanning content and input-quality axes), per-stage unit tests with hand-written mocks (`test_stages.py`, runs in under 1s on every save), and live-API e2e tests behind the `pytest -m e2e` marker, including a hallucination audit that fails when `why_it_fits` makes un-corroborated cert claims. |
| `examples/basic_usage.py` | Original Acelab SDK smoke test (verifies env wiring). |
| `examples/probe.py` | Diagnostic probe of all SDK endpoints on the README's hospital-corridor brief. Informed Stage 2's similarity thresholds and the decision **not** to enrich with `materials.notes` (the field came back empty). |
| `examples/probe_companies.py` | Follow-up probe confirming `companies.search` is name-based, not description-based: the reason Stage 2 sanity-checks brand resolutions by substring. |

## Pipeline at a glance

```mermaid
sequenceDiagram
    participant U as User
    participant A as Agent
    participant L as LLM (OpenRouter)
    participant S as Acelab SDK

    U->>A: brief
    A->>L: extract CriteriaSpec
    L-->>A: structured CriteriaSpec
    par Grounding fan-out (parallel)
        A->>S: certifications.search
        A->>S: taxonomy.search
        A->>S: companies.search
    end
    S-->>A: GroundedContext
    loop Search loop (≤8 iterations)
        A->>L: pick next decomposed query
        L-->>A: tool call: search_products / search_companies
        A->>S: search request
        S-->>A: results with similarity scores
        A->>A: accumulate ProductHit + QueryMatch provenance
    end
    A->>L: rank top-30 with criteria + grounded context
    L-->>A: ranked Recommendations + caveats
    A-->>U: Report (markdown or JSON)
```

## What I would improve with more time

- **`--verify-top-3` flag** using `:online` web search to verify cert claims on the top 3 picks only. Kept off the v1 critical path so latency and rubric framing stay clean, but it's the natural next add-on for an architect who wants extra confidence before specifying.
- **React/TypeScript web UI on top of the stage-level API.** Search-bar input, then editable keyword chips after Stage 1, then checkbox grid for cert canonicalizations after Stage 2, then live progress sidebar during Stage 3, then collapsible recommendation cards for Stage 4. The agent layer is already shaped for this; it's a new entry point, not a refactor.
- **LLM-judge cert canonicalization.** Today's threshold-based grounding occasionally lets semantically related but factually different certs through (e.g. "ASTM E84 Class A" resolves to "E108-20a (Class A)", which is a different test). A second-pass LLM judge with a clear "is X the same standard as Y?" prompt would catch these.
- **Cached SDK responses for deterministic e2e tests.** The 21-test `pytest -m e2e` suite currently hits live APIs and burns LLM credits per run. Recording the SDK responses per `BriefCase` once (and the LLM responses behind a deterministic seed) would make hallucination audits and prompt-regression checks CI-friendly.
- **Sharper Stage 1 axis taxonomy.** "no PVC" is currently tagged as a performance constraint when it's arguably a material exclusion. A separate `material_exclusions[]` axis (or a tighter prompt with negative examples) would give Stage 3 a cleaner signal to filter against rather than search for.
