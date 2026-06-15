"""A3 Evidence Extraction — converts documents into Claim[] with typed annotations.

Pipeline:
  1. Retrieve predefined source type from payload (research_paper / news_article / blog)
  2. Extract claims via LLM with optimized structured JSON output
  3. Extract PIOT entities and span-level attribution per claim
  4. Apply soft constraint guardrails (length, confidence, fuzzy span match, max limit)
  5. Embedding-based deduplication at the claim level
"""
import uuid
import json
import re
import logging
from typing import Optional

from backend.models.schemas import (
    Claim,
    ClaimType,
    PIOTEntities,
    SourceType,
    SpanReference,
)
from backend.services.gemini_service import gemini_service

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Optimized Extraction Prompts
# ---------------------------------------------------------------------------

EXTRACTION_PROMPT_RESEARCH = """You are an expert clinical data extraction system. Analyze the Research Paper below and extract all distinct medical/scientific claims.

For each claim, output a JSON object with:
- "text": concise, stand-alone proposition summarizing the claim.
- "claim_type": "quantitative" (e.g. stats, percentages, specific outcomes), "qualitative" (general associations, descriptive findings), "hedged" (stated with low certainty, e.g., "may", "could"), or "methodological_caveat" (methodological constraints/parameters, e.g. sample size, study duration).
- "confidence": confidence level of the claim statement (0.0 to 1.0).
- "source_sentence": the exact sentence containing this claim.
- "paragraph_index": 0-indexed paragraph number where the source sentence is located.
- "population": study population description (age, condition, size) or null.
- "intervention": treatment, agent, or action evaluated or null.
- "outcome": direct clinical outcome measured or null.
- "timeframe": follow-up duration or treatment period or null.

Return a valid JSON array only. Do not include markdown code block styling or any explanation.

Document:
{document}
"""

EXTRACTION_PROMPT_NEWS = """You are an expert news intelligence system. Analyze the News Article below and extract all distinct factual claims, assertions, or expert quotes.

For each claim, output a JSON object with:
- "text": concise, stand-alone proposition summarizing the statement.
- "claim_type": "quantitative" (statistical/numerical claims), "qualitative" (general statements/assertions), "hedged" (speculative/unverified statements), or "methodological_caveat" (study/trial details mentioned).
- "confidence": confidence level of the claim assertion (0.0 to 1.0).
- "source_sentence": the exact sentence containing this claim.
- "paragraph_index": 0-indexed paragraph number where the source sentence is located.
- "population": target group, demographics, or null.
- "intervention": policy, compound, or event or null.
- "outcome": reported effect or null.
- "timeframe": duration or period or null.

Return a valid JSON array only. Do not include markdown code block styling or any explanation.

Document:
{document}
"""

EXTRACTION_PROMPT_BLOG = """You are an expert fact-extraction system. Analyze the Blog Post below and extract all core claims, separating factual assertions from subjective commentary.

For each claim, output a JSON object with:
- "text": concise, stand-alone proposition summarizing the claim.
- "claim_type": "quantitative" (numerical claims), "qualitative" (descriptive assertions), "hedged" (highly speculative claims/opinions), or "methodological_caveat" (methodology/context reference).
- "confidence": confidence level of the statement (0.0 to 1.0; reduce for pure opinions).
- "source_sentence": the exact sentence containing this claim.
- "paragraph_index": 0-indexed paragraph number where the source sentence is located.
- "population": affected group or null.
- "intervention": discussed substance, diet, or treatment or null.
- "outcome": asserted outcome or null.
- "timeframe": duration or null.

Return a valid JSON array only. Do not include markdown code block styling or any explanation.

Document:
{document}
"""

PROMPT_BY_SOURCE = {
    SourceType.RESEARCH_PAPER: EXTRACTION_PROMPT_RESEARCH,
    SourceType.NEWS_ARTICLE: EXTRACTION_PROMPT_NEWS,
    SourceType.BLOG: EXTRACTION_PROMPT_BLOG,
    SourceType.UNKNOWN: EXTRACTION_PROMPT_BLOG,
}


# ---------------------------------------------------------------------------
# Guardrails and Soft Constraints Configuration
# ---------------------------------------------------------------------------
MAX_CLAIMS_PER_DOC = 15          # Prevents hallucination flood
MIN_CLAIM_CONFIDENCE_FLOOR = 0.3  # Discards extremely low confidence claims
MIN_CLAIM_TEXT_LENGTH = 10       # Discards empty or fragment claims
MAX_CLAIM_TEXT_LENGTH = 300      # Truncates overly long text to maintain conciseness
DEDUP_SIMILARITY_THRESHOLD = 0.92


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class ExtractionAgent:
    """A3 — converts raw documents into a deduplicated Claim[] array.

    Features soft constraint guardrails to prevent downstream system overload
    and improve reliability of span and entity mappings.
    """

    def run(self, documents: list[dict]) -> list[Claim]:
        """Process a batch of documents and return deduplicated claims.

        Args:
            documents: list of dicts with keys:
                - id: unique document identifier (join key for A4)
                - payload: { text: str, source_type?: str, ... }

        Returns:
            Deduplicated list of Claim objects.
        """
        all_claims: list[Claim] = []
        for doc in documents:
            doc_id = str(doc["id"])
            payload = doc.get("payload", {})
            text = payload.get("text", "")
            if not text.strip():
                logger.warning("Skipping empty document %s", doc_id)
                continue

            # Predefined source type from payload
            source_type = self._get_source_type(payload)
            claims = self._extract_claims(text, source_type, doc_id)
            all_claims.extend(claims)

        # Embedding-based deduplication across all documents
        deduplicated = self._deduplicate(all_claims)
        logger.info(
            "A3 extraction: %d raw claims -> %d after dedup",
            len(all_claims),
            len(deduplicated),
        )
        return deduplicated

    def _get_source_type(self, payload: dict) -> SourceType:
        """Retrieve the predefined source type from payload metadata."""
        pre_tagged = payload.get("source_type", "").lower().strip()
        for st in SourceType:
            if st.value == pre_tagged:
                return st
        return SourceType.UNKNOWN

    def _extract_claims(
        self, text: str, source_type: SourceType, doc_id: str
    ) -> list[Claim]:
        """Run source-type-specific extraction prompt and parse JSON claims."""
        prompt_template = PROMPT_BY_SOURCE[source_type]
        prompt = prompt_template.format(document=text)

        try:
            raw = gemini_service.generate(prompt, use_flash=True)
            return self._parse_claims(raw, doc_id, text)
        except Exception as exc:
            logger.error("Claim extraction failed for doc %s: %s", doc_id, exc)
            return []

    def _parse_claims(self, raw: str, source_id: str, full_text: str) -> list[Claim]:
        """Parse LLM JSON output into Claim objects with soft constraint guardrails."""
        try:
            # Strip markdown code fencing if the LLM wraps its response
            cleaned = re.sub(r"```json\s*", "", raw)
            cleaned = re.sub(r"```\s*$", "", cleaned)
            match = re.search(r"\[.*\]", cleaned, re.DOTALL)
            if not match:
                logger.warning("No JSON array found in extraction output")
                return []

            items = json.loads(match.group())
        except (json.JSONDecodeError, AttributeError) as exc:
            logger.warning("JSON parse error in extraction: %s", exc)
            return []

        # Soft constraint: cap total claims per document to avoid hallucination floods
        if len(items) > MAX_CLAIMS_PER_DOC:
            logger.warning("Document %s exceeded max claims. Truncating to %d.", source_id, MAX_CLAIMS_PER_DOC)
            items = items[:MAX_CLAIMS_PER_DOC]

        claims: list[Claim] = []
        for item in items:
            try:
                # --- Text content guardrails (soft constraints) ---
                claim_text = item.get("text", "").strip()
                if len(claim_text) < MIN_CLAIM_TEXT_LENGTH:
                    logger.debug("Discarding too short claim text: %s", claim_text)
                    continue

                if len(claim_text) > MAX_CLAIM_TEXT_LENGTH:
                    logger.debug("Truncating claim text exceeding max limit")
                    claim_text = claim_text[:MAX_CLAIM_TEXT_LENGTH - 3] + "..."

                # --- Confidence floor guardrail ---
                try:
                    confidence = float(item.get("confidence", 0.5))
                except (ValueError, TypeError):
                    confidence = 0.5
                
                if confidence < MIN_CLAIM_CONFIDENCE_FLOOR:
                    logger.debug("Discarding claim with low confidence: %s (%f)", claim_text, confidence)
                    continue

                # --- Fuzzy Span resolver guardrail ---
                source_sentence = item.get("source_sentence", "").strip()
                span_start = self._find_span_start_fuzzy(full_text, source_sentence)
                span = SpanReference(
                    paragraph_index=item.get("paragraph_index"),
                    sentence_text=source_sentence,
                    char_start=span_start,
                    char_end=span_start + len(source_sentence) if span_start is not None else None,
                )

                # Build PIOT
                piot = PIOTEntities(
                    population=item.get("population"),
                    intervention=item.get("intervention"),
                    outcome=item.get("outcome"),
                    timeframe=item.get("timeframe"),
                )

                # Normalise claim_type
                raw_type = item.get("claim_type", "qualitative").lower().strip()
                try:
                    claim_type = ClaimType(raw_type)
                except ValueError:
                    claim_type = ClaimType.QUALITATIVE

                claims.append(
                    Claim(
                        claim_id=str(uuid.uuid4()),
                        source_id=source_id,
                        text=claim_text,
                        claim_type=claim_type,
                        confidence=confidence,
                        span=span,
                        piot=piot,
                    )
                )
            except Exception as exc:
                logger.warning("Skipping malformed claim item: %s", exc)
                continue

        return claims

    @staticmethod
    def _find_span_start_fuzzy(full_text: str, sentence: str) -> Optional[int]:
        """Soft span matching guardrail.
        
        Attempts:
          1. Exact match.
          2. Case-insensitive match.
          3. Whitespace-normalized match.
        """
        if not sentence:
            return None
        
        # 1. Exact match
        idx = full_text.find(sentence)
        if idx != -1:
            return idx
            
        # 2. Case-insensitive match
        idx = full_text.lower().find(sentence.lower())
        if idx != -1:
            return idx
            
        # 3. Normalized whitespace match (remove extra newlines/tabs)
        norm_sentence = re.sub(r"\s+", " ", sentence).strip()
        norm_text = re.sub(r"\s+", " ", full_text)
        idx = norm_text.find(norm_sentence)
        if idx != -1:
            # Estimate character offset in original text
            # (Best effort approximation based on relative position)
            ratio = idx / len(norm_text)
            return int(ratio * len(full_text))

        return None

    def _deduplicate(self, claims: list[Claim]) -> list[Claim]:
        """Remove near-duplicate claims using embedding cosine similarity."""
        if len(claims) <= 1:
            return claims

        # Compute embeddings for all claims
        embeddings: list[list[float]] = []
        for claim in claims:
            try:
                emb = gemini_service.embed(claim.text)
                embeddings.append(emb)
                claim.embedding = emb
            except Exception:
                embeddings.append([])

        keep_mask = [True] * len(claims)
        for i in range(len(claims)):
            if not keep_mask[i]:
                continue
            for j in range(i + 1, len(claims)):
                if not keep_mask[j]:
                    continue
                sim = self._cosine_similarity(embeddings[i], embeddings[j])
                if sim >= DEDUP_SIMILARITY_THRESHOLD:
                    if claims[j].confidence > claims[i].confidence:
                        keep_mask[i] = False
                        break
                    else:
                        keep_mask[j] = False

        deduplicated = [c for c, keep in zip(claims, keep_mask) if keep]
        for c in deduplicated:
            c.embedding = None
        return deduplicated

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        mag_a = sum(x * x for x in a) ** 0.5
        mag_b = sum(x * x for x in b) ** 0.5
        if mag_a == 0 or mag_b == 0:
            return 0.0
        return dot / (mag_a * mag_b)
