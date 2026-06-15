# Shivam RAG Chatbot Frontend

Modern Next.js frontend for a stateless RAG chatbot. It streams Markdown responses, displays retrieval workflow progress, shows source metadata, and is ready to connect to a FastAPI backend.

## Run

```bash
npm install
npm run dev
```

The UI uses a mock stream by default so it works before the backend is integrated. To connect FastAPI, copy `.env.example` to `.env.local` and set:

```bash
NEXT_PUBLIC_RAG_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_USE_MOCK_RAG=false
```

## Expected FastAPI Stream

`POST /rag/query` should return newline-delimited JSON events:

```json
{"type":"checkpoint","checkpointId":"ckpt_123"}
{"type":"progress","stage":"retrieving","status":"active"}
{"type":"progress","stage":"reranking","status":"active"}
{"type":"progress","stage":"generating","status":"active"}
{"type":"token","content":"Hello"}
{"type":"sources","sources":[{"fileName":"handbook.pdf","relevanceScore":0.93,"pageNumber":12,"chunkId":"c_12_03","documentId":"doc_1"}]}
{"type":"done"}
```

Retry requests are sent to `POST /rag/retry` with the last `checkpointId`.
