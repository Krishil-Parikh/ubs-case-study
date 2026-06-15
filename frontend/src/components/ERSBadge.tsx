import { ERSResult } from "../services/api";

const BAND_COLORS: Record<string, string> = {
  High: "#22c55e",
  Medium: "#f59e0b",
  Low: "#ef4444",
};

interface Props {
  ers: ERSResult;
}

export function ERSBadge({ ers }: Props) {
  const color = BAND_COLORS[ers.band] ?? "#6b7280";
  return (
    <div style={{ border: `2px solid ${color}`, borderRadius: 8, padding: "12px 16px", display: "inline-block" }}>
      <div style={{ fontSize: 13, color: "#6b7280" }}>Evidence Reliability Score</div>
      <div style={{ fontSize: 32, fontWeight: 700, color }}>{ers.score.toFixed(2)}</div>
      <div style={{ fontSize: 14, color, fontWeight: 600 }}>{ers.band}</div>
      <div style={{ fontSize: 12, color: "#9ca3af", marginTop: 4 }}>
        CI [{ers.confidence_lower.toFixed(2)} – {ers.confidence_upper.toFixed(2)}]
      </div>
    </div>
  );
}
