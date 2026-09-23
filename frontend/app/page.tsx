"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { ProcessingProgress } from "@/components/ProcessingProgress";
import { UploadZone } from "@/components/UploadZone";
import { ApiError, analyse } from "@/lib/api";
import { storeResult } from "@/lib/session";

export default function UploadPage() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [genre, setGenre] = useState("");
  const [useLlm, setUseLlm] = useState(true);
  const [running, setRunning] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  async function start() {
    if (!file) return;
    setRunning(true);
    setFailure(null);

    try {
      const result = await analyse(file, { genre, useLlm });
      storeResult(result, file.name);
      router.push("/results");
    } catch (error) {
      setFailure(
        error instanceof ApiError ? error.message : "the analysis failed unexpectedly",
      );
      setRunning(false);
    }
  }

  if (running) {
    return <ProcessingProgress filename={file?.name ?? "your recording"} />;
  }

  return (
    <div className="space-y-6">
      <UploadZone file={file} onFile={setFile} />

      <div className="panel space-y-5 p-6">
        <label className="block">
          <span className="text-sm">Genre</span>
          <span className="muted ml-2 text-sm">
            optional — the listening pass judges against it
          </span>
          <input
            type="text"
            value={genre}
            onChange={(event) => setGenre(event.target.value)}
            placeholder="bedroom rap, indie folk, drill…"
            className="mt-2 w-full rounded-md border border-[var(--border)] bg-black/30 px-3 py-2 outline-none focus:border-white/40"
          />
        </label>

        <label className="flex items-center gap-3">
          <input
            type="checkbox"
            checked={useLlm}
            onChange={(event) => setUseLlm(event.target.checked)}
            className="h-4 w-4"
          />
          <span className="text-sm">
            Listen as well as measure
            <span className="muted ml-2">
              slower, and needs the server to have an API key
            </span>
          </span>
        </label>
      </div>

      {failure && (
        <p className="text-sm text-critical" role="alert">
          {failure}
        </p>
      )}

      <button
        type="button"
        onClick={start}
        disabled={!file}
        className="rounded-md bg-white px-5 py-2.5 font-medium text-black transition disabled:cursor-not-allowed disabled:opacity-40"
      >
        Analyse
      </button>
    </div>
  );
}
