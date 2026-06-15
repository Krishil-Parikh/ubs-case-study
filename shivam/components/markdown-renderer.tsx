"use client";

import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark, oneLight } from "react-syntax-highlighter/dist/esm/styles/prism";
import remarkGfm from "remark-gfm";

export function MarkdownRenderer({ content }: { content: string }) {
  const [dark, setDark] = useState(false);

  useEffect(() => {
    const sync = () => setDark(document.documentElement.dataset.theme === "dark");
    sync();
    const observer = new MutationObserver(sync);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
  }, []);

  return (
    <div className="markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          code({ className, children, ...props }) {
            const match = /language-(\w+)/.exec(className || "");
            const code = String(children).replace(/\n$/, "");
            return match ? (
              <SyntaxHighlighter
                PreTag="div"
                language={match[1]}
                style={dark ? oneDark : oneLight}
                customStyle={{
                  margin: 0,
                  borderRadius: "8px",
                  background: "var(--code-bg)"
                }}
              >
                {code}
              </SyntaxHighlighter>
            ) : (
              <code {...props}>{children}</code>
            );
          }
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
