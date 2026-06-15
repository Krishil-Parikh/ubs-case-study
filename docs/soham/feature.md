Let me read the document carefully and give you a direct, technically precise answer.

## A3 — Evidence Extraction Agent

**Core job:** Take raw text documents (papers, news, blogs) and convert them into a structured `Claim[]` array with typed annotations. Here's how to build it properly.

**Document pre-processing layer** comes first. You need to handle the fact that your three source types have completely different structures. Research papers have abstracts, methods, results, and discussion sections — each section has a different epistemic weight. News articles have ledes and quotes. Blogs are unstructured opinion. You cannot run the same extraction logic across all three and expect clean output. Use a lightweight classifier (fine-tuned BERT or a prompted LLM) to detect source type first, then route to source-specific extraction pipelines.

**Claim extraction** is where most teams screw up by treating it as pure NER. It's not. A claim is a proposition with an associated confidence marker, a subject, and a scope. You should use an LLM with a structured output schema (JSON mode or tool use) and prompt it to extract claims across four typed categories — quantitative claims ("X reduces Y by 30%"), qualitative claims ("evidence suggests X is associated with Y"), hedged claims ("may", "could", "preliminary findings indicate"), and methodological caveats ("based on a 12-week RCT with n=40"). That last type is critical because it directly feeds the Reliability and Applicability agents. If you skip it, A4 and A7 are flying blind.

**Span-level attribution** must be preserved. Every extracted claim needs a character-level pointer back to the source sentence. Don't just extract the claim text — store the source document ID, page or paragraph number, and the exact span. This is what makes A11's audit trail meaningful and what lets you replay contradictions back to their origin.

**Deduplication within A3** — after extraction, run embedding-based deduplication at the claim level, not the document level. Two papers might state the same finding in different words. If you don't deduplicate claims before they hit A4 and A5, you artificially inflate consensus scores because the same claim appears to come from multiple sources when it's actually one.

**What A3 outputs:** A `Claim[]` array where each object carries: claim text, claim type (quantitative/qualitative/hedged/methodological), source document ID, span reference, a raw confidence estimate from the extraction LLM, and extracted entities (population, intervention, outcome, timeframe) using something like GLiNER or a prompted extraction pass. Those PIOT fields are what A7 will use.

---

## A4 — Reliability Agent

**The honest framing first:** this agent is harder than it looks because "reliability" conflates two different things — source credibility and evidence quality. You need to track both separately and not collapse them into one number prematurely.

**Deterministic first pass** handles everything you can score with metadata alone. Source type gets a base score: peer-reviewed journals score highest, with a further multiplier for impact factor or citation count if you can retrieve it via CrossRef or Semantic Scholar APIs. News articles from established outlets get a mid-tier score. Blogs get the lowest base. Recency decay is straightforward — apply an exponential decay function to the publication date, with a half-life you tune depending on your domain (biomedical evidence decays slower than news). This entire pass is rules-based, fast, and fully auditable.

**LLM escalation pass** handles the two things you cannot score deterministically: conflict-of-interest detection and study design assessment. For CoI — if a source is from a vendor, a supplement company, an industry-funded outlet, or contains identifiable promotional language, you flag it with a penalty. A heuristic URL/domain blocklist catches the obvious cases. For edge cases, a lightweight LLM classifier with a focused prompt ("does this text exhibit promotional intent or commercial conflict of interest? output yes/no with a brief rationale") handles the rest. For study design — a research paper needs to be classified as RCT, meta-analysis, cohort study, case report, narrative review, or opinion. This cannot be done from metadata alone in most cases. You need an LLM to read the methods section and classify. This is where the methodological caveat claims extracted in A3 become directly useful input.

**Critical mistake to avoid:** don't let A4 try to assess whether the claim itself is true. That's not its job. A4 assesses the credibility of the source and the rigor of the evidence methodology. Truth assessment is downstream at A8. If you blur this boundary, your penalty system in A9 becomes incoherent because you can't separate "unreliable source saying something plausible" from "reliable source saying something contradicted elsewhere."

**What A4 outputs:** A `ReliabilityScore[]` array — one score object per source document (not per claim), containing: base source type score, recency-adjusted score, CoI flag with severity (none/low/high), study design classification, and a final composite `source_score` in 0–1 range. A9 picks this up directly for the ERS formula.

---

## The integration point you need to get right

A3 and A4 operate on different units — A3 outputs claim-level objects, A4 outputs document-level scores. When A9 computes ERS, it needs to join them: each claim inherits its source document's reliability score. Build an explicit join key (document ID) from day one. If you let this slip, your ERS computation will require messy runtime joins and will be a debugging nightmare when scores look wrong.