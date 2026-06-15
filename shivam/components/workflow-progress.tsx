"use client";

import { Check, Circle, Loader2, X } from "lucide-react";
import type { StageStatus, WorkflowStage } from "@/lib/types";

const labels: Record<WorkflowStage, string> = {
  retrieving: "Retrieving Documents",
  reranking: "Reranking",
  generating: "Generating Response"
};

const order: WorkflowStage[] = ["retrieving", "reranking", "generating"];

export function WorkflowProgress({ stages }: { stages: Record<WorkflowStage, StageStatus> }) {
  return (
    <aside className="workflow" aria-label="Workflow progress">
      {order.map((stage) => (
        <div className={`workflow-step workflow-${stages[stage]}`} key={stage}>
          <span className="workflow-icon" aria-hidden="true">
            {iconFor(stages[stage])}
          </span>
          <span>{labels[stage]}</span>
        </div>
      ))}
    </aside>
  );
}

function iconFor(status: StageStatus) {
  if (status === "complete") return <Check size={15} />;
  if (status === "active") return <Loader2 size={15} className="spin" />;
  if (status === "error") return <X size={15} />;
  return <Circle size={15} />;
}
