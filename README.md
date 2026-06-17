## The final architecture: 11 agents

Here is the merged, definitive design:

**Phase 1 — Ingress (sequential)**
`A1 Ingestion` → GLiNER NER, PII redaction, prompt-injection filter, token budget enforcement, deduplication

**Phase 2 — Retrieval (sequential, within A2)**
`A2 Retrieval` → BM25 + Qdrant vector search → hybrid merge → cross-encoder rerank → `TopKDocuments`

**Phase 3 — Extraction (sequential)**
`A3 Evidence Extraction` → converts documents into `Claim[]` with typed annotations (quantitative, qualitative, hedged, methodological caveat)

**Phase 4 — Parallel scoring (fan-out, all 4 run simultaneously)**
`A4 Reliability` → deterministic source-type + recency scoring, LLM escalation for CoI/study-design edge cases → `ReliabilityScore[]`
`A5 Consensus` → pairwise cosine similarity matrix → `consensus_score` per claim cluster
`A6 Contradiction` → similarity-filtered pairs → LLM classification for logical conflicts only → `ContradictionGraph` (types: `SUPPORTS`, `CONTRADICTS`, `PARTIAL_CONTRADICTION`, `NOT_COMPARABLE`)
`A7 Applicability` → checks question population vs. evidence population, question timeframe vs. evidence timeframe, question outcome vs. evidence outcome → `ApplicabilityReport` with per-source flags

**Phase 5 — Adversarial reasoning (sequential)**
`A8 Critique / Skeptic` → receives all Phase 4 outputs. Operates from four fixed lenses: source attack, scope/applicability attack, completeness attack, convergence attack. Has authority to emit `INSUFFICIENT_EVIDENCE` as a hard override.
`A9 ERS Calibration` → computes `ERS = 0.45×source_score + 0.35×consensus_score + 0.20×retrieval_relevance` then applies contradiction penalty, applicability penalty, uncertainty penalty → final `0.0–1.0` score with confidence band

**Phase 6 — Output**
`A10 Response` → assembles final structured output: answer, ERS band (High/Medium/Low), support map, contradictions manifest, uncertainties list, `INSUFFICIENT_EVIDENCE` flag

**Phase 7 — Async post-processing**
`A11 Audit` → writes full trace to PostgreSQL + LangSmith. Supports replay and feedback ingestion.

The key structural improvements over both prior versions: Applicability is its own agent (not folded into Critique), contradiction detection is scoped to logical conflicts only (applicability failures stay in A7), and the ERS formula is computed in a dedicated calibration step after the Critique has had authority to modify inputs.

Now the diagrams — I'll do the full pipeline first, then zoom into the ERS formula and the Critique agent's internal logic.Now the ERS formula internals — this deserves its own diagram because it's what makes the system defensible:And finally the Critique agent's internal anatomy — this is the agent that will make or break the evaluation:Click any node in the diagrams to go deeper on that component. Here's where the synthesis lands:

---

## Key decisions and why

**Applicability as its own agent (A7), not folded into Critique.** Your doc's suggestion to add an Applicability Agent is correct, and the reason goes deeper than just "it addresses the hidden eval criteria." Applicability failures and logical contradictions are fundamentally different problems. A `population_mismatch` is not a contradiction — it means a source simply isn't about the right thing. If you lump it into the Contradiction agent, you conflate two different evidence problems and make A9's penalty system ambiguous. A7 runs in parallel with A4/A5/A6, outputs an `ApplicabilityReport` with per-source flags, and feeds a dedicated `applicability_penalty` into ERS.

**Contradiction Agent scoped to logical conflicts only.** The Contradiction agent uses the right flow (embed → similarity filter at `> 0.8` → LLM classify), but it should only classify genuine logical conflicts. Scope/population mismatches that look like contradictions should not enter the `ContradictionGraph` — they belong in A7. This keeps the penalty system clean: contradiction penalty reflects evidence quality, applicability penalty reflects evidence relevance.

**Critique agent input isolation is non-negotiable.** The Critique agent receives Phase 4 outputs — claims, scores, the contradiction graph, the applicability report. It does not receive any prior answer or synthesis. This is what makes the adversarial attack real. If you let the Critique see a drafted answer, it anchors on it and produces decoration, not adversarial pressure.

**ERS is a computed output, not a heuristic.** The formula gives you auditability. Every evaluator can trace exactly why a score is `0.61` — 45% came from moderately reliable sources, consensus was moderate, but a high-severity contradiction and two applicability penalties pulled it down. That's defensible. A black-box "confidence: Medium" is not.

**Security layer is built into A1, not sprinkled later.** PII redaction, injection filter, and token budget enforcement all happen at the ingestion boundary. Nothing downstream should ever assume its inputs are clean — but the architecture enforces that the attack surface is minimized at entry.
