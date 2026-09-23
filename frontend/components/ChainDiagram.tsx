"use client";

import {
  Background,
  Controls,
  Position,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useMemo, useState } from "react";

import { TIERS, TIER_LABELS, type SignalChain, type Tier } from "@/lib/types";

const NODE_WIDTH = 190;
const NODE_GAP = 70;

export function ChainDiagram({ chains }: { chains: SignalChain[] }) {
  const [tier, setTier] = useState<Tier>(chains[0]?.tier ?? "FREE");
  const [selected, setSelected] = useState<number | null>(null);

  const chain = chains.find((candidate) => candidate.tier === tier);
  const available = TIERS.filter((candidate) =>
    chains.some((existing) => existing.tier === candidate),
  );

  const { nodes, edges } = useMemo(() => buildGraph(chain), [chain]);
  const step = selected !== null ? chain?.steps[selected] : undefined;

  if (!chain) {
    return (
      <section className="panel p-6">
        <h2 className="mb-2 text-lg font-medium">Chain</h2>
        <p className="muted">
          No chains came back with this analysis — the plugin catalog was unavailable.
        </p>
      </section>
    );
  }

  const total = totalPrice(chain);

  return (
    <section className="panel p-6">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-4">
        <h2 className="text-lg font-medium">Chain</h2>
        <div className="flex gap-1 rounded-lg border border-[var(--border)] p-1">
          {available.map((candidate) => (
            <button
              key={candidate}
              type="button"
              onClick={() => {
                setTier(candidate);
                setSelected(null);
              }}
              aria-pressed={candidate === tier}
              className={`rounded-md px-3 py-1.5 text-sm transition ${
                candidate === tier ? "bg-white text-black" : "muted hover:text-[var(--text)]"
              }`}
            >
              {TIER_LABELS[candidate]}
            </button>
          ))}
        </div>
      </div>

      <p className="muted mb-4 text-sm">
        {chain.steps.length} steps in signal order ·{" "}
        {total === 0 ? "free" : `about $${total.toFixed(0)} to buy outright`}
      </p>

      <div className="h-[260px] rounded-lg border border-[var(--border)]">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          fitView
          nodesDraggable={false}
          nodesConnectable={false}
          proOptions={{ hideAttribution: true }}
          onNodeClick={(_, node) => setSelected(Number(node.id))}
        >
          <Background color="#272c34" gap={18} />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>

      {step ? (
        <div className="mt-4 space-y-2 rounded-lg border border-[var(--border)] p-4">
          <div className="flex items-baseline justify-between gap-4">
            <h3 className="font-medium">{step.plugin_name}</h3>
            <span className="muted text-sm">
              {step.category.replace(/_/g, " ")} · {step.price}
            </span>
          </div>
          <p className="text-sm leading-relaxed">{step.suggested_settings}</p>
          <p className="muted text-sm leading-relaxed">{step.why}</p>
          {step.purchase_url && (
            <a
              href={step.purchase_url}
              target="_blank"
              rel="noreferrer noopener"
              className="inline-block text-sm text-series underline"
            >
              {new URL(step.purchase_url).host}
            </a>
          )}
        </div>
      ) : (
        <p className="muted mt-4 text-sm">Select a step to see its settings.</p>
      )}
    </section>
  );
}

function buildGraph(chain: SignalChain | undefined): { nodes: Node[]; edges: Edge[] } {
  if (!chain) return { nodes: [], edges: [] };

  const nodes: Node[] = chain.steps.map((step, index) => ({
    id: String(index),
    position: { x: index * (NODE_WIDTH + NODE_GAP), y: 0 },
    data: {
      label: (
        <div className="px-1 py-0.5 text-left">
          <div className="muted text-[10px] uppercase tracking-wide">
            {step.category.replace(/_/g, " ")}
          </div>
          <div className="truncate text-sm">{step.plugin_name}</div>
        </div>
      ),
    },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    style: {
      width: NODE_WIDTH,
      background: "#171a1f",
      border: "1px solid #272c34",
      borderRadius: 10,
      color: "#e6e8ea",
    },
  }));

  const edges: Edge[] = chain.steps.slice(1).map((_, index) => ({
    id: `${index}-${index + 1}`,
    source: String(index),
    target: String(index + 1),
    animated: false,
    style: { stroke: "#3b424c" },
  }));

  return { nodes, edges };
}

/** A plugin used twice in one chain is bought once. */
function totalPrice(chain: SignalChain): number {
  const unique = new Map(chain.steps.map((step) => [step.plugin_name, step.price]));
  let total = 0;
  for (const price of unique.values()) {
    const digits = price.replace(/[^0-9.]/g, "");
    total += digits ? Number.parseFloat(digits) : 0;
  }
  return total;
}
