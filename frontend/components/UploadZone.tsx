"use client";

import { useCallback, useRef, useState } from "react";

const ACCEPTED = [".wav", ".flac", ".mp3", ".aiff", ".aif", ".ogg", ".m4a"];
const MAX_BYTES = 60 * 1024 * 1024;

interface Props {
  file: File | null;
  onFile: (file: File | null) => void;
  disabled?: boolean;
}

/** Drag-and-drop target that rejects the obvious cases before an upload is attempted. */
export function UploadZone({ file, onFile, disabled }: Props) {
  const [dragging, setDragging] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);

  const accept = useCallback(
    (candidate: File | undefined) => {
      if (!candidate) return;

      const suffix = candidate.name.slice(candidate.name.lastIndexOf(".")).toLowerCase();
      if (!ACCEPTED.includes(suffix)) {
        setProblem(`${suffix || "that file"} is not audio we can read — try ${ACCEPTED.join(", ")}`);
        return;
      }
      if (candidate.size > MAX_BYTES) {
        setProblem(`that file is ${(candidate.size / 1024 / 1024).toFixed(0)} MB; the limit is 60 MB`);
        return;
      }
      setProblem(null);
      onFile(candidate);
    },
    [onFile],
  );

  return (
    <div>
      <div
        role="button"
        tabIndex={disabled ? -1 : 0}
        aria-label="Upload a recording"
        onClick={() => !disabled && input.current?.click()}
        onKeyDown={(event) => {
          if (!disabled && (event.key === "Enter" || event.key === " ")) {
            event.preventDefault();
            input.current?.click();
          }
        }}
        onDragOver={(event) => {
          event.preventDefault();
          if (!disabled) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          if (!disabled) accept(event.dataTransfer.files[0]);
        }}
        className={[
          "panel flex min-h-48 cursor-pointer flex-col items-center justify-center gap-2 border-dashed p-10 text-center transition",
          dragging ? "border-white/60 bg-white/5" : "",
          disabled ? "cursor-not-allowed opacity-60" : "hover:border-white/30",
        ].join(" ")}
      >
        {file ? (
          <>
            <p className="text-lg">{file.name}</p>
            <p className="muted text-sm">
              {(file.size / 1024 / 1024).toFixed(1)} MB · click to choose a different take
            </p>
          </>
        ) : (
          <>
            <p className="text-lg">Drop a vocal here</p>
            <p className="muted text-sm">
              WAV or FLAC is best. Keep the gaps between phrases — the noise floor and the
              room are measured in them.
            </p>
          </>
        )}
        <input
          ref={input}
          type="file"
          accept={ACCEPTED.join(",")}
          className="hidden"
          onChange={(event) => accept(event.target.files?.[0])}
        />
      </div>

      {problem && (
        <p className="mt-3 text-sm text-critical" role="alert">
          {problem}
        </p>
      )}
    </div>
  );
}
