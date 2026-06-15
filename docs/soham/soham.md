# Soham — Features Developed

This file documents the technical architecture, operational pipeline, and internal logic for the components built under my development track: **A3 (Evidence Extraction)** and **A4 (Reliability)**.

---

## 1. A3 — Evidence Extraction Agent

### Purpose
Converts raw text documents (Research Papers, News Articles, Blogs) into a structured array of `Claim` objects. It is designed to preserve auditability (character spans) and extract structured entity descriptors (PIOT) for down-stream processing (A7, A8, A9).

### Pipeline Flow & Internal Logic

```mermaid
graph TD
    A[Documents Input] --> B[Source Type Retrieval]
    B --> C{Route Prompt}
    C -->|research_paper| D[Clinical Extraction Prompt]
    C -->|news_article| E[News/Expert Quote Prompt]
    C -->|blog / unknown| F[Fact vs Opinion Prompt]
    D & E & F --> G[LLM Structured Generation]
    G --> H[JSON Parser & Guardrail Validation]
    H --> I[Fuzzy Span Resolver]
    I --> J[Embedding Generation]
    J --> K[Cosine Similarity Deduplication]
    K --> L[Claim[] Output]
```

#### Step 1: Predefined Source Routing
Instead of using expensive LLM classification at run-time, A3 retrieves a predefined `source_type` from the document's payload metadata (mapping to the `SourceType` enum: `research_paper`, `news_article`, `blog`, or `unknown`).

#### Step 2: Specialized Extraction Prompts
Based on the routed source type, A3 calls the Gemini model using tailored prompts optimized to extract claims matching specific structural properties:
*   **Research Papers:** Focuses on scientific metrics, study attributes, and clinical methodology parameters.
*   **News Articles:** Focuses on quotes, public assertions, and factual reporting.
*   **Blogs:** Focuses on isolating core claims from opinionated filler and subjective commentary.

Each extraction prompt requests a flat JSON array of objects representing individual claims.

#### Step 3: Guardrail Validation & Span Resolution
For every extracted claim, the agent applies the following **soft constraints and guardrails**:
*   **Claims Per Document Cap:** Caps extracted claims to a maximum of 15 per document. This protects down-stream services from hallucination floods or excessively verbose articles.
*   **Text Length Constraints:** Filters out claims with a text length under 10 characters (too short/meaningless) and truncates claims over 300 characters to keep downstream comparisons fast and reliable.
*   **Confidence Floor:** Discards claims with LLM extraction confidence scores below `0.3` to weed out low-certainty statements and random noise.
*   **Fuzzy Span Resolver:** To avoid mapping failures from minor LLM punctuation or whitespace alterations, the span resolver attempts:
    1.  An exact match search.
    2.  A case-insensitive search.
    3.  A normalized whitespace relative-offset approximation.
*   **PIOT** entities: Extracts *Population*, *Intervention*, *Outcome*, and *Timeframe*.
*   **Claim Type:** Assigns `quantitative`, `qualitative`, `hedged`, or `methodological_caveat`.

#### Step 4: Embedding-Based Deduplication
To prevent artificial inflation of consensus scores downstream (e.g. in A5 Consensus), the agent:
1.  Computes content embeddings for each extracted claim text using the embedding service.
2.  Computes pairwise cosine similarity between claims.
3.  Prunes claims with a similarity higher than `0.92`, retaining the claim version with the higher LLM confidence score.

---

## 2. A4 — Reliability Agent

### Purpose
Calculates the credibility of the document source and the methodological rigor of the study design. It operates at the document level (outputs one `ReliabilityScore` per document) and does not judge the absolute factual truth of individual claims (which is handled downstream by A8/A9).

### Pipeline Flow & Internal Logic

```mermaid
graph TD
    A[Documents & A3 Claims] --> B[Pass 1: Deterministic Scoring]
    B --> C[Check URL / Metadata for CoI]
    C --> D[Calculate Exponential Recency Decay]
    D --> E{Escalate?}
    E -->|No| H[Calculate Composite Score]
    E -->|Yes| F[Pass 2: LLM Escalation]
    F --> G[CoI Severity & Study Design Extraction]
    G --> H
    H --> I[ReliabilityScore[] Output]
```

#### Pass 1: Deterministic Scoring (Fast & Auditable)
1.  **Base Score Allocation:** Assigned by predefined evidence hierarchy:
    *   Research Paper: `0.80`
    *   News Article: `0.40`
    *   Blog: `0.30`
    *   Unknown: `0.20`
2.  **Recency Exponential Decay:** Applies a temporal decay function using a configurable half-life of 5 years:
    $$\text{Recency Score} = 2^{-\frac{\text{Current Year} - \text{Pub Year}}{5}}$$
    
    *   **Temporal Guardrails (Soft Constraints):**
        *   *Future Year Clamping:* If a document has future-dated metadata (e.g. 2028 or 2035), the year is capped to `CURRENT_YEAR` to prevent negative age values.
        *   *Recency Floor:* Applies a floor of `0.3` to the recency score. This ensures landmark, high-quality historical studies (e.g., highly cited RCTs from 15-20 years ago) do not get completely zeroed out by temporal decay.
3.  **Deterministic CoI Flags:** Matches the domain against a static domain blocklist (e.g., promotional vendors, affiliate health sites) or checks metadata flags. If found, sets `CoISeverity` to `HIGH`.

#### Pass 2: LLM Escalation (Context-Aware)
If the document is a research paper or shows promotional linguistic indicators, the agent escalates to the LLM:
1.  **Conflict of Interest (CoI) Detection:** Prompts the LLM to inspect metadata and content snippets to determine commercial bias, tagging severity as `none`, `low` (affiliate links/minor bias), or `high` (sponsored study/direct sales).
2.  **Study Design Classification:** Inspects the methods text and the `methodological_caveat` claims extracted by A3. Classifies research papers into:
    *   `meta_analysis` (Multiplier: `1.25`)
    *   `systematic_review` (Multiplier: `1.20`)
    *   `rct` (Multiplier: `1.10`)
    *   `cohort` (Multiplier: `1.00`)
    *   `case_control` (Multiplier: `0.90`)
    *   `case_report` (Multiplier: `0.75`)
    *   `narrative_review` (Multiplier: `0.70`)
    *   `opinion` (Multiplier: `0.60`)

    *   **Fuzzy Enum Mapping Guardrail:** If the LLM generates a non-exact matches for study designs (e.g., "clinical trial", "editorial review"), the agent performs a fuzzy substring-matching check (mapping "clinical trial" to `rct` and "review" to `systematic_review` or `narrative_review`) before defaulting to `StudyDesign.NOT_APPLICABLE`.

#### Final Composite Score Calculation
The deterministic and escalated metrics are combined into a final reliability score between `0.0` and `1.0`:
$$\text{Adjusted Base} = \min(\text{Base Score} \times \text{Study Design Multiplier}, 1.0)$$
$$\text{Raw Score} = (0.6 \times \text{Adjusted Base} + 0.4 \times \text{Recency}) - \text{CoI Penalty}$$
$$\text{Final Score} = \max(0.0, \min(1.0, \text{Raw Score}))$$

*CoI Penalties: `none` = 0.0, `low` = 0.10, `high` = 0.25.*

---

## 3. Integration Mechanics

*   **Explicit Join Key:** A3 outputs claims mapped with `source_id`. A4 outputs document scores mapped with `source_id`.
*   **ERS Calculation:** When downstream agents (A9) calculate the Evidence Reliability Score, they perform a simple join:
    $$\text{Claim Reliability} = \text{ReliabilityScore}[\text{claim.source_id}]$$
*   **Boilerplate Isolation:** The entire data exchange uses clean schemas (`Claim`, `ReliabilityScore`) and imports only standard Pydantic models. This ensures no dependency conflicts when other features (A5, A6, A7, etc.) are integrated by the rest of the team.
