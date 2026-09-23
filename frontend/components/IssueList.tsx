"use client";

import { useState } from "react";

import { SeverityBadge } from "./SeverityBadge";
import { SEVERITY_ORDER, type VocalIssue } from "@/lib/types";

const SOURCE_LABELS: Record<string, string> = {
  spectral: "measured",
  qualitative: "heard",
};

export function IssueList({ issues }: { issues: VocalIssue[] }) {
  if (issues.length === 0) {
    return (
      <section className="panel p-6">
        <h2 className="mb-2 text-lg font-medium">Issues</h2>
        <p className="muted">
          Nothing worth fixing turned up. The balance, dynamics and noise floor all sit in
          a normal range.
        </p>
      </section>
    );
  }

  const sorted = [...issues].sort(
    (a, b) =>
      SEVERITY_ORDER[b.severity] - SEVERITY_ORDER[a.severity] ||
      b.confidence - a.confidence,
  );

  return (
    <section className="panel p-6">
      <h2 className="mb-4 text-lg font-medium">
        Issues <span className="muted font-normal">({issues.length})</span>
      </h2>
      <ul className="divide-y divide-[var(--border)]">
        {sorted.map((issue) => (
          <IssueRow key={`${issue.name}-${issue.category}`} issue={issue} />
        ))}
      </ul>
    </section>
  );
}

function IssueRow({ issue }: { issue: VocalIssue }) {
  const [open, setOpen] = useState(false);
  const evidence = Object.entries(issue.spectral_evidence ?? {});

  return (
    <li>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex w-full items-center gap-3 py-3 text-left"
      >
        <SeverityBadge severity={issue.severity} />
        <span className="flex-1">{issue.name}</span>
        <span className="muted text-sm">
          {Math.round(issue.confidence * 100)}% ·{" "}
          {issue.sources.map((source) => SOURCE_LABELS[source] ?? source).join(" + ")}
        </span>
        <span aria-hidden className="muted">
          {open ? "−" : "+"}
        </span>
      </button>

      {open && (
        <div className="space-y-3 pb-4 pl-[5.5rem] pr-4">
          <p className="leading-relaxed">{issue.description}</p>
          {evidence.length > 0 && (
            <dl className="muted flex flex-wrap gap-x-6 gap-y-1 text-sm">
              {evidence.map(([key, value]) => (
                <div key={key} className="flex gap-2">
                  <dt>{key.replace(/_/g, " ")}</dt>
                  <dd className="text-[var(--text)]">{String(value)}</dd>
                </div>
              ))}
            </dl>
          )}
        </div>
      )}
    </li>
  );
}
