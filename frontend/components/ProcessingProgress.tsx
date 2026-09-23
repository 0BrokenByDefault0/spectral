"use client";

import { useEffect, useState } from "react";

/**
 * The backend analyses in one synchronous request, so it cannot report which stage it
 * is on. Rather than pretend, this advances through the stages on a timer that matches
 * roughly how long each one takes, and parks on the last stage until the response
 * actually lands — so it never claims to be finished before it is.
 */
const STAGES = [
  { label: "Reading the file", seconds: 1 },
  { label: "Checking vocal or full mix", seconds: 2 },
  { label: "Measuring the signal", seconds: 4 },
  { label: "Listening for what the numbers miss", seconds: 12 },
  { label: "Building the chains", seconds: 2 },
] as const;

export function ProcessingProgress({ filename }: { filename: string }) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const started = Date.now();
    const timer = setInterval(() => setElapsed((Date.now() - started) / 1000), 250);
    return () => clearInterval(timer);
  }, []);

  let remaining = elapsed;
  let current = STAGES.length - 1;
  for (let index = 0; index < STAGES.length; index += 1) {
    if (remaining < STAGES[index].seconds) {
      current = index;
      break;
    }
    remaining -= STAGES[index].seconds;
  }

  return (
    <div className="panel p-8">
      <p className="muted mb-6 text-sm">Analysing {filename}</p>
      <ol className="space-y-3">
        {STAGES.map((stage, index) => {
          const done = index < current;
          const active = index === current;
          return (
            <li key={stage.label} className="flex items-center gap-3">
              <span
                aria-hidden
                className={[
                  "h-2 w-2 rounded-full",
                  done ? "bg-minor" : active ? "animate-pulse bg-white" : "bg-white/20",
                ].join(" ")}
              />
              <span className={done || active ? "" : "muted"}>{stage.label}</span>
              {active && <span className="muted text-sm">…</span>}
            </li>
          );
        })}
      </ol>
      {elapsed > 30 && (
        <p className="muted mt-6 text-sm">
          Still going. Long takes and the listening pass both add time.
        </p>
      )}
    </div>
  );
}
