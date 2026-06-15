# ERS Evidence Evaluation Pipeline — System Documentation

> **Author:** Krishil Parikh  
> **Stack:** Python 3.11 · FastAPI · Gemini 1.5 Pro · Qdrant · React + Vite

---

## What this system does

The ERS (Evidence Reliability Score) Pipeline evaluates the quality and trustworthiness of evidence in response to a research question. It answers: *"How much should I trust the evidence behind this conclusion?"*

Given a natural-language research question, the pipeline:
1. Sanitises and validates the input
2. Retrieves relevant documents from a Qdrant vector store
3. Extracts typed claims from those documents
4. Scores each source for reliability, consensus, contradiction, and applicability — in parallel
5. Subjects all scores to adversarial critique through four attack lenses
6. Computes a final 0.0–1.0 ERS score using a transparent formula
7. Generates a structured answer with full provenance
8. Asynchronously logs everything for audit and replay

The result is not just an answer — it is an evidence quality certificate with a traceable audit trail.

---

## Architecture — 11 Agents in 7 Phases

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Phase 1 — Ingress (sequential)                                             │
│  A1 Ingestion → PII redaction · injection filter · token budget · dedup    │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │ clean_query
┌────────────────────────────────▼────────────────────────────────────────────┐
│  Phase 2 — Retrieval (sequential)                                           │
│  A2 Retrieval → BM25 + Qdrant vector → hybrid merge → cross-encoder rerank │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │ TopKDocuments
┌────────────────────────────────▼────────────────────────────────────────────┐
│  Phase 3 — Extraction (sequential)                                          │
│  A3 Extraction → Claim[] with typed annotations                             │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │ Claim[]
┌────────────────────────────────▼────────────────────────────────────────────┐
│  Phase 4 — Parallel scoring (fan-out)                                       │
│  A4 Reliability ───────────────────────────────► ReliabilityScore[]        │
│  A5 Consensus ──────────────────────────────────► consensus_score: float   │
│  A6 Contradiction ──────────────────────────────► ContradictionGraph       │
│  A7 Applicability ──────────────────────────────► ApplicabilityReport      │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │ all Phase 4 outputs
┌────────────────────────────────▼────────────────────────────────────────────┐
│  Phase 5 — Adversarial reasoning (sequential)                               │
│  A8 Critique / Skeptic                                                      │
│    └─ source attack · scope attack · completeness attack · convergence      │
│    └─ INSUFFICIENT_EVIDENCE hard override                                   │
│    └─► CritiqueOutput (adjusted scores + uncertainties)                    │
│  A9 ERS Calibration                                                         │
│    └─ ERS = 0.45×src + 0.35×con + 0.20×ret − Σ(penalties)                │
│    └─► ERSResult (score · band · confidence band · formula trace)          │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │ ERSResult + CritiqueOutput
┌────────────────────────────────▼────────────────────────────────────────────┐
│  Phase 6 — Output (sequential)                                              │
│  A10 Response → structured answer + ERS band + support map                 │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │ PipelineResponse
┌────────────────────────────────▼────────────────────────────────────────────┐
│  Phase 7 — Async post-processing                                            │
│  A11 Audit → PostgreSQL trace + LangSmith (fire-and-forget)                │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
ubs-case-study/
├── backend/
│   ├── agents/
│   │   ├── a1_ingestion.py        Phase 1 — sanitise input
│   │   ├── a2_retrieval.py        Phase 2 — BM25 + Qdrant + rerank
│   │   ├── a3_extraction.py       Phase 3 — extract typed claims
│   │   ├── a4_reliability.py      Phase 4 — source reliability scoring
│   │   ├── a5_consensus.py        Phase 4 — cosine consensus matrix
│   │   ├── a6_contradiction.py    Phase 4 — logical contradiction detection
│   │   ├── a7_applicability.py    Phase 4 — scope/population/timeframe checks
│   │   ├── a8_critique.py         Phase 5 — adversarial 4-lens critique  ★
│   │   ├── a9_ers_calibration.py  Phase 5 — ERS formula + penalties       ★
│   │   ├── a10_response.py        Phase 6 — final answer assembly
│   │   └── a11_audit.py           Phase 7 — async audit logging
│   ├── api/routes/
│   │   ├── pipeline.py            POST /pipeline/query
│   │   └── health.py              GET /health
│   ├── config/settings.py         Pydantic settings (reads .env)
│   ├── core/
│   │   ├── logging_config.py      Structured JSON + console logging
│   │   └── pipeline.py            Orchestrator
│   ├── models/schemas.py          All Pydantic types
│   ├── services/
│   │   ├── gemini_service.py      Gemini Pro/Flash + embeddings + retry
│   │   └── qdrant_service.py      Qdrant client wrapper
│   ├── main.py                    FastAPI app entry
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── services/api.ts        Typed Axios client
│   │   ├── hooks/usePipeline.ts   React state hook
│   │   ├── components/
│   │   │   ├── QueryForm.tsx
│   │   │   ├── ERSBadge.tsx
│   │   │   └── ResultPanel.tsx
│   │   └── pages/Home.tsx
│   ├── index.html
│   ├── package.json
│   └── vite.config.ts
└── krishil-docs/                  ← you are here
    ├── README.md                  This file
    ├── phase5-adversarial-reasoning.md
    ├── system-prompts.md
    └── agent-io-reference.md
```

---

## Quick Start

### Backend
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt

# Copy and fill in your keys:
cp .env.example .env

uvicorn backend.main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev                     # http://localhost:3000
```

### Environment variables (`.env`)
```
QDRANT_URL=https://1e14cac1-d310-42c5-a4a9-78b69a22f909.sa-east-1-0.aws.cloud.qdrant.io:6333
QDRANT_API_KEY=<your qdrant key>
GEMINI_API_KEY=<your gemini key>
DEBUG=false
LOG_LEVEL=INFO
```

---

## ERS Score Interpretation

| Band   | Score Range | Meaning |
|--------|-------------|---------|
| High   | 0.70 – 1.00 | Strong, consistent, applicable evidence. Conclusions are defensible. |
| Medium | 0.40 – 0.69 | Moderate evidence with some gaps or contradictions. Use with caveats. |
| Low    | 0.00 – 0.39 | Weak, conflicting, or inapplicable evidence. Treat conclusions with scepticism. |

A score of `INSUFFICIENT_EVIDENCE` is a hard override that blocks any conclusion regardless of the numeric score.

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Applicability is a separate agent (A7), not folded into Critique | Population mismatches and logical contradictions are fundamentally different problems. Conflating them makes the penalty system ambiguous. |
| Contradiction agent scoped to logical conflicts only | Scope/population mismatches that look like contradictions belong in A7, not the ContradictionGraph. Keeps penalty tracks clean. |
| Critique (A8) receives Phase 4 outputs — not a drafted answer | Input isolation prevents anchoring. If A8 saw a draft answer it would decorate, not attack. |
| ERS computed in a dedicated calibration step (A9) | Every evaluator can trace exactly why a score is 0.61. A black-box "Medium" is not defensible. |
| Security layer built into A1, not sprinkled later | Attack surface is minimised at the entry boundary. |

---

## Documentation Index

| File | Contents |
|------|----------|
| `phase5-adversarial-reasoning.md` | Deep dive into A8 Critique and A9 ERS Calibration — design rationale, algorithm, edge cases |
| `system-prompts.md` | Every system instruction and user message template with annotation |
| `agent-io-reference.md` | Complete input/output specification for all 11 agents |
