from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from backend.config.settings import settings


class QdrantService:
    def __init__(self):
        self.client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
        )
        self.collection = settings.qdrant_collection

    def ensure_collection(self, vector_size: int = 768):
        existing = [c.name for c in self.client.get_collections().collections]
        if self.collection not in existing:
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )

    def upsert(self, points: list[PointStruct]):
        self.client.upsert(collection_name=self.collection, points=points)

    def search(self, query_vector: list[float], top_k: int = 10, filter_=None):
        return self.client.search(
            collection_name=self.collection,
            query_vector=query_vector,
            limit=top_k,
            query_filter=filter_,
            with_payload=True,
        )

    def health(self) -> bool:
        try:
            self.client.get_collections()
            return True
        except Exception:
            return False


qdrant_service = QdrantService()
