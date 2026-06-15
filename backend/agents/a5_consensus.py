"""A5 Consensus — pairwise cosine similarity matrix → consensus_score per claim cluster."""
import numpy as np
from backend.models.schemas import Claim
from backend.services.gemini_service import gemini_service


class ConsensusAgent:
    def run(self, claims: list[Claim]) -> float:
        if len(claims) < 2:
            return 0.5
        embeddings = [gemini_service.embed(c.text) for c in claims]
        matrix = self._cosine_matrix(embeddings)
        upper = matrix[np.triu_indices(len(matrix), k=1)]
        return float(np.mean(upper))

    def _cosine_matrix(self, vecs: list[list[float]]) -> np.ndarray:
        arr = np.array(vecs)
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        normed = arr / (norms + 1e-9)
        return normed @ normed.T
