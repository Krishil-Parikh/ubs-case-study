import type { RagRequest, RagStreamEvent, Source, WorkflowStage } from "@/lib/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_RAG_API_BASE_URL;
const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK_RAG !== "false" || !API_BASE_URL;

export async function* streamRagResponse(request: RagRequest): AsyncGenerator<RagStreamEvent> {
  if (USE_MOCK) {
    yield* mockRagStream(request);
    return;
  }

  const endpoint = request.checkpointId ? "/rag/retry" : "/rag/query";
  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/x-ndjson"
    },
    body: JSON.stringify({
      query: request.query,
      checkpoint_id: request.checkpointId
    }),
    signal: request.signal
  });

  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new Error(detail || `RAG request failed with status ${response.status}`);
  }

  if (!response.body) {
    throw new Error("The RAG backend did not return a readable stream.");
  }

  yield* parseNdjsonStream(response.body);
}

export function buildSourceUrl(source: Source) {
  if (source.openUrl) {
    return source.openUrl;
  }

  const baseUrl = API_BASE_URL || "";
  const documentId = source.documentId || encodeURIComponent(source.fileName);
  const params = new URLSearchParams({
    page: String(source.pageNumber),
    chunk_id: source.chunkId
  });

  return `${baseUrl}/documents/${documentId}?${params.toString()}`;
}

async function* parseNdjsonStream(stream: ReadableStream<Uint8Array>): AsyncGenerator<RagStreamEvent> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      yield normalizeEvent(JSON.parse(trimmed));
    }
  }

  const finalLine = buffer.trim();
  if (finalLine) {
    yield normalizeEvent(JSON.parse(finalLine));
  }
}

function normalizeEvent(payload: Record<string, unknown>): RagStreamEvent {
  if (payload.type === "checkpoint") {
    return { type: "checkpoint", checkpointId: String(payload.checkpointId || payload.checkpoint_id || "") };
  }

  if (payload.type === "progress") {
    return {
      type: "progress",
      stage: normalizeStage(payload.stage),
      status: normalizeProgressStatus(payload.status)
    };
  }

  if (payload.type === "token") {
    return { type: "token", content: String(payload.content || payload.token || "") };
  }

  if (payload.type === "sources") {
    return { type: "sources", sources: normalizeSources(payload.sources) };
  }

  if (payload.type === "error") {
    return {
      type: "error",
      message: String(payload.message || "The RAG backend returned an error."),
      recoverable: Boolean(payload.recoverable ?? true),
      checkpointId: payload.checkpointId || payload.checkpoint_id ? String(payload.checkpointId || payload.checkpoint_id) : undefined
    };
  }

  return { type: "done" };
}

function normalizeSources(value: unknown): Source[] {
  if (!Array.isArray(value)) return [];

  return value.map((item) => {
    const source = item as Record<string, unknown>;
    return {
      fileName: String(source.fileName || source.file_name || "Untitled document"),
      relevanceScore: Number(source.relevanceScore || source.relevance_score || 0),
      pageNumber: Number(source.pageNumber || source.page_number || 1),
      chunkId: String(source.chunkId || source.chunk_id || ""),
      documentId: source.documentId || source.document_id ? String(source.documentId || source.document_id) : undefined,
      openUrl: source.openUrl || source.open_url ? String(source.openUrl || source.open_url) : undefined,
      metadata: source.metadata as Record<string, unknown> | undefined
    };
  });
}

function normalizeStage(value: unknown): WorkflowStage {
  if (value === "reranking" || value === "generating") {
    return value;
  }
  return "retrieving";
}

function normalizeProgressStatus(value: unknown) {
  if (value === "complete" || value === "error") {
    return value;
  }
  return "active";
}

async function* mockRagStream(request: RagRequest): AsyncGenerator<RagStreamEvent> {
  const checkpointId = request.checkpointId || `mock-${Date.now()}`;
  yield { type: "checkpoint", checkpointId };
  yield { type: "progress", stage: "retrieving", status: "active" };
  await delay(450, request.signal);
  yield { type: "progress", stage: "retrieving", status: "complete" };
  yield { type: "progress", stage: "reranking", status: "active" };
  await delay(450, request.signal);
  yield { type: "progress", stage: "reranking", status: "complete" };
  yield { type: "progress", stage: "generating", status: "active" };

  const answer = `Here is a production-style RAG answer for: **${request.query}**.\n\nThe frontend streams tokens incrementally, renders Markdown, and keeps source metadata attached to the answer. A FastAPI backend can emit newline-delimited JSON events like this:\n\n\`\`\`python\n@app.post("/rag/query")\nasync def query_rag(payload: RagQuery):\n    return StreamingResponse(stream_events(payload), media_type="application/x-ndjson")\n\`\`\`\n\nBecause the chat is stateless, every request should include the full user query and no prior conversation memory.`;

  for (const chunk of answer.match(/.{1,9}/g) || []) {
    await delay(35, request.signal);
    yield { type: "token", content: chunk };
  }

  yield {
    type: "sources",
    sources: [
      {
        fileName: "architecture-notes.pdf",
        relevanceScore: 0.94,
        pageNumber: 7,
        chunkId: "arch-007-02",
        documentId: "architecture-notes"
      },
      {
        fileName: "retrieval-evaluation.md",
        relevanceScore: 0.89,
        pageNumber: 3,
        chunkId: "eval-003-01",
        documentId: "retrieval-evaluation"
      }
    ]
  };
  yield { type: "progress", stage: "generating", status: "complete" };
  yield { type: "done" };
}

function delay(ms: number, signal?: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException("The stream was interrupted.", "AbortError"));
      return;
    }

    const timeout = window.setTimeout(resolve, ms);
    signal?.addEventListener(
      "abort",
      () => {
        window.clearTimeout(timeout);
        reject(new DOMException("The stream was interrupted.", "AbortError"));
      },
      { once: true }
    );
  });
}
