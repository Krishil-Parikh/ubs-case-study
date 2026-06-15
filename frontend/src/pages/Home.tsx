import { usePipeline } from "../hooks/usePipeline";
import { QueryForm } from "../components/QueryForm";
import { ResultPanel } from "../components/ResultPanel";

export function Home() {
  const { submit, loading, error, result } = usePipeline();

  return (
    <div style={{ maxWidth: 900, margin: "40px auto", padding: "0 20px", fontFamily: "system-ui, sans-serif" }}>
      <h1 style={{ marginBottom: 4 }}>Evidence Reliability Score Pipeline</h1>
      <p style={{ color: "#6b7280", marginBottom: 24 }}>
        Submit a research question to evaluate evidence quality across 11 agents.
      </p>

      <QueryForm onSubmit={(q) => submit({ query: q })} loading={loading} />

      {error && (
        <div style={{ marginTop: 16, color: "#dc2626", background: "#fef2f2", borderRadius: 4, padding: 10 }}>
          {error}
        </div>
      )}

      {result && <ResultPanel result={result} />}
    </div>
  );
}
