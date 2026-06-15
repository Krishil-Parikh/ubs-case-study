"use client";

import { useCallback, useRef, useState } from "react";
import { streamRagResponse } from "@/lib/rag-api";
import type { ChatError, Source, StageStatus, WorkflowStage } from "@/lib/types";

type StageState = Record<WorkflowStage, StageStatus>;

export type Exchange = {
  query: string;
  answer: string;
  sources: Source[];
};

const initialStages: StageState = {
  retrieving: "idle",
  reranking: "idle",
  generating: "idle"
};

export function useRagChat() {
  const [exchange, setExchange] = useState<Exchange | null>(null);
  const [stages, setStages] = useState<StageState>(initialStages);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<ChatError | null>(null);
  const [checkpointId, setCheckpointId] = useState<string | undefined>();
  const abortRef = useRef<AbortController | null>(null);
  const checkpointRef = useRef<string | undefined>();
  const lastQueryRef = useRef("");

  const runStream = useCallback(async (query: string, retryCheckpointId?: string) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setIsStreaming(true);
    setError(null);
    lastQueryRef.current = query;

    if (!retryCheckpointId) {
      setExchange({ query, answer: "", sources: [] });
      setStages(initialStages);
      checkpointRef.current = undefined;
      setCheckpointId(undefined);
    }

    try {
      for await (const event of streamRagResponse({
        query,
        checkpointId: retryCheckpointId,
        signal: controller.signal
      })) {
        if (event.type === "checkpoint") {
          checkpointRef.current = event.checkpointId;
          setCheckpointId(event.checkpointId);
        }

        if (event.type === "progress") {
          setStages((current) => ({
            ...current,
            [event.stage]: event.status
          }));
        }

        if (event.type === "token") {
          setExchange((current) => current && { ...current, answer: current.answer + event.content });
        }

        if (event.type === "sources") {
          setExchange((current) => current && { ...current, sources: event.sources });
        }

        if (event.type === "error") {
          if (event.checkpointId) {
            checkpointRef.current = event.checkpointId;
            setCheckpointId(event.checkpointId);
          }
          throw new RecoverableStreamError(event.message, event.recoverable ?? true);
        }
      }
    } catch (caught) {
      if (controller.signal.aborted) {
        setError({ message: "The response stream was interrupted.", recoverable: Boolean(checkpointRef.current) });
      } else {
        const streamError = caught as Error & { recoverable?: boolean };
        setError({
          message: streamError.message || "Unable to stream the response.",
          recoverable: streamError.recoverable ?? true
        });
      }
      setStages((current) => markActiveStageErrored(current));
    } finally {
      setIsStreaming(false);
      abortRef.current = null;
    }
  }, []);

  const submit = useCallback((query: string) => runStream(query), [runStream]);

  const retry = useCallback(() => {
    if (!lastQueryRef.current || !checkpointId) return;
    void runStream(lastQueryRef.current, checkpointId);
  }, [checkpointId, runStream]);

  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  return {
    exchange,
    stages,
    isStreaming,
    error,
    canRetry: Boolean(error?.recoverable && checkpointId),
    submit,
    retry,
    stop
  };
}

class RecoverableStreamError extends Error {
  recoverable: boolean;

  constructor(message: string, recoverable: boolean) {
    super(message);
    this.recoverable = recoverable;
  }
}

function markActiveStageErrored(stages: StageState): StageState {
  const active = Object.entries(stages).find(([, status]) => status === "active")?.[0] as WorkflowStage | undefined;
  if (!active) return stages;
  return { ...stages, [active]: "error" };
}
