import axios from "axios";

const client = axios.create({ baseURL: "/api" });

export interface PipelineRequest {
  query: string;
  user_id?: string;
  session_id?: string;
  max_sources?: number;
}

export interface ERSResult {
  score: number;
  band: "High" | "Medium" | "Low";
  confidence_lower: number;
  confidence_upper: number;
  source_score: number;
  consensus_score: number;
  retrieval_relevance: number;
  contradiction_penalty: number;
  applicability_penalty: number;
  uncertainty_penalty: number;
}

export interface PipelineResponse {
  answer: string;
  ers: ERSResult;
  claims: { claim_id: string; source_id: string; text: string; claim_type: string; confidence: number }[];
  contradiction_graph: { edges: { claim_a_id: string; claim_b_id: string; relation: string; explanation: string }[] };
  applicability_report: { flags: object[]; overall_applicable: boolean };
  uncertainties: string[];
  insufficient_evidence: boolean;
  session_id?: string;
}

export const queryPipeline = (req: PipelineRequest) =>
  client.post<PipelineResponse>("/pipeline/query", req).then((r) => r.data);

export const healthCheck = () =>
  client.get<{ status: string; qdrant: boolean }>("/health").then((r) => r.data);
