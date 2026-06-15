import { useState } from "react";
import { queryPipeline, PipelineRequest, PipelineResponse } from "../services/api";

export function usePipeline() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<PipelineResponse | null>(null);

  const submit = async (req: PipelineRequest) => {
    setLoading(true);
    setError(null);
    try {
      const data = await queryPipeline(req);
      setResult(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  return { submit, loading, error, result };
}
