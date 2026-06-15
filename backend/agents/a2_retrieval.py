"""A2 Retrieval — BM25 + Qdrant vector search → hybrid merge → cross-encoder rerank → TopKDocuments."""
import math
from backend.services.qdrant_service import qdrant_service
from backend.services.gemini_service import gemini_service
from backend.config.settings import settings

try:
    from rank_bm25 import BM25Okapi
except ImportError:
    # A robust built-in Python BM25 implementation fallback if rank-bm25 is not installed
    class BM25Okapi:
        def __init__(self, corpus):
            self.corpus = corpus
            self.doc_len = [len(doc) for doc in corpus]
            self.avg_doc_len = sum(self.doc_len) / len(corpus) if corpus else 0
            self.doc_count = len(corpus)
            self.df = {}
            for doc in corpus:
                for word in set(doc):
                    self.df[word] = self.df.get(word, 0) + 1
            self.k1 = 1.5
            self.b = 0.75

        def get_scores(self, query):
            scores = []
            for i, doc in enumerate(self.corpus):
                score = 0.0
                doc_len = self.doc_len[i]
                for word in query:
                    if word in self.df:
                        df = self.df[word]
                        idf = math.log((self.doc_count - df + 0.5) / (df + 0.5) + 1.0)
                        tf = doc.count(word)
                        num = tf * (self.k1 + 1)
                        den = tf + self.k1 * (1 - self.b + self.b * doc_len / self.avg_doc_len)
                        score += idf * (num / den)
                scores.append(score)
            return scores


class RetrievalAgent:
    def run(self, clean_query: str) -> list[dict]:
        # Perform semantic vector search
        try:
            query_vector = gemini_service.embed(clean_query)
            vector_hits = qdrant_service.search(query_vector, top_k=settings.top_k_documents)
        except Exception as e:
            print(f"[RetrievalAgent] Vector search failed or skipped: {e}")
            vector_hits = []

        # Perform BM25 lexical search
        bm25_hits = self._bm25_search(clean_query)

        # Perform hybrid merge (RRF)
        merged = self._hybrid_merge(vector_hits, bm25_hits)

        # Perform cross-encoder reranking
        reranked = self._rerank(clean_query, merged)

        # Enrich retrieved documents with metadata for downstream agents
        return self._enrich_metadata(reranked)

    def _bm25_search(self, query: str) -> list[dict]:
        # Integrate BM25 lexical search over stored documents
        try:
            # Retrieve documents from Qdrant for BM25 indexing
            response = qdrant_service.client.scroll(
                collection_name=qdrant_service.collection,
                limit=100,
                with_payload=True,
                with_vectors=False
            )
            points = response[0] if isinstance(response, tuple) else response
            if not points:
                return []

            docs = []
            for p in points:
                doc_id = str(getattr(p, 'id', p.get('id') if isinstance(p, dict) else ''))
                payload = getattr(p, 'payload', p.get('payload') if isinstance(p, dict) else {})
                docs.append({
                    "id": doc_id,
                    "payload": payload
                })

            # Tokenize corpus and query
            corpus_texts = [d["payload"].get("text", "") for d in docs]
            tokenized_corpus = [text.lower().split() for text in corpus_texts]
            tokenized_query = query.lower().split()

            bm25 = BM25Okapi(tokenized_corpus)
            doc_scores = bm25.get_scores(tokenized_query)

            scored_docs = []
            for doc, score in zip(docs, doc_scores):
                if score > 0.0:
                    doc_copy = dict(doc)
                    doc_copy["score"] = float(score)
                    scored_docs.append(doc_copy)

            return sorted(scored_docs, key=lambda x: x["score"], reverse=True)
        except Exception as e:
            print(f"[RetrievalAgent] BM25 lexical search failed: {e}")
            return []

    def _hybrid_merge(self, vector_hits, bm25_hits) -> list[dict]:
        # Perform reciprocal rank fusion (RRF) to merge BM25 and Qdrant hits
        k = 60
        rrf_scores = {}
        doc_map = {}

        # Process vector hits
        for rank, hit in enumerate(vector_hits):
            doc_id = str(getattr(hit, 'id', hit.get('id') if isinstance(hit, dict) else ''))
            payload = getattr(hit, 'payload', hit.get('payload') if isinstance(hit, dict) else {})
            score = float(getattr(hit, 'score', hit.get('score') if isinstance(hit, dict) else 0.0))

            if not doc_id:
                continue

            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + (1.0 / (k + rank + 1))
            doc_map[doc_id] = {
                "id": doc_id,
                "payload": payload,
                "score": score
            }

        # Process BM25 hits
        for rank, hit in enumerate(bm25_hits):
            doc_id = str(hit.get('id'))
            if not doc_id:
                continue

            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + (1.0 / (k + rank + 1))
            if doc_id not in doc_map:
                doc_map[doc_id] = {
                    "id": doc_id,
                    "payload": hit.get("payload", {}),
                    "score": hit.get("score", 0.0)
                }

        # Sort combined documents by RRF score descending
        sorted_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)

        merged_docs = []
        for doc_id in sorted_ids:
            doc = doc_map[doc_id]
            doc["score"] = rrf_scores[doc_id]
            merged_docs.append(doc)

        return merged_docs

    def _rerank(self, query: str, docs: list[dict]) -> list[dict]:
        # Cross-encoder reranking via sentence-transformers to optimize precision
        try:
            from sentence_transformers import CrossEncoder
            model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
            pairs = [[query, doc.get("payload", {}).get("text", "")] for doc in docs]
            scores = model.predict(pairs)
            for doc, score in zip(docs, scores):
                doc["score"] = float(score)
                if "payload" in doc:
                    doc["payload"]["retrieval_score"] = float(score)
            return sorted(docs, key=lambda x: x["score"], reverse=True)
        except Exception as e:
            print(f"[RetrievalAgent] SentenceTransformers/CrossEncoder not available or failed: {e}. Keeping RRF/Vector ranking.")
            return docs

    def _enrich_metadata(self, docs: list[dict]) -> list[dict]:
        # Enrich retrieved evidence with essential metadata needed by downstream agents
        enriched = []
        for doc in docs:
            doc_id = doc.get("id")
            score = doc.get("score", 0.0)
            payload = dict(doc.get("payload", {}))

            # Populate fields required by downstream agents (Reliability, Applicability, etc.)
            source_type = payload.get("source_type") or payload.get("type") or "unknown"
            payload["source_type"] = source_type

            pub_date = payload.get("publication_date") or payload.get("date") or "2020-01-01"
            payload["publication_date"] = pub_date

            try:
                year = int(pub_date.split("-")[0]) if "-" in str(pub_date) else int(pub_date)
            except Exception:
                year = int(payload.get("year", 2020))
            payload["year"] = year

            payload["retrieval_score"] = float(score)

            if "metadata" not in payload or not isinstance(payload["metadata"], dict):
                payload["metadata"] = {}

            payload["metadata"].update({
                "source_id": doc_id,
                "author": payload.get("author") or payload.get("creator") or "Unknown Author",
                "conflict_of_interest": bool(payload.get("conflict_of_interest", False)),
                "title": payload.get("title") or "Untitled Document",
                "retrieval_score": float(score)
            })

            payload["text"] = payload.get("text", "")

            enriched.append({
                "id": doc_id,
                "score": float(score),
                "payload": payload
            })

        return enriched
