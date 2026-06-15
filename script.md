# ERS Evidence Evaluation Pipeline
## Presentation Playbook & Script

This document is a comprehensive guide and presentation script for a **6-member team**. Instead of slides, this script is designed for presenting directly from the main presentation document. It details the complete thought process, architecture layers, agents, tools, and LLM distribution, without complex equations or local file paths.

---

# PART 1: The Presentation Script (10-15 Minutes)

---

### Member 1: Introduction & The Core Problem
**Time Allocation: 2 Minutes**

*(Directing attention to the title of the presentation document)*
**[Speaker: Member 1]**
> "Hello everyone. Today, our team is presenting the ERS—or Evidence Reliability Score—Pipeline. We will be walking you directly through our system document.
> 
> Let’s start with a simple problem. Imagine you ask a standard enterprise AI assistant: *'Are our banking systems vulnerable to the latest voice-cloning deepfakes?'*
> 
> The AI searches your files, finds a whitepaper from your security vendor, and confidently says: *'No. Our vendor guarantees 100% liveness detection.'* You trust this answer. Two weeks later, attackers bypass your voice system using cloned voice clips. Why did the AI fail? Because it blindly trusted a biased marketing document and ignored a recent security news report.
> 
> Traditional AI search systems—often called RAG—are naively optimistic. They treat all search results as absolute truth. They cannot identify biased advertising, outdated files, or conflicting claims."

*(Directing attention to Section 1: Problem Statement)*
**[Speaker: Member 1]**
> "As you can see in Section 1 of our presentation document, we designed our system to solve five core vulnerabilities in standard AI search:
> 1. **Mixed Quality**: Treating an unverified blog post with the same trust as a peer-reviewed research study.
> 2. **Illusory Agreement**: Believing something is true just because multiple articles copy and paste the same claim (citation cascade).
> 3. **Hidden Contradictions**: Smoothing over logical conflicts instead of highlighting them to the user.
> 4. **Outdated Information**: Using old rules (like SMS-OTP security from 2021) in a modern threat environment.
> 5. **Scope Mismatch**: Assuming research tested on healthy young adults applies to older demographics.
> 
> To solve this, we built a modular **11-agent pipeline executed across 7 phases**. It evaluates sources, calculates an Evidence Reliability Score, and generates a structured answer. 
> 
> I will now hand over to [Member 2] to explain our evaluation dataset and how we engineered a test harness to validate this system."

---

### Member 2: The Data Layer & Test Harness
**Time Allocation: 2 Minutes**

*(Directing attention to Section 8: Actual target, harness and assumptions of this project)*
**[Speaker: Member 2]**
> "Thank you, [Member 1]. To prove that our pipeline can handle real-world challenges, we built a custom dataset focused on mobile banking security. Scroll down to Section 8, and you will see how we populated our database with simulated documents designed to test specific vulnerabilities:
> 
> * **Wikipedia Pages**: These provide unbiased, standard definitions of security terms.
> * **Research Papers**: Technical articles containing error rates. We deliberately made some files outdated (pre-2021) and limited some studies to specific populations (like identical twins) to test if our system flags them as mismatches.
> * **News & Breach Reports**: Articles detailing real security failures, written with high emotional intensity to test if the system filters out drama.
> * **Security Forums & Blogs**: Informal posts containing anecdotal noise and overconfident opinions.
> * **Vendor Whitepapers**: Highly biased marketing materials asserting perfect security, acting as a bias trap."

*(Directing attention to the Test Harness (Synthetic Corpus Traps) subsection)*
**[Speaker: Member 2]**
> "We generated these documents using target prompts. For example, we told our generator:
> 
> *'Act as a marketing director... write promotional claims asserting zero percent failure. This will serve as a commercial bias trap.'*
> 
> By building this dataset, we created a validation benchmark. A naive AI search system will blindly trust the vendor claims. Our system must identify the commercial bias, down-weight the outdated research, flag the population mismatches, and report any contradictions.
> 
> Now, [Member 3] will explain how a user's question enters the system and how we retrieve and extract information."

---

### Member 3: Ingress, Retrieval, & Extraction Layers
**Time Allocation: 2 Minutes**

*(Directing attention to Section 2: Our proposed solution and Section 4: End-to-end flow of the system)*
**[Speaker: Member 3]**
> "Thank you, [Member 2]. Let's walk through how a question moves through the initial layers of our architecture.
> 
> **Phase 1: Ingestion** is managed by **Agent 1 (A1 Ingestion)**. As shown in Section 2, this layer cleans the user's question, masks private data (like names or emails), and screens for prompt injection attacks.
> 
> **Phase 2: Retrieval** is handled by **Agent 2 (A2 Retrieval)**. Standard vector search matches concepts but often misses exact technical keywords. To solve this, we run a hybrid search: we use the **Qdrant Vector Database** for semantic concepts, and a **BM25 Lexical Index** for exact keyword matches. We combine these results and rerank them using a local **Cross-Encoder Model** to place the most relevant documents at the top. If the reranking model fails, the system automatically falls back to the merged order to prevent a crash."

*(Directing attention to Section 4: End-to-end flow of the system sequence steps 5-6)*
**[Speaker: Member 3]**
> "**Phase 3: Extraction** is managed by **Agent 3 (A3 Extraction)**. This agent uses the fast **Gemini 1.5 Flash** model. 
> 
> Instead of using a single general prompt, A3 checks the document type. It routes research papers to a technical prompt, news to a factual prompt, and blogs to an opinion-filtering prompt. It extracts:
> * **PIOT Details**: Population, Intervention, Outcome, and Timeframe.
> * **Claim Type**: Categorized as numeric, directional, hedged, or methodological caveats.
> * **Exact Spans**: The character positions where the claim is located in the text, ensuring full auditability.
> 
> Finally, A3 runs an embedding check to deduplicate claims. If two papers state the same finding, A3 keeps only the highest-confidence claim, preventing redundant entries from inflating consensus.
> 
> I will now hand over to [Member 4] to explain our parallel scoring layer."

---

### Member 4: The Parallel Scoring Layer
**Time Allocation: 2 Minutes**

*(Directing attention to Section 5: Complete end-to-end system architecture flowchart)*
**[Speaker: Member 4]**
> "Thank you, [Member 3]. Once claims are extracted, we enter **Phase 4: Parallel Scoring**. If you look at Section 5, our architecture flowchart displays a parallel group of agents. To save time, we run these four specialized agents concurrently using asynchronous Python threads.
> 
> * **Agent 4 (A4 Reliability)** rates source credibility. It assigns base scores based on document type (research papers get high scores; blogs get low scores). It then applies a **recency decay calculation**, lowering scores for older documents. If a document has potential conflicts of interest, A4 escalates to **Gemini 1.5 Flash** to identify commercial bias and deduct a penalty.
> * **Agent 5 (A5 Consensus)** measures agreement. It generates embeddings for the claims and uses a mathematical matrix to calculate the average similarity. If most claims point in the same direction, the consensus score is high."

*(Directing attention to Section 6: Complete AI and agent workflow and architecture)*
**[Speaker: Member 4]**
> "Section 6 highlights the details of the next two scoring agents:
> * **Agent 6 (A6 Contradiction)** detects logical conflicts. To save API costs, we only compare claims that are semantically similar. We use **Gemini 1.5 Flash** to classify their relationship (Supports, Contradicts, Partially Contradicts). Crucially, the prompt instructs the model to ignore demographic mismatches here, as they are not logical contradictions.
> * **Agent 7 (A7 Applicability)** evaluates relevance. It uses **Gemini 1.5 Flash** to verify if the study population, timeframe, and measured outcome match the user's question.
> 
> By dividing these tasks, each agent evaluates a single dimension, and the entire parallel scoring phase completes in less than a second.
> 
> I will now pass it to [Member 5] to explain our critique and calibration layers."

---

### Member 5: Adversarial Critique & ERS Calibration Layers
**Time Allocation: 2 Minutes**

*(Directing attention to Phase 5: Adversarial Reasoning in Section 6)*
**[Speaker: Member 5]**
> "Thank you, [Member 4]. We now enter **Phase 5: Adversarial Reasoning**, which is the defensive heart of our pipeline.
> 
> **Agent 8 (A8 Critique)** acts as an adversarial review board. To avoid bias, it does not see the generated answer. It only reviews the raw scores, claims, contradictions, and applicability reports.
> 
> As detailed in Section 6 under A8, it uses the reasoning-focused **Gemini 1.5 Pro** model to evaluate the evidence through **four critical lenses**:
> 1. **Source Attack**: Evaluates sample sizes and conflicts of interest.
> 2. **Scope Attack**: Identifies demographic mismatches missed by the scoring agents.
> 3. **Completeness Attack**: Flags what information is missing or if there is research bias.
> 4. **Convergence Attack**: Exposes citation cascades, showing if multiple sources are simply repeating one upstream study.
> 
> If the evidence is too thin, or if all sources are unreliable, A8 triggers a **hard override** called 'Insufficient Evidence', halting the pipeline."

*(Directing attention to A9 ERS Calibration Agent details in Section 6)*
**[Speaker: Member 5]**
> "If A8 approves the evidence, **Agent 9 (A9 ERS Calibration)** computes the final score. A9 does not use an LLM; it is fully deterministic.
> 
> As outlined here, it starts with a base calculation:
> * **45%** comes from the Source Reliability score.
> * **35%** comes from the Consensus score.
> * **20%** comes from the Search Relevance score.
> 
> It then subtracts penalties:
> * A **Contradiction Penalty** for logical conflicts.
> * An **Applicability Penalty** for irrelevant populations or outcomes.
> * An **Uncertainty Penalty** for items flagged by the critique agent.
> 
> A9 also calculates a dynamic **Confidence Band**. If the sources are highly reliable, the band narrows, indicating high confidence. If there are contradictions or uncertainties, the band widens, warning the user of score volatility.
> 
> I will now pass it to [Member 6] to explain our response and audit layers."

---

### Member 6: Response Synthesis, Auditing, & Future Steps
**Time Allocation: 2 Minutes**

*(Directing attention to Phase 6: Output and Phase 7: Async Post-processing in Section 6)*
**[Speaker: Member 6]**
> "Thank you, [Member 5]. Once the score is calculated, **Agent 10 (A10 Response)** generates the final answer using the advanced **Gemini 1.5 Pro** model.
> 
> To prevent hallucinations, the prompt limits A10 to the claims extracted in Phase 3. As you can see, it adjusts its language based on the ERS score:
> * **High Confidence**: The AI writes assertively.
> * **Medium Confidence**: The AI uses cautious language, like *'evidence suggests'* or *'findings indicate'*.
> * **Low Confidence**: The AI writes with strong caveats and warns the user to consult other sources.
> 
> If the 'Insufficient Evidence' flag is triggered, A10 generates an explanation detailing *why* the data is insufficient and what information is missing."

*(Directing attention to Section 7: Production-grade requirements meeting)*
**[Speaker: Member 6]**
> "If you look at Section 7, we address our production standards:
> 
> * **Security & Privacy**: Masking customer data at ingestion.
> * **Audit Trails**: Saving every score component to a database.
> * **Resiliency**: If a complex ranking engine goes offline, the system falls back to standard rankings.
> 
> Finally, **Agent 11 (A11 Audit)** logs the query and the complete evaluation details asynchronously to a **PostgreSQL database** and **LangSmith** in a background task, ensuring the user experiences no performance delay.
> 
> By decomposing the search and evaluation workflow into specialized agents, we replace opaque black-box generation with a transparent, auditable, and self-critiquing evaluation engine.
> 
> Thank you, and we are happy to take your questions."

---

# PART 2: System Architecture & Agent Ideology

Here is a clear, simple guide to each layer, the tools used, the agent mechanics, and the LLM distribution.

## 1. Technological Layers

```
┌────────────────────────────────────────────────────────┐
│                    CLIENT LAYER                        │
│  React (Vite) Frontend - Glassmorphic Dark-Mode UI     │
└──────────────────────────┬─────────────────────────────┘
                           │ API Call
┌──────────────────────────▼─────────────────────────────┐
│                      API LAYER                         │
│  FastAPI (Python 3.11) - Handles Routing & CORS        │
└──────────────────────────┬─────────────────────────────┘
                           │ Pipeline Request
┌──────────────────────────▼─────────────────────────────┐
│                    ENGINE CORE                         │
│  EvidencePipeline Orchestrator - Coordinates Agents    │
└──────────────────────────┬─────────────────────────────┘
                           │ Data Store Queries / LLM API
┌──────────────────────────▼─────────────────────────────┐
│                INFRASTRUCTURE LAYER                    │
│  • Qdrant (Vector DB)       • Gemini API (Pro/Flash)   │
│  • Cross-Encoder Model      • PostgreSQL & LangSmith   │
└────────────────────────────────────────────────────────┘
```

* **Client Layer**: A single-page web app built with React, Vite, and TypeScript. It features a dashboard showing the ERS score, confidence band, citations map, and contradiction warnings. It uses plain CSS for consistent styling.
* **API Layer**: Built with FastAPI. It exposes a POST endpoint to submit research queries, runs validation checks using Pydantic, and returns structured JSON responses.
* **Engine Core**: A Python class that runs the 11 agents in sequence, passing data between steps.
* **Infrastructure Layer**: Performs vector storage (Qdrant), keyword mapping (BM25), deep ranking (Cross-Encoder), LLM reasoning (Gemini API), and database logging (PostgreSQL & LangSmith).

---

## 2. LLM Distribution Table (Which model is used & Why)

We use two models from the Google Gemini family, selecting the appropriate tier for each agent to optimize speed, cost, and reasoning quality:

| Agent | Model | Type | Why this model was chosen? |
| :--- | :--- | :--- | :--- |
| **A1 Ingestion** | None | Local Code | Performs local checks (regular expressions, character limits, token counting) for maximum speed and security. |
| **A2 Retrieval** | None | Local/Qdrant | Queries Qdrant and runs a BM25 index. The reranker runs on the local CPU/GPU for instant similarity scoring. |
| **A3 Extraction** | **Gemini 1.5 Flash** | API | Extraction is a pattern-matching task. Flash is fast, cost-effective, and handles JSON structure generation efficiently. |
| **A4 Reliability** | **Gemini 1.5 Flash** | API (Escalation) | Used only when metadata is missing to classify study types or verify conflicts of interest. Flash minimizes latency. |
| **A5 Consensus** | None | Local Code | Calculates a mathematical average using NumPy in-memory vector calculations. No LLM is required. |
| **A6 Contradiction** | **Gemini 1.5 Flash** | API | Classifies pair relationships (Supports vs Contradicts) using a simple structural classification prompt. Flash keeps costs low. |
| **A7 Applicability** | **Gemini 1.5 Flash** | API | Evaluates binary indicators (`population_match`, `timeframe_match`, `outcome_match`) against a short excerpt. Flash is sufficient. |
| **A8 Critique** | **Gemini 1.5 Pro** | API | Requires advanced reasoning, contextual logic, and critical analysis to evaluate evidence gaps and identify citation cascades. |
| **A9 Calibration** | None | Local Code | Performs deterministic arithmetic calculations (weights and penalty subtractions) in Python, ensuring repeatable scores. |
| **A10 Response** | **Gemini 1.5 Pro** | API | High-quality synthesis, inline citation referencing, and tone control adjustments require Pro's instruction-following capabilities. |
| **A11 Audit** | None | Local Code | Connects to PostgreSQL and LangSmith databases asynchronously using background tasks. |

---

## 3. Agent Ideology (Why and How)

### Phase 1: Ingress
* **A1 Ingestion Agent**
  * *Why*: Protects downstream LLMs from attacks and prevents formatting failures.
  * *How*: Uses local code to strip names, emails, and IPs (PII Redaction), flags malicious inputs (Prompt Injection Filter), and enforces character limits.

### Phase 2: Retrieval
* **A2 Retrieval Agent**
  * *Why*: Standard search algorithms often miss contextual details. Hybrid retrieval combines semantic and keyword search.
  * *How*: Queries Qdrant vectors and BM25 keywords in parallel, merges results using Reciprocal Rank Fusion, and reranks them using a local Cross-Encoder transformer model.

### Phase 3: Evidence Extraction
* **A3 Evidence Extraction Agent**
  * *Why*: Evaluators need to audit claims at the sentence level, not the document level.
  * *How*: Routes text to document-specific prompts using **Gemini 1.5 Flash** to extract claims containing Population, Intervention, Outcome, and Timeframe tags. It records character start and end positions, and runs embedding similarity comparisons to prune duplicate claims.

### Phase 4: Parallel Scoring
* **A4 Reliability Agent**
  * *Why*: High-quality research is more trustworthy than a blog, and older security guidelines decay over time.
  * *How*: Assigns base scores to study types (e.g., Systematic reviews get 0.8; blogs get 0.3) and applies a recency decay calculation. It escalates to **Gemini 1.5 Flash** to identify commercial conflicts of interest and reduce scores.
* **A5 Consensus Agent**
  * *Why*: If independent sources agree on a finding, the finding is more trustworthy.
  * *How*: Computes an average similarity score across all claims using NumPy vector calculations.
* **A6 Contradiction Agent**
  * *Why*: Contradictory evidence indicates scientific disagreement or emerging exploits.
  * *How*: Pre-filters claims with high similarity and uses **Gemini 1.5 Flash** to classify conflicts, ignoring differences in demographics.
* **A7 Applicability Agent**
  * *Why*: A study that does not address your demographic population is not relevant, even if it is reliable.
  * *How*: Uses **Gemini 1.5 Flash** to verify if the study population, timeline, and measured outcomes match the query.

### Phase 5: Adversarial Reasoning & Calibration
* **A8 Critique / Skeptic Agent**
  * *Why*: Scoring metrics can be optimistically biased. An adversarial critic is needed to identify gaps.
  * *How*: Uses **Gemini 1.5 Pro** to review the claims, reliability scores, contradictions, and applicability reports. It evaluates the data through four lenses (Source, Scope, Completeness, Convergence) and applies score adjustments, triggering an 'Insufficient Evidence' override if necessary.
* **A9 ERS Calibration Agent**
  * *Why*: A transparent, repeatable math formula is needed so compliance officers can audit the results.
  * *How*: Runs local Python code to calculate a weighted average (45% Reliability, 35% Consensus, 20% Relevance) and subtracts penalties for contradictions, inapplicable sources, and critique uncertainties, and calculates a dynamic confidence margin.

### Phase 6: Output Synthesis
* **A10 Response Agent**
  * *Why*: Users need a direct answer grounded in the evidence, with tone indicators matching the confidence level.
  * *How*: Uses **Gemini 1.5 Pro** to write the answer, limiting it to the extracted claims. It inserts citation numbers and adjusts its language based on the ERS band (High, Medium, Low).

### Phase 7: Post-Processing
* **A11 Audit Agent**
  * *Why*: Provides compliance records and performance statistics for system improvement.
  * *How*: Uses FastAPI background tasks to log the execution payload to PostgreSQL and LangSmith, preventing latency overhead for the user.
