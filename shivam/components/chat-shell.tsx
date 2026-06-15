"use client";

import { Bot, Moon, Search, Square, Sun } from "lucide-react";
import { FormEvent, useEffect, useRef, useState } from "react";
import { ChatInput } from "@/components/chat-input";
import { MessageBubble } from "@/components/message-bubble";
import { WorkflowProgress } from "@/components/workflow-progress";
import { useRagChat } from "@/hooks/use-rag-chat";

export function ChatShell() {
  const { exchange, stages, isStreaming, error, canRetry, submit, retry, stop } = useRagChat();
  const [query, setQuery] = useState("");
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const stored = window.localStorage.getItem("rag-theme");
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    setTheme(stored === "dark" || (!stored && prefersDark) ? "dark" : "light");
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem("rag-theme", theme);
  }, [theme]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [exchange?.answer, exchange?.sources.length, isStreaming, error]);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = query.trim();
    if (!trimmed || isStreaming) return;
    void submit(trimmed);
    setQuery("");
  }

  return (
    <main className="app-shell">
      <header className="top-bar">
        <div className="brand-lockup">
          <span className="brand-mark" aria-hidden="true">
            <Bot size={20} />
          </span>
          <div>
            <h1>RAG Chatbot</h1>
            <p>Stateless retrieval assistant</p>
          </div>
        </div>
        <button
          className="icon-button"
          type="button"
          aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
          title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
          onClick={() => setTheme((current) => (current === "dark" ? "light" : "dark"))}
        >
          {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
        </button>
      </header>

      <section className="chat-workspace" aria-label="RAG chatbot">
        <div className="conversation">
          {!exchange ? (
            <div className="empty-state">
              <Search size={28} />
              <h2>Ask a question across your documents</h2>
              <p>Responses stream live, cite retrieved chunks, and can be retried from backend checkpoints.</p>
            </div>
          ) : (
            <>
              <MessageBubble role="user" content={exchange.query} />
              <MessageBubble
                role="assistant"
                content={exchange.answer}
                sources={exchange.sources}
                isStreaming={isStreaming}
              />
            </>
          )}

          {(isStreaming || exchange || error) && <WorkflowProgress stages={stages} />}

          {error && (
            <div className="error-panel" role="alert">
              <div>
                <strong>Stream interrupted</strong>
                <p>{error.message}</p>
              </div>
              <div className="error-actions">
                {isStreaming ? (
                  <button className="secondary-button" type="button" onClick={stop}>
                    <Square size={15} />
                    Stop
                  </button>
                ) : (
                  <button className="primary-button" type="button" onClick={retry} disabled={!canRetry}>
                    Retry
                  </button>
                )}
              </div>
            </div>
          )}
          <div ref={endRef} />
        </div>

        <ChatInput
          value={query}
          disabled={isStreaming}
          onChange={setQuery}
          onSubmit={handleSubmit}
          onStop={stop}
          isStreaming={isStreaming}
        />
      </section>
    </main>
  );
}
