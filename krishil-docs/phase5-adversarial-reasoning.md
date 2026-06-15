# Phase 5 — Adversarial Reasoning

> Agents: **A8 Critique / Skeptic** → **A9 ERS Calibration**  
> File: `backend/agents/a8_critique.py` · `backend/agents/a9_ers_calibration.py`

---

## Why adversarial reasoning?

Phases 1–4 are constructive — they retrieve evidence, extract claims, and score components.  
Without an adversarial counterweight, those scores can compound optimistically:  
a source labelled "peer-reviewed" gets a high reliability score even if all such sources  
cite the same upstream paper, and even if the study population doesn't match the question.

Phase 5 is the adversarial counterweight. Its job is to find what is wrong.

---

## A8 — Critique / Skeptic

### Role in the pipeline

A8 is the last agent before the ERS formula. It receives all four Phase 4 outputs simultaneously and stress-tests them through four fixed lenses before any score is finalised.

**Critical constraint:** A8 does NOT receive a drafted answer. It receives only evidence metadata. This prevents anchoring — if A8 saw an answer it would decorate it, not attack it.

### Execution flow

```
A8.run(query, claims, reliability, contradiction_graph, applicability)
  │
  ├─ Step 1: Deterministic pre-checks (no LLM cost)
  │    ├─ < 2 claims?               → INSUFFICIENT_EVIDENCE immediately
  │    ├─ all sources < 0.4?        → INSUFFICIENT_EVIDENCE immediately
  │    ├─ zero applicable sources?  → INSUFFICIENT_EVIDENCE immediately
  │    └─ ≥3 hard contradictions + < 5 claims? → INSUFFICIENT_EVIDENCE
  │
  ├─ Step 2: Build structured user message
  │    └─ Formats all Phase 4 data into a compact, auditable text block
  │
  ├─ Step 3: Call Gemini Pro (JSON mode, adversarial system instruction)
  │    └─ System instruction is anchored at model level, not user content
  │    └─ Retries with exponential backoff (up to 3 attempts)
  │
  └─ Step 4: Parse + validate → CritiqueOutput
       └─ Falls back to conservative_fallback() if Gemini is unavailable
```

### The four fixed lenses

Each lens is applied in a single Gemini call. The model returns a structured JSON object with a `rating`, `findings` list, and `penalty_recommendation` for each.

---

#### Lens 1 — Source Attack

**What it probes:**
- Peer-review status and journal quality
- Sample sizes — are they sufficient to support the claim?
- Conflict of interest disclosures and funding sources
- Methodological rigour (RCT vs observational vs expert opinion)
- Publication bias toward positive results
- Replication history

**Why it matters:**  
A systematic review from a high-impact journal is categorically different from an expert opinion letter. The deterministic source-type scoring in A4 catches obvious cases, but CoI, funding bias, and methodological subtleties require LLM reasoning.

**Output example:**
```json
{
  "rating": "moderate",
  "findings": [
    "Two of four sources are funded by the intervention manufacturer — potential CoI.",
    "Largest study (n=340) is underpowered for the subgroup analysis being cited.",
    "No replication of primary finding in independent cohort."
  ],
  "penalty_recommendation": 0.15
}
```

---

#### Lens 2 — Scope / Applicability Attack

**What it probes:**
- Does the study population match the question population? (age, demographics, clinical profile)
- Is the measured timeframe relevant to the question's context?
- Are the outcomes reported the ones the question actually asks about?
- Is the intervention or exposure equivalent to what the question describes?

**Why it's a separate lens from A7:**  
A7 applies deterministic binary flags (population_match: true/false) using Gemini Flash.  
The Scope Attack in A8 applies qualitative adversarial pressure — it can identify *why* a source is only partially applicable, and flag cases A7 missed.

**Output example:**
```json
{
  "rating": "severe",
  "findings": [
    "All sources study adults aged 18–45; question targets elderly (65+) population.",
    "Primary outcome in sources is biomarker level; question asks about clinical endpoint."
  ],
  "penalty_recommendation": 0.25
}
```

---

#### Lens 3 — Completeness Attack

**What it probes:**
- What evidence is conspicuously absent?
- Are there known opposing studies not represented in the retrieved set?
- Systematic gaps: all sources from one geography, one time window, one research group?
- Would the conclusion change if the missing evidence were included?
- File-drawer problem: are negative results systematically missing?

**Why it matters:**  
Retrieval (A2) finds what is in the knowledge base. It cannot know what is missing. The Completeness Attack is the only agent that can flag absence-of-evidence as an evidence-quality signal.

**Output example:**
```json
{
  "rating": "moderate",
  "findings": [
    "All 4 sources are from high-income countries; no evidence from low/middle-income settings.",
    "Only post-2015 studies present — this intervention has a 20-year history; earlier evidence may contradict.",
    "No negative trials represented — classic publication bias signature."
  ],
  "penalty_recommendation": 0.12
}
```

---

#### Lens 4 — Convergence Attack

**What it probes:**
- Is apparent consensus genuine or illusory?
- Citation cascade: do all "agreeing" sources trace back to a single upstream paper?
- Researcher overlap: are "independent" studies from the same group?
- Methodological correlation: do all studies use the same instrument/protocol, creating correlated errors?
- Funding correlation: same sponsor → same direction of finding?

**Why it matters:**  
A5 (Consensus agent) measures semantic agreement using cosine similarity. High cosine similarity looks like consensus. But if three papers all cite the same RCT and reanalyse the same dataset, cosine similarity is high while independence is zero. The Convergence Attack catches this.

**Output example:**
```json
{
  "rating": "severe",
  "findings": [
    "Sources 2, 3, and 4 all cite Source 1 as the primary evidence base — citation cascade, not independent replication.",
    "Sources 1 and 3 share a principal investigator.",
    "All four studies use the same proprietary measurement instrument — correlated measurement error."
  ],
  "penalty_recommendation": 0.20
}
```

---

### INSUFFICIENT_EVIDENCE hard override

This is A8's highest-authority action. When emitted, it propagates to A10 (Response) as a hard block — no conclusion is drawn regardless of the ERS score.

**Pre-check conditions (deterministic, no LLM):**

| Condition | Threshold |
|-----------|-----------|
| Evidence base too thin | `< 2 independent claims` |
| All sources unreliable | `all source scores < 0.4` |
| Zero applicable sources | `all applicability flags inapplicable` |
| Unresolvable contradictions | `≥ 3 hard contradictions + < 5 claims` |

**LLM-triggered conditions (Gemini may also set this):**
- Publication bias so severe the real effect direction is unknowable
- The only applicable source has a direct conflict of interest

**Output when triggered:**
```json
{
  "insufficient_evidence": true,
  "insufficient_evidence_reason": "All 3 sources score below 0.4 reliability (avg: 0.31).",
  "adjusted_reliability": 0.0,
  "adjusted_consensus": 0.0,
  "overall_severity": "severe"
}
```

---

### CritiqueOutput schema

```python
class CritiqueOutput(BaseModel):
    source_attack:       LensAnalysis   # rating + findings + penalty_recommendation
    scope_attack:        LensAnalysis
    completeness_attack: LensAnalysis
    convergence_attack:  LensAnalysis

    insufficient_evidence:        bool
    insufficient_evidence_reason: Optional[str]

    adjusted_reliability: float   # source_score after adversarial adjustment
    adjusted_consensus:   float   # consensus_score after adversarial adjustment

    key_uncertainties: list[str]  # forwarded to A9 for uncertainty penalty
    overall_severity:  LensRating # severe | moderate | minor | clear
```

---

### Fallback behaviour

| Scenario | Behaviour |
|----------|-----------|
| Pre-check triggers | Build INSUFFICIENT_EVIDENCE output immediately, no LLM call |
| Gemini unavailable | `_conservative_fallback()` — moderate severity, 20% haircut on reliability, no INSUFFICIENT_EVIDENCE |
| Gemini returns unparseable output | Same as above |
| All retries exhausted | Same as above + error logged |

The fallback never crashes the pipeline. It penalises for the unknown.

---

## A9 — ERS Calibration

### Role in the pipeline

A9 receives A8's output (adjusted scores + uncertainties) and applies the canonical ERS formula. It is fully deterministic — no LLM calls. Every number is traceable.

### The ERS formula

```
ERS_base = 0.45 × source_score
         + 0.35 × consensus_score
         + 0.20 × retrieval_relevance
```

Where:
- `source_score` = `adjusted_reliability` from A8 (after adversarial pressure)
- `consensus_score` = `adjusted_consensus` from A8 (after adversarial pressure)
- `retrieval_relevance` = average Qdrant vector similarity score from A2

**Why these weights?**

| Weight | Rationale |
|--------|-----------|
| 0.45 — source | Source quality is the single largest determinant of evidence trustworthiness |
| 0.35 — consensus | Agreement across independent sources is the second strongest signal |
| 0.20 — retrieval | Retrieval relevance matters but is a retrieval artefact, not an evidence quality signal |

Weights must sum to 1.0 (enforced at agent init).

---

### Penalty tracks

Three independent penalty tracks are applied after the base score:

```
final_ERS = clamp( ERS_base − contradiction_penalty − applicability_penalty − uncertainty_penalty , 0.0, 1.0 )
```

#### Contradiction penalty

```
penalty = (hard_contradictions × 0.10) + (partial_contradictions × 0.05)
penalty = min(penalty, 0.30)   # cap
```

| Type | Per-edge penalty | Source |
|------|-----------------|--------|
| CONTRADICTS | 0.10 | A6 ContradictionGraph |
| PARTIAL_CONTRADICTION | 0.05 | A6 ContradictionGraph |
| Cap | 0.30 | Prevents single factor from dominating |

#### Applicability penalty

```
penalty = (inapplicable_sources / total_sources) × 0.20
penalty = min(penalty, 0.20)   # cap
```

A source is inapplicable if ANY of `population_match`, `timeframe_match`, `outcome_match` is `false`.

#### Uncertainty penalty

```
penalty = len(key_uncertainties) × 0.03
penalty = min(penalty, 0.15)   # cap
```

`key_uncertainties` comes from A8's critique output — each item the adversary flagged as a genuine unknown.

---

### Confidence band

The confidence band reflects how certain we are about the ERS score itself (meta-uncertainty), not about the evidence.

```
base_margin = 0.05

margin += hard_contradictions   × 0.02   # each hard contradiction widens the band
margin += len(uncertainties)    × 0.01   # each uncertainty widens the band
margin -= high_reliability_count × 0.005  # more reliable sources narrow the band

margin = clamp(margin, 0.02, 0.20)

confidence_lower = max(0.0, final_ERS − margin)
confidence_upper = min(1.0, final_ERS + margin)
```

**Interpretation:** An ERS of 0.62 with confidence band [0.55, 0.69] means: "We are confident the true score lies between 0.55 and 0.69." A wider band signals greater meta-uncertainty.

---

### Band thresholds

| Band | Threshold | Meaning |
|------|-----------|---------|
| High | ≥ 0.70 | Strong evidence, narrow band |
| Medium | 0.40–0.69 | Moderate evidence, use with caveats |
| Low | < 0.40 | Weak evidence, treat with scepticism |

---

### ERSResult schema

```python
class ERSResult(BaseModel):
    score:             float    # final ERS 0.0–1.0
    band:              ERSBand  # High | Medium | Low

    confidence_lower:  float    # dynamic lower bound
    confidence_upper:  float    # dynamic upper bound

    source_score:        float  # post-critique adjusted_reliability
    consensus_score:     float  # post-critique adjusted_consensus
    retrieval_relevance: float  # avg Qdrant score

    contradiction_penalty: float
    applicability_penalty: float
    uncertainty_penalty:   float

    penalty_breakdown: ERSPenaltyBreakdown  # full audit trail
    formula_trace:     str      # human-readable formula string
```

**`formula_trace` example:**
```
ERS = 0.45×0.720(src) + 0.35×0.610(con) + 0.20×0.830(ret) = 0.6985(base)
    − 0.1000(contra) − 0.0400(applic) − 0.0600(uncert) = 0.4985
```

---

### ERSPenaltyBreakdown schema

```python
class ERSPenaltyBreakdown(BaseModel):
    contradiction_edges_hard:    int
    contradiction_edges_partial: int
    contradiction_penalty:       float

    inapplicable_source_count:   int
    total_source_count:          int
    applicability_penalty:       float

    uncertainty_count:           int
    uncertainty_penalty:         float

    total_penalty:               float
```

---

## End-to-end example

**Input question:** "Does daily aspirin reduce cardiovascular risk in adults over 70?"

**Phase 4 inputs to A8:**
- 8 claims from 4 sources
- Reliability scores: [0.82, 0.71, 0.48, 0.35]
- 1 CONTRADICTS edge (aspirin benefit vs aspirin harm in elderly)
- 2 applicability flags (sources studied 45–65 age range, not 70+)

**A8 Critique output:**
- Source attack: `moderate` — one source has potential CoI (pharmaceutical funding)
- Scope attack: `severe` — both flagged sources studied 45–65, question targets 70+
- Completeness attack: `moderate` — no negative trials in set
- Convergence attack: `minor` — sources are reasonably independent
- `insufficient_evidence`: false
- `adjusted_reliability`: 0.61 (down from raw avg 0.59 with reweighting)
- `adjusted_consensus`: 0.55 (down from 0.71 due to convergence concerns)
- `key_uncertainties`: ["Applicability to 70+ not established", "CoI in source 4 not resolved"]

**A9 ERS Calibration:**
```
base   = 0.45×0.61 + 0.35×0.55 + 0.20×0.74 = 0.2745 + 0.1925 + 0.1480 = 0.6150
contra = 1 × 0.10 = 0.10   (1 hard contradiction)
applic = (2/4) × 0.20 = 0.10   (2 of 4 sources inapplicable)
uncert = 2 × 0.03 = 0.06   (2 key uncertainties)

final  = 0.6150 − 0.10 − 0.10 − 0.06 = 0.355 → Band: LOW

confidence band: 0.05 + 1×0.02 + 2×0.01 = 0.09 → [0.265, 0.445]
```

**Interpretation:** Despite the sources appearing moderately reliable in isolation, the scope mismatch and contradiction reduce the ERS to Low. The answer would carry a strong caveat about applicability to the 70+ population.
