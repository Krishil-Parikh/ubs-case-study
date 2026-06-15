Build a modern, production-ready **RAG chatbot frontend using Next.js**. The backend will be developed and integrated later using **FastAPI**, so keep the frontend modular and API-driven.

Requirements:

* Stateless chatbot (no conversation history or memory).
* ChatGPT-like interface with a query input and streaming AI responses.
* Stream responses token-by-token with Markdown and code block support.
* Display retrieved sources below each response, including **file name, relevance score, page number, and chunk ID**.
* Clicking a source should open the corresponding document at the **exact page/chunk** using metadata returned by the FastAPI backend.
* Show workflow progress (Retrieving Documents → Reranking → Generating Response).
* Gracefully handle errors (network failures, API errors, interrupted streams) with a **Retry** button that resumes from the last backend checkpoint instead of restarting the workflow, assuming the FastAPI backend supports checkpointing.
* Include loading states, auto-scroll, copy response button, responsive design, and light/dark mode.

Design the frontend to be clean, responsive, and easily extensible for future FastAPI integration, using best practices for Next.js and component-based architecture.

# Retrieval Agent Prompt

Retrieve relevant evidence using a hybrid retrieval strategy.

Responsibilities:

* BM25 lexical retrieval
* Qdrant semantic retrieval
* Cross-encoder reranking
* Metadata enrichment

Prepare evidence for:

* Reliability Agent
* Applicability Agent
* Consensus Agent
* Contradiction Agent

Do not perform reasoning.
Do not generate conclusions.
Only retrieve and structure evidence.

# Rugved — Phase 6: A10 Response Agent

> **Author**: Rugved  
> **Phase**: 6 — Output  
> **Agent**: A10 Response  
> **Status**: Implementation Complete

---

## Feature Description

Phase 6 is the **Output phase** of the ERS (Evidence Reliability Score) Evidence Pipeline. It is the final content-generation stage before the response reaches the user. The A10 Response Agent receives all upstream analysis — claims, reliability scores, consensus assessments, contradiction graphs, applicability reports, critique findings, and the computed ERS score — and assembles them into a structured, honest, and defensible answer.

### What This Phase Builds

1. **Evidence-Grounded Answer Synthesis** — An LLM-generated answer that is strictly grounded in the provided evidence claims, with inline citations (`[1]`, `[2]`, etc.) linking every assertion to its source claim.

2. **ERS-Adaptive Tone Control** — The answer's language and hedging automatically adjusts based on the ERS band:
   - **High (≥ 0.70)**: Confident, assertive language while still citing sources
   - **Medium (0.40–0.69)**: Hedged language ("evidence suggests", "findings indicate")
   - **Low (< 0.40)**: Strongly caveated, emphasizes unknowns, recommends seeking additional sources

3. **Support Map** — A structured mapping of which claims support which sections of the answer. Each entry includes the claim text, its source, a computed relevance score (blending claim confidence and source reliability), and the answer section it appears in.

4. **Contradictions Manifest** — Transforms the raw `ContradictionGraph` edges into human-readable entries with severity ratings (high/moderate/low) based on contradiction type and claim confidence levels.

5. **Structured Uncertainties** — Raw uncertainty strings from the Critique Agent are categorized (data gap, methodology, scope, temporal, population) and assessed for impact level using keyword heuristics and critique context.

6. **INSUFFICIENT_EVIDENCE Handling** — When the upstream Critique Agent flags insufficient evidence, A10 generates a dedicated "cannot answer" response that explains *why* the evidence is insufficient (using the four critique lenses: source attack, scope attack, completeness attack, convergence attack) and recommends what types of evidence would be needed.

7. **Response Metadata** — Source counts, claim counts, contradiction counts, applicability flag counts, ERS band, and generation model are attached to every response for auditability.

---

## Architecture Position

```
Phase 1 (Ingestion) → Phase 2 (Retrieval) → Phase 3 (Extraction)
    → Phase 4 (Reliability, Consensus, Contradiction, Applicability) [parallel]
    → Phase 5 (Critique, ERS Calibration) [sequential]
    → ★ Phase 6 (A10 Response) ← YOU ARE HERE
    → Phase 7 (Audit) [async, fire-and-forget]
```

A10 receives inputs from **all preceding phases** and produces the single `PipelineResponse` object that flows to the API layer and ultimately to the user.

---

## Agent Prompt

Below is the full system prompt used by the A10 Response Agent:

```
You are the Response Agent of the ERS Evidence Pipeline.
Your role is to synthesize evidence into a structured, honest, and defensible answer.

RULES:
1. Ground every statement in the provided claims. Use inline citations like [1], [2], etc.
   Each number corresponds to the claim index in the claims list (1-indexed).
2. NEVER fabricate information or go beyond the evidence provided.
3. Explicitly acknowledge contradictions — do not hide conflicting evidence.
4. When evidence is hedged or has methodological caveats, reflect that uncertainty in your language.
5. Structure your answer in clear sections with headings.
6. End with a "Limitations & Uncertainties" section summarizing key gaps.
```

### ERS-Adaptive Tone Modifiers

**HIGH Confidence (ERS ≥ 0.70)**:
```
The evidence is strong and largely convergent. Write with appropriate confidence,
but still cite sources and note any minor caveats.
```

**MEDIUM Confidence (ERS 0.40–0.69)**:
```
The evidence is mixed or has notable gaps. Use hedged language ("evidence suggests",
"based on available data", "findings indicate but are not conclusive").
Clearly separate well-supported claims from weaker ones.
```

**LOW Confidence (ERS < 0.40)**:
```
The evidence is weak, contradictory, or largely inapplicable. Use strongly hedged
language throughout. Emphasize what is NOT known. Recommend the user seek
additional authoritative sources before acting on this information.
```

### Insufficient Evidence Override

```
CRITICAL: The evidence is INSUFFICIENT to support any conclusion.

The upstream Critique Agent has determined that the available evidence cannot
support a reliable answer to this question. Explain WHY the evidence is
insufficient using the critique findings below, and recommend what types of
evidence would be needed to answer this question properly.
```

---

## Input / Output Contract

### Inputs (from upstream agents)

| Input | Source Agent | Type |
|-------|-------------|------|
| `query` | A1 Ingestion | `str` — the cleaned, sanitized user question |
| `claims` | A3 Extraction | `list[Claim]` — extracted evidence claims with type annotations |
| `ers` | A9 ERS Calibration | `ERSResult` — computed score, band, penalties |
| `contradiction_graph` | A6 Contradiction | `ContradictionGraph` — edges between conflicting claims |
| `applicability_report` | A7 Applicability | `ApplicabilityReport` — per-source applicability flags |
| `uncertainties` | A8 Critique | `list[str]` — key uncertainties identified by adversarial review |
| `insufficient_evidence` | A8 Critique | `bool` — hard override flag |
| `reliability` | A4 Reliability | `list[ReliabilityScore]` — per-source reliability assessments |
| `critique` | A8 Critique | `dict` — full critique output with four attack lenses |

### Output

`PipelineResponse` with the following fields:

| Field | Type | Description |
|-------|------|-------------|
| `answer` | `str` | Full synthesized answer with inline citations |
| `ers` | `ERSResult` | Pass-through of the ERS computation |
| `claims` | `list[Claim]` | Pass-through of all evidence claims |
| `contradiction_graph` | `ContradictionGraph` | Pass-through of contradiction analysis |
| `applicability_report` | `ApplicabilityReport` | Pass-through of applicability analysis |
| `uncertainties` | `list[str]` | Pass-through of raw uncertainties |
| `insufficient_evidence` | `bool` | Whether evidence was deemed insufficient |
| `answer_sections` | `list[AnswerSection]` | Parsed answer sections with headings and cited claims |
| `support_map` | `list[SupportMapEntry]` | Claim-to-answer mapping with relevance scores |
| `contradictions_manifest` | `list[ContradictionManifestEntry]` | Human-readable contradiction summaries |
| `structured_uncertainties` | `list[UncertaintyEntry]` | Categorized and impact-assessed uncertainties |
| `metadata` | `ResponseMetadata` | Generation metadata for auditability |



## Key Design Decisions

1. **ERS-adaptive tone over uniform answers**: A static prompt produces answers that are either always confident or always hedged. Adapting the system prompt based on the ERS band ensures the answer's certainty claims match the evidence quality.

2. **Citation-first architecture**: Every statement must trace to a `[N]` citation. The support map then resolves these to `claim_id` and `source_id` pairs, making the entire answer auditable.

3. **Severity-rated contradictions**: Not all contradictions are equal. A direct `CONTRADICTS` between two high-confidence claims is a "high" severity event; a `PARTIAL_CONTRADICTION` between low-confidence claims is "low". This helps downstream consumers (frontend, auditors) prioritize what to surface.

4. **Keyword-based uncertainty classification over LLM classification**: Using keyword heuristics instead of another LLM call to categorize uncertainties is a deliberate latency/cost trade-off. The Critique Agent already used an LLM to identify these uncertainties; re-classifying them deterministically avoids a redundant inference.

5. **Backward-compatible schema expansion**: All new `PipelineResponse` fields have defaults, so existing API consumers are not broken.



# Soham — Prompt Log

---

## Prompt 1
Before we start building in the backend make sure every prompt after this is stored in `soham/soham_prompts.md` and the feature that was developed in `soham/soham.md`.

## Prompt 2
Keep only prompts in the `soham/soham_prompts.md` — no timestamp or the action taken.

## Prompt 3
Using the `soham/feature.md` and `backend/agents/a3_extraction.py`, `backend/agents/a4_reliability.py` boilerplate code develop the logic for proper extraction based on the claim in the doc and for the reliability ensure that mapping is done in an accurate manner. Make boilerplate code that can be merged later with other features which are to be made by other members of my team.

## Prompt 4
Write schemas only for A3 and A4 as of now nothing else.

## Prompt 5
1) source will be predefined no need to get it from the llm
2) Optimize the other system prompts 
3) Update soham/soham.md to give a detailed description of what is the functioning of a3 and a4

## Prompt 6
add soft contrainsts as guardrails as well

## Prompt 7
`backend/models/schemas.py` is common for all so that will be configured later based on all agent files so keep it default which was pulled , remove changes by us DO NOT CHANGE `backend/agents/a3_extraction.py`, `backend/agents/a4_reliability.py`

---
