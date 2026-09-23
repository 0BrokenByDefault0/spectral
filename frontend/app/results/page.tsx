"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { ChainDiagram } from "@/components/ChainDiagram";
import { IssueList } from "@/components/IssueList";
import { VocalProfileCard } from "@/components/VocalProfileCard";
import { loadResult } from "@/lib/session";
import type { AnalysisResult } from "@/lib/types";

export default function ResultsPage() {
  // The analysis lives in sessionStorage, which only exists in the browser, so this
  // reads after mount rather than during render.
  const [state, setState] = useState<
    { result: AnalysisResult; filename: string } | null | undefined
  >(undefined);

  useEffect(() => {
    setState(loadResult());
  }, []);

  if (state === undefined) {
    return <p className="muted">Loading…</p>;
  }

  if (state === null) {
    return (
      <div className="panel p-8">
        <p className="mb-4">There is no analysis to show — it does not survive a new tab.</p>
        <Link href="/" className="text-series underline">
          Upload a recording
        </Link>
      </div>
    );
  }

  const { result, filename } = state;

  return (
    <div className="space-y-6">
      <VocalProfileCard profile={result.profile} filename={filename} />
      <IssueList issues={result.profile.issues} />
      <ChainDiagram chains={result.chains} />

      <Link href="/" className="muted inline-block text-sm underline">
        Analyse another take
      </Link>
    </div>
  );
}
