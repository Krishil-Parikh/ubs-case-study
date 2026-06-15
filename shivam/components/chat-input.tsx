"use client";

import { ArrowUp, Square } from "lucide-react";
import type { FormEvent } from "react";

type ChatInputProps = {
  value: string;
  disabled: boolean;
  isStreaming: boolean;
  onChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onStop: () => void;
};

export function ChatInput({ value, disabled, isStreaming, onChange, onSubmit, onStop }: ChatInputProps) {
  return (
    <form className="composer" onSubmit={onSubmit}>
      <textarea
        value={value}
        disabled={disabled}
        rows={1}
        placeholder="Ask about policies, PDFs, reports, or knowledge base articles..."
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            event.currentTarget.form?.requestSubmit();
          }
        }}
      />
      {isStreaming ? (
        <button className="icon-button send-button" type="button" aria-label="Stop response" title="Stop response" onClick={onStop}>
          <Square size={16} />
        </button>
      ) : (
        <button className="icon-button send-button" type="submit" aria-label="Send query" title="Send query" disabled={!value.trim()}>
          <ArrowUp size={18} />
        </button>
      )}
    </form>
  );
}
