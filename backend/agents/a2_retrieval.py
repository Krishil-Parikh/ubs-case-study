"""A2 Retrieval — BM25 + Qdrant vector search → hybrid merge → cross-encoder rerank → TopKDocuments."""
from backend.services.qdrant_service import qdrant_service
from backend.services.gemini_service import gemini_service
from backend.config.settings import settings


class RetrievalAgent:
    def run(self, clean_query: str) -> list[dict]:
        query_vector = gemini_service.embed(clean_query)
        vector_hits = qdrant_service.search(query_vector, top_k=settings.top_k_documents)
        bm25_hits = self._bm25_search(clean_query)
        merged = self._hybrid_merge(vector_hits, bm25_hits)
        return self._rerank(clean_query, merged)

    def _bm25_search(self, query: str) -> list[dict]:
        # TODO: integrate rank_bm25 over stored documents
        return []

    def _hybrid_merge(self, vector_hits, bm25_hits) -> list[dict]:
        # TODO: reciprocal rank fusion
        return [{"id": h.id, "payload": h.payload, "score": h.score} for h in vector_hits]

    def _rerank(self, query: str, docs: list[dict]) -> list[dict]:
        # TODO: cross-encoder reranking via sentence-transformers
        return docs
