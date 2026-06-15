# Agent I/O Reference — All 11 Agents

> Complete input/output specification for every agent in the pipeline.  
> All types are defined in `backend/models/schemas.py`.

---

## Type definitions (shared)

```python
# Enums
ClaimType     = "quantitative" | "qualitative" | "hedged" | "methodological_caveat"
RelationType  = "SUPPORTS" | "CONTRADICTS" | "PARTIAL_CONTRADICTION" | "NOT_COMPARABLE"
ERSBand       = "High" | "Medium" | "Low"
LensRating    = "severe" | "moderate" | "minor" | "clear"

# Core models
Claim = {
    claim_id:   str        # UUID
    source_id:  str        # Qdrant point ID
    text:       str        # full claim sentence
    claim_type: ClaimType
    confidence: float      # 0.0–1.0 — source's own hedging
}

ReliabilityScore = {
    source_id:         str
    score:             float        # 0.0–1.0
    source_type:       str          # "rct", "cohort", etc.
    recency_score:     float        # 0.0–1.0
    llm_escalated:     bool
    escalation_reason: str | None
}

ContradictionEdge = {
    claim_a_id:  str
    claim_b_id:  str
    relation:    RelationType
    explanation: str
}

ContradictionGraph = {
    edges: list[ContradictionEdge]
}

ApplicabilityFlag = {
    source_id:        str
    population_match: bool
    timeframe_match:  bool
    outcome_match:    bool
    flag_reason:      str | None
}

ApplicabilityReport = {
    flags:              list[ApplicabilityFlag]
    overall_applicable: bool
}

LensAnalysis = {
    rating:                 LensRating
    findings:               list[str]   # specific issues, min 1
    penalty_recommendation: float       # 0.00–0.30
}

CritiqueOutput = {
    source_attack:       LensAnalysis
    scope_attack:        LensAnalysis
    completeness_attack: LensAnalysis
    convergence_attack:  LensAnalysis
    insufficient_evidence:        bool
    insufficient_evidence_reason: str | None
    adjusted_reliability:         float    # 0.0–1.0
    adjusted_consensus:           float    # 0.0–1.0
    key_uncertainties:            list[str]
    overall_severity:             LensRating
}

ERSPenaltyBreakdown = {
    contradiction_edges_hard:    int
    contradiction_edges_partial: int
    contradiction_penalty:       float
    inapplicable_source_count:   int
    total_source_count:          int
    applicability_penalty:       float
    uncertainty_count:           int
    uncertainty_penalty:         float
    total_penalty:               float
}

ERSResult = {
    score:                float        # 0.0–1.0, final ERS
    band:                 ERSBand
    confidence_lower:     float
    confidence_upper:     float
    source_score:         float
    consensus_score:      float
    retrieval_relevance:  float
    contradiction_penalty: float
    applicability_penalty: float
    uncertainty_penalty:   float
    penalty_breakdown:    ERSPenaltyBreakdown
    formula_trace:        str          # e.g. "ERS = 0.45×0.72 + 0.35×0.61 + 0.20×0.83 = ..."
}
```

---

## A1 — Ingestion

**Phase:** 1  
**Type:** Sequential  
**LLM:** None

### Input
```python
request: PipelineRequest = {
    query:       str        # raw user question
    user_id:     str | None
    session_id:  str | None
    max_sources: int        # default 10
}
```

### Output
```python
{
    "clean_query": str,      # sanitised, PII-redacted, injection-filtered query
    "session_id":  str | None
}
```

### Processing steps
1. GLiNER NER scan → redact named entities classified as PII (names, locations, IDs)
2. Prompt-injection pattern matching → strip known injection payloads
3. Token budget enforcement → raise if `len(tokens) > max_tokens_per_request`
4. Deduplication → exact-match hash check against recent session queries

### Error conditions
| Condition | Behaviour |
|-----------|-----------|
| Token budget exceeded | Raises `ValueError` — pipeline halts |
| Injection detected | Query is sanitised (injection stripped), warning logged |

---

## A2 — Retrieval

**Phase:** 2  
**Type:** Sequential  
**LLM:** Gemini embedding-001

### Input
```python
clean_query: str
```

### Output
```python
list[{
    "id":      str | int,       # Qdrant point ID
    "score":   float,           # vector similarity score 0.0–1.0
    "payload": dict             # stored document metadata + text
}]
```

### Processing steps
1. Embed `clean_query` via `gemini_service.embed()` → 768-dim vector
2. Qdrant vector search → top-K by cosine similarity
3. BM25 keyword search → top-K by BM25 score (uses stored document index)
4. Hybrid merge via Reciprocal Rank Fusion (RRF)
5. Cross-encoder rerank → final ranked list

### Configuration
| Setting | Default | Description |
|---------|---------|-------------|
| `top_k_documents` | 10 | Number of documents to return |
| Qdrant collection | `evidence_store` | Configured in settings |
| BM25 | rank_bm25 | Corpus built from stored payloads |

---

## A3 — Evidence Extraction

**Phase:** 3  
**Type:** Sequential  
**LLM:** Gemini Flash (one call per document)

### Input
```python
documents: list[{
    "id":      str | int,
    "score":   float,
    "payload": {"text": str, ...}
}]
```

### Output
```python
claims: list[Claim]
```

### Processing steps
1. For each document: call Gemini Flash with extraction prompt
2. Parse JSON array from response
3. Validate each claim against `Claim` schema
4. Assign `claim_id` (UUID) and `source_id` (document ID)
5. Filter out claims with `confidence < 0.1`

### Edge cases
| Condition | Behaviour |
|-----------|-----------|
| Empty document | Returns empty list for that document |
| Gemini returns invalid JSON | Parse error logged, document skipped |
| 0 claims extracted across all documents | A8 pre-check triggers INSUFFICIENT_EVIDENCE |

---

## A4 — Reliability Scoring

**Phase:** 4 (parallel with A5/A6/A7)  
**Type:** Parallel  
**LLM:** Gemini Flash (escalation path only)

### Input
```python
documents: list[{
    "id":      str | int,
    "payload": {
        "source_type":        str,   # "rct", "cohort", etc.
        "year":               int,
        "conflict_of_interest": bool | None
    }
}]
```

### Output
```python
reliability: list[ReliabilityScore]
```

### Processing steps
1. Look up `source_type` in deterministic score table
2. Compute `recency_score = max(0, 1 - (2025 - year) × 0.05)`
3. If CoI flag or unknown source type → LLM escalation
4. Final score = average of (base_score, recency_score)

### Source type score table
| Source type | Base score |
|-------------|-----------|
| systematic_review | 1.0 |
| rct | 0.9 |
| cohort | 0.75 |
| case_control | 0.65 |
| expert_opinion | 0.4 |
| unknown | 0.3 → escalated |

---

## A5 — Consensus Scoring

**Phase:** 4 (parallel)  
**Type:** Parallel  
**LLM:** Gemini embedding-001 (one embed per claim)

### Input
```python
claims: list[Claim]
```

### Output
```python
consensus_score: float    # 0.0–1.0
```

### Processing steps
1. Embed each claim text → 768-dim vector
2. Build pairwise cosine similarity matrix (n × n)
3. Extract upper triangle (non-diagonal pairs)
4. Return mean of all pairwise similarities

### Edge cases
| Condition | Behaviour |
|-----------|-----------|
| 0 claims | Returns 0.5 |
| 1 claim | Returns 0.5 (insufficient data for consensus) |
| All claims identical | Returns ~1.0 |

---

## A6 — Contradiction Detection

**Phase:** 4 (parallel)  
**Type:** Parallel  
**LLM:** Gemini Flash (only for similar pairs)

### Input
```python
claims: list[Claim]
```

### Output
```python
contradiction_graph: ContradictionGraph
```

### Processing steps
1. Embed all claims (reuses embeddings if A5 ran first — TODO: share cache)
2. Compute pairwise cosine similarity
3. Filter to pairs with similarity ≥ 0.8 (same topic threshold)
4. For each filtered pair: call Gemini Flash to classify relationship
5. Collect all non-NOT_COMPARABLE edges into ContradictionGraph

### Similarity threshold rationale
Threshold of 0.8 means: only claims about the same topic are compared.  
Below 0.8, claims are too dissimilar to logically contradict each other.  
Above 0.8, semantic similarity is high enough that logical conflict is meaningful.

---

## A7 — Applicability Assessment

**Phase:** 4 (parallel)  
**Type:** Parallel  
**LLM:** Gemini Flash (one call per document)

### Input
```python
query:     str
documents: list[{"id": str, "payload": {"text": str, ...}}]
```

### Output
```python
applicability_report: ApplicabilityReport
```

### Processing steps
1. For each document: call Gemini Flash with applicability prompt
2. Parse `{population_match, timeframe_match, outcome_match, flag_reason}`
3. Build `ApplicabilityFlag` per document
4. Set `overall_applicable = all flags have all three dimensions True`

---

## A8 — Critique / Skeptic  ★ Phase 5

**Phase:** 5 (sequential, after all Phase 4)  
**Type:** Sequential  
**LLM:** Gemini Pro (system instruction + JSON mode)

### Input
```python
query:               str
claims:              list[Claim]
reliability:         list[ReliabilityScore]
contradiction_graph: ContradictionGraph
applicability:       ApplicabilityReport
```

### Output
```python
critique: CritiqueOutput
```

### Internal execution order
```
1. _pre_check()           — deterministic, no LLM
2. _build_message()       — format all inputs
3. model.generate_content()  — Gemini Pro with system instruction
4. _parse()               — validate into CritiqueOutput
```

### Key output fields

| Field | Type | Description |
|-------|------|-------------|
| `source_attack` | LensAnalysis | Issues with source quality and reliability |
| `scope_attack` | LensAnalysis | Issues with population/timeframe/outcome match |
| `completeness_attack` | LensAnalysis | Missing evidence and systematic gaps |
| `convergence_attack` | LensAnalysis | Illusory consensus, citation cascades |
| `insufficient_evidence` | bool | Hard block — prevents any conclusion |
| `insufficient_evidence_reason` | str | Explanation for hard block |
| `adjusted_reliability` | float | Source score after adversarial adjustment |
| `adjusted_consensus` | float | Consensus score after adversarial adjustment |
| `key_uncertainties` | list[str] | Each item adds uncertainty penalty in A9 |
| `overall_severity` | LensRating | Aggregate attack severity |

### Fallback chain
```
Gemini unavailable → _conservative_fallback()
  • overall_severity = moderate
  • adjusted_reliability = raw_avg × 0.8
  • adjusted_consensus = 0.5
  • insufficient_evidence = False
  • key_uncertainties = ["Adversarial critique could not be completed."]
```

---

## A9 — ERS Calibration  ★ Phase 5

**Phase:** 5 (sequential, after A8)  
**Type:** Sequential  
**LLM:** None — fully deterministic

### Input
```python
source_score:            float      # critique.adjusted_reliability
consensus_score:         float      # critique.adjusted_consensus
retrieval_relevance:     float      # avg Qdrant score from A2
contradiction_graph:     ContradictionGraph
applicability_report:    ApplicabilityReport
uncertainties:           list[str]  # critique.key_uncertainties
high_reliability_count:  int        # # of sources with score ≥ 0.7
```

### Output
```python
ers: ERSResult
```

### Formula

```
ERS_base = 0.45 × source_score
         + 0.35 × consensus_score
         + 0.20 × retrieval_relevance

contradiction_penalty = min(
    hard × 0.10 + partial × 0.05,
    0.30
)

applicability_penalty = min(
    (inapplicable / total) × 0.20,
    0.20
)

uncertainty_penalty = min(
    len(uncertainties) × 0.03,
    0.15
)

ERS = clamp(ERS_base − Σ(penalties), 0.0, 1.0)
```

### Confidence band formula

```
margin = 0.05
       + (hard_contradictions × 0.02)
       + (len(uncertainties) × 0.01)
       − (high_reliability_count × 0.005)

margin = clamp(margin, 0.02, 0.20)

lower = max(0.0, ERS − margin)
upper = min(1.0, ERS + margin)
```

### ERSResult fields

| Field | Source | Description |
|-------|--------|-------------|
| `score` | Formula | Final ERS 0.0–1.0 |
| `band` | Thresholds | High (≥0.70) · Medium (≥0.40) · Low (<0.40) |
| `confidence_lower` | Dynamic margin | Lower confidence bound |
| `confidence_upper` | Dynamic margin | Upper confidence bound |
| `source_score` | A8 output | adjusted_reliability |
| `consensus_score` | A8 output | adjusted_consensus |
| `retrieval_relevance` | A2 average | Average Qdrant similarity |
| `contradiction_penalty` | A6 graph | Computed contradiction deduction |
| `applicability_penalty` | A7 report | Computed applicability deduction |
| `uncertainty_penalty` | A8 uncertainties | Computed uncertainty deduction |
| `penalty_breakdown` | Detailed | Full per-component audit |
| `formula_trace` | Computed | Human-readable formula string |

---

## A10 — Response Assembly

**Phase:** 6  
**Type:** Sequential  
**LLM:** Gemini Pro

### Input
```python
query:                str
claims:               list[Claim]
ers:                  ERSResult
contradiction_graph:  ContradictionGraph
applicability_report: ApplicabilityReport
uncertainties:        list[str]
insufficient_evidence: bool
session_id:           str | None
```

### Output
```python
response: PipelineResponse = {
    answer:               str
    ers:                  ERSResult
    critique:             CritiqueOutput   # attached by pipeline orchestrator
    claims:               list[Claim]
    contradiction_graph:  ContradictionGraph
    applicability_report: ApplicabilityReport
    uncertainties:        list[str]
    insufficient_evidence: bool
    session_id:           str | None
}
```

### Answer structure
When `insufficient_evidence = False`:
1. Direct answer to the question
2. Key supporting evidence (claim references)
3. Contradictions and their significance
4. Confidence statement with ERS band

When `insufficient_evidence = True`:
1. INSUFFICIENT EVIDENCE statement
2. Reason (from A8)
3. What would be needed to resolve it

---

## A11 — Audit (Async)

**Phase:** 7  
**Type:** Async fire-and-forget  
**LLM:** None

### Input
```python
request_query: str
response:      PipelineResponse
trace_id:      str | None    # generated if not provided
```

### Output
```python
trace_id: str    # UUID of the audit record
```

### Written to
| Destination | Contents |
|-------------|---------|
| PostgreSQL `audit_traces` table | trace_id, timestamp, query, ers_score, ers_band, insufficient_evidence, claim_count, contradiction_count |
| LangSmith | Full trace including all agent inputs/outputs |

### Async behaviour
A11 is launched as `asyncio.create_task()` — it does not block the response. If A11 fails, it is logged but does not affect the pipeline response. Supports replay via `trace_id`.

---

## Pipeline API

### POST `/pipeline/query`

**Request:**
```json
{
  "query": "Does daily aspirin reduce cardiovascular risk in adults over 70?",
  "user_id": "user_abc123",
  "session_id": "sess_xyz789",
  "max_sources": 10
}
```

**Response:**
```json
{
  "answer": "Based on the available evidence...",
  "ers": {
    "score": 0.4985,
    "band": "Low",
    "confidence_lower": 0.4085,
    "confidence_upper": 0.5885,
    "source_score": 0.61,
    "consensus_score": 0.55,
    "retrieval_relevance": 0.74,
    "contradiction_penalty": 0.10,
    "applicability_penalty": 0.10,
    "uncertainty_penalty": 0.06,
    "penalty_breakdown": {
      "contradiction_edges_hard": 1,
      "contradiction_edges_partial": 0,
      "contradiction_penalty": 0.10,
      "inapplicable_source_count": 2,
      "total_source_count": 4,
      "applicability_penalty": 0.10,
      "uncertainty_count": 2,
      "uncertainty_penalty": 0.06,
      "total_penalty": 0.26
    },
    "formula_trace": "ERS = 0.45×0.610(src) + 0.35×0.550(con) + 0.20×0.740(ret) = 0.6150(base) − 0.1000(contra) − 0.1000(applic) − 0.0600(uncert) = 0.4550"
  },
  "critique": {
    "source_attack": {
      "rating": "moderate",
      "findings": ["Source 4 has potential pharmaceutical funding conflict."],
      "penalty_recommendation": 0.10
    },
    "scope_attack": {
      "rating": "severe",
      "findings": ["All sources studied adults 45–65; question targets 70+."],
      "penalty_recommendation": 0.25
    },
    "completeness_attack": {
      "rating": "moderate",
      "findings": ["No negative trials present in evidence set."],
      "penalty_recommendation": 0.10
    },
    "convergence_attack": {
      "rating": "minor",
      "findings": ["Sources appear reasonably independent."],
      "penalty_recommendation": 0.02
    },
    "insufficient_evidence": false,
    "insufficient_evidence_reason": null,
    "adjusted_reliability": 0.61,
    "adjusted_consensus": 0.55,
    "key_uncertainties": [
      "Applicability to 70+ population not established by any source.",
      "Conflict of interest in source 4 not resolved."
    ],
    "overall_severity": "moderate"
  },
  "claims": [...],
  "contradiction_graph": { "edges": [...] },
  "applicability_report": { "flags": [...], "overall_applicable": false },
  "uncertainties": ["Applicability to 70+ not established", "CoI in source 4"],
  "insufficient_evidence": false,
  "session_id": "sess_xyz789"
}
```

### GET `/health`

**Response:**
```json
{
  "status": "ok",
  "qdrant": true
}
```
