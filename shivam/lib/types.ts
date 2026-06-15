export type WorkflowStage = "retrieving" | "reranking" | "generating";

export type StageStatus = "idle" | "active" | "complete" | "error";

export type Source = {
  fileName: string;
  relevanceScore: number;
  pageNumber: number;
  chunkId: string;
  documentId?: string;
  openUrl?: string;
  metadata?: Record<string, unknown>;
};

export type ProgressEvent = {
  type: "progress";
  stage: WorkflowStage;
  status: Exclude<StageStatus, "idle">;
};

export type RagStreamEvent =
  | { type: "checkpoint"; checkpointId: string }
  | ProgressEvent
  | { type: "token"; content: string }
  | { type: "sources"; sources: Source[] }
  | { type: "error"; message: string; recoverable?: boolean; checkpointId?: string }
  | { type: "done" };

export type RagRequest = {
  query: string;
  checkpointId?: string;
  signal?: AbortSignal;
};

export type ChatError = {
  message: string;
  recoverable: boolean;
};
