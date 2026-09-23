"use client";

import {
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";

import type { VocalProfile } from "@/lib/types";

/** Axis order is fixed so the shape of the chart means the same thing across takes. */
const AXES = [
  { key: "clarity", label: "Clarity" },
  { key: "dynamics", label: "Dynamics" },
  { key: "noise", label: "Noise" },
  { key: "room", label: "Room" },
  { key: "sibilance", label: "Sibilance" },
  { key: "tonal_balance", label: "Tonal balance" },
] as const;

export function VocalProfileCard({
  profile,
  filename,
}: {
  profile: VocalProfile;
  filename: string;
}) {
  const data = AXES.map(({ key, label }) => ({
    axis: label,
    score: Math.round(profile.scores?.[key] ?? 0),
  }));

  const worst = [...data].sort((a, b) => a.score - b.score)[0];

  return (
    <section className="panel p-6">
      <div className="mb-5 flex items-baseline justify-between gap-4">
        <div>
          <h2 className="text-lg font-medium">{filename}</h2>
          <p className="muted text-sm">
            {profile.source.source_type === "FULL_MIX" ? "Full mix" : "Dry vocal"}
            {" · "}
            {Math.round(profile.source.confidence * 100)}% confident
            {profile.genre ? ` · ${profile.genre}` : ""}
          </p>
        </div>
        <p className="muted text-sm">
          Weakest: <span className="text-[var(--text)]">{worst.axis}</span>
        </p>
      </div>

      <div className="grid gap-8 lg:grid-cols-[1fr_1.1fr]">
        <div>
          {/* One series, so no legend: the heading names it. 100 is nothing to fix. */}
          <ResponsiveContainer width="100%" height={280}>
            <RadarChart data={data} outerRadius="72%">
              <PolarGrid stroke="#272c34" />
              <PolarAngleAxis
                dataKey="axis"
                tick={{ fill: "#9aa3ad", fontSize: 12 }}
              />
              <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
              <Radar
                dataKey="score"
                stroke="#3987e5"
                strokeWidth={2}
                fill="#3987e5"
                fillOpacity={0.25}
                isAnimationActive={false}
              />
              <Tooltip
                cursor={false}
                contentStyle={{
                  background: "#0f1114",
                  border: "1px solid #272c34",
                  borderRadius: "0.5rem",
                  color: "#e6e8ea",
                }}
                formatter={(value: number) => [`${value} / 100`, ""]}
              />
            </RadarChart>
          </ResponsiveContainer>

          {/* The chart is a shape; the numbers are also readable as a table. */}
          <dl className="mt-2 grid grid-cols-3 gap-x-4 gap-y-1 text-sm">
            {data.map((entry) => (
              <div key={entry.axis} className="flex justify-between gap-2">
                <dt className="muted truncate">{entry.axis}</dt>
                <dd>{entry.score}</dd>
              </div>
            ))}
          </dl>
        </div>

        <div className="space-y-4">
          <p className="leading-relaxed">{profile.qualitative_summary}</p>

          <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
            <Measurement
              label="Crest factor"
              value={`${profile.dynamic_range.crest_factor_db.toFixed(1)} dB`}
              note={`${profile.dynamic_range.loud_quiet_spread_db.toFixed(0)} dB passage spread`}
            />
            <Measurement
              label="Signal to noise"
              value={`${profile.noise_floor.snr_db.toFixed(0)} dB`}
              note={profile.noise_floor.has_hum ? `hum at ${profile.noise_floor.hum_freq_hz?.toFixed(0)} Hz` : undefined}
            />
            <Measurement
              label="Room RT60"
              value={
                profile.room_quality.measurement === "none"
                  ? "not measurable"
                  : `${(profile.room_quality.reverb_tail_ms / 1000).toFixed(2)} s`
              }
              note={
                profile.room_quality.measurement === "none"
                  ? undefined
                  : `${profile.room_quality.treated ? "treated" : "live"}, from ${profile.room_quality.probes} ${profile.room_quality.measurement}`
              }
            />
            <Measurement
              label="Pitch drift"
              value={`${profile.pitch_stability.drift_cents.toFixed(0)} cents`}
              note={profile.pitch_stability.needs_correction ? "worth correcting" : "in tune"}
            />
            <Measurement
              label="Sibilance"
              value={`${profile.sibilance.peak_freq_hz.toFixed(0)} Hz`}
              note={`ratio ${profile.sibilance.ratio.toFixed(3)}`}
            />
            <Measurement
              label="Source bandwidth"
              value={`${(profile.bandwidth_hz / 1000).toFixed(1)} kHz`}
            />
          </dl>

          {profile.analysis_notes.length > 0 && (
            <ul className="muted space-y-1 border-t border-[var(--border)] pt-3 text-sm">
              {profile.analysis_notes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </section>
  );
}

function Measurement({
  label,
  value,
  note,
}: {
  label: string;
  value: string;
  note?: string;
}) {
  return (
    <div>
      <dt className="muted">{label}</dt>
      <dd>
        {value}
        {note && <span className="muted"> · {note}</span>}
      </dd>
    </div>
  );
}
