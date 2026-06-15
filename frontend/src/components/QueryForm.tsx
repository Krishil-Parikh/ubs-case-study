import { useState, FormEvent } from "react";

interface Props {
  onSubmit: (query: string) => void;
  loading: boolean;
}

export function QueryForm({ onSubmit, loading }: Props) {
  const [query, setQuery] = useState("");

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (query.trim()) onSubmit(query.trim());
  };

  return (
    <form onSubmit={handleSubmit} style={{ display: "flex", gap: 8 }}>
      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Enter your research question..."
        style={{ flex: 1, padding: "8px 12px", fontSize: 16 }}
        disabled={loading}
      />
      <button type="submit" disabled={loading || !query.trim()}>
        {loading ? "Analyzing..." : "Submit"}
      </button>
    </form>
  );
}
