import { PipelineResponse } from "../services/api";
import { ERSBadge } from "./ERSBadge";

interface Props {
  result: PipelineResponse;
}

export function ResultPanel({ result }: Props) {
  return (
    <div style={{ marginTop: 24 }}>
      {result.insufficient_evidence && (
        <div style={{ background: "#fef2f2", border: "1px solid #fca5a5", borderRadius: 6, padding: 12, marginBottom: 16, color: "#dc2626" }}>
          INSUFFICIENT_EVIDENCE — The retrieved evidence is insufficient to support a reliable conclusion.
        </div>
      )}

      <div style={{ display: "flex", gap: 24, flexWrap: "wrap", marginBottom: 20 }}>
        <ERSBadge ers={result.ers} />
        <div style={{ flex: 1, minWidth: 240 }}>
          <h3 style={{ margin: "0 0 8px" }}>Answer</h3>
          <p style={{ margin: 0, lineHeight: 1.6 }}>{result.answer}</p>
        </div>
      </div>

      {result.uncertainties.length > 0 && (
        <div>
          <h4>Key Uncertainties</h4>
          <ul>
            {result.uncertainties.map((u, i) => <li key={i}>{u}</li>)}
          </ul>
        </div>
      )}

      {result.contradiction_graph.edges.length > 0 && (
        <div>
          <h4>Contradictions ({result.contradiction_graph.edges.length})</h4>
          {result.contradiction_graph.edges.map((e, i) => (
            <div key={i} style={{ background: "#fff7ed", border: "1px solid #fed7aa", borderRadius: 4, padding: 8, marginBottom: 6, fontSize: 13 }}>
              <strong>{e.relation}</strong> — {e.explanation}
            </div>
          ))}
        </div>
      )}

      <div>
        <h4>Claims ({result.claims.length})</h4>
        {result.claims.slice(0, 10).map((c) => (
          <div key={c.claim_id} style={{ background: "#f9fafb", borderRadius: 4, padding: "6px 10px", marginBottom: 4, fontSize: 13 }}>
            <span style={{ color: "#6b7280", marginRight: 8 }}>[{c.claim_type}]</span>{c.text}
          </div>
        ))}
      </div>
    </div>
  );
}
