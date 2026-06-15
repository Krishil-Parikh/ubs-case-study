"use client";

import { Check, Copy } from "lucide-react";
import { useState } from "react";
import { MarkdownRenderer } from "@/components/markdown-renderer";
import { SourceList } from "@/components/source-list";
import type { Source } from "@/lib/types";

type MessageBubbleProps = {
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  isStreaming?: boolean;
};

export function MessageBubble({ role, content, sources = [], isStreaming }: MessageBubbleProps) {
  const [copied, setCopied] = useState(false);
  const isAssistant = role === "assistant";

  async function copyAnswer() {
    await navigator.clipboard.writeText(content);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1400);
  }

  return (
    <article className={`message message-${role}`}>
      <div className="message-avatar">{isAssistant ? "AI" : "You"}</div>
      <div className="message-body">
        <div className="message-header">
          <span>{isAssistant ? "Assistant" : "Question"}</span>
          {isAssistant && content && (
            <button className="ghost-button" type="button" onClick={copyAnswer}>
              {copied ? <Check size={15} /> : <Copy size={15} />}
              {copied ? "Copied" : "Copy"}
            </button>
          )}
        </div>
        {isAssistant ? (
          <MarkdownRenderer content={content || (isStreaming ? " " : "")} />
        ) : (
          <p className="user-query">{content}</p>
        )}
        {isAssistant && isStreaming && <span className="stream-cursor" aria-label="Streaming response" />}
        {isAssistant && sources.length > 0 && <SourceList sources={sources} />}
      </div>
    </article>
  );
}
