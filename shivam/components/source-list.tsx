"use client";

import { ExternalLink, FileText } from "lucide-react";
import { buildSourceUrl } from "@/lib/rag-api";
import type { Source } from "@/lib/types";

export function SourceList({ sources }: { sources: Source[] }) {
  return (
    <div className="sources" aria-label="Retrieved sources">
      <div className="sources-title">Retrieved sources</div>
      <div className="source-grid">
        {sources.map((source) => (
          <a
            className="source-card"
            href={buildSourceUrl(source)}
            target="_blank"
            rel="noreferrer"
            key={`${source.fileName}-${source.pageNumber}-${source.chunkId}`}
          >
            <span className="source-icon" aria-hidden="true">
              <FileText size={18} />
            </span>
            <span className="source-content">
              <span className="source-name">{source.fileName}</span>
              <span className="source-meta">
                Score {source.relevanceScore.toFixed(2)} - Page {source.pageNumber} - Chunk {source.chunkId}
              </span>
            </span>
            <ExternalLink size={15} />
          </a>
        ))}
      </div>
    </div>
  );
}
