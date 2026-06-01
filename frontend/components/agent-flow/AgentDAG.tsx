'use client'

import { useMemo } from 'react'
import ReactFlow, {
  Background,
  Handle,
  Position,
  type Edge,
  type Node,
  type NodeProps,
  type EdgeProps,
} from 'reactflow'
import 'reactflow/dist/style.css'

import type { AgentRun } from '@/lib/types'

// ── Layout constants ──────────────────────────────────────────────────────────

const GAP = 210 // horizontal center-to-center distance
const NODE_Y = 70 // top-left y of each node

// ── Slot definitions ──────────────────────────────────────────────────────────

interface AgentSlot {
  id: string
  label: string
  x: number
  matcher: string | null
}

const SLOTS: AgentSlot[] = [
  { id: 'collector', label: 'Collector', x: 0, matcher: 'Collector' },
  { id: 'analyst', label: 'Analyst', x: GAP * 1, matcher: 'Analyst' },
  { id: 'writer', label: 'Writer', x: GAP * 2, matcher: 'Writer' },
  { id: 'qa', label: 'QA', x: GAP * 3, matcher: 'QA' },
  { id: 'end', label: 'END', x: GAP * 4, matcher: null },
]

// ── Node colour by status ─────────────────────────────────────────────────────

interface SlotStyle {
  bg: string
  border: string
  color: string
}

const STATUS_STYLE: Record<string, SlotStyle> = {
  success: { bg: '#dcfce7', border: '#4ade80', color: '#166534' },
  failed: { bg: '#fee2e2', border: '#f87171', color: '#991b1b' },
  running: { bg: '#dbeafe', border: '#60a5fa', color: '#1e3a8a' },
  idle: { bg: '#f9fafb', border: '#d1d5db', color: '#9ca3af' },
}

function findStyle(slot: AgentSlot, traces: AgentRun[]): SlotStyle {
  if (!slot.matcher) {
    const passed = traces.some(
      (t) =>
        t.agent_name.includes('QA') &&
        t.status === 'success' &&
        (t.output as { passed?: boolean }).passed === true
    )
    return passed ? STATUS_STYLE.success : STATUS_STYLE.idle
  }
  const latest = [...traces].reverse().find((t) => t.agent_name.includes(slot.matcher!))
  return STATUS_STYLE[latest?.status ?? 'idle'] ?? STATUS_STYLE.idle
}

// ── Custom node — exposes bottom handles for rework arcs ──────────────────────

function AgentNode({ data }: NodeProps) {
  const { label, slotStyle: s } = data as { label: string; slotStyle: SlotStyle }
  return (
    <div
      style={{
        background: s.bg,
        border: `1.5px solid ${s.border}`,
        borderRadius: 8,
        padding: '9px 20px',
        minWidth: 110,
        textAlign: 'center',
        fontWeight: 600,
        fontSize: 13,
        color: s.color,
        userSelect: 'none',
        boxShadow: '0 1px 3px rgba(0,0,0,.07)',
      }}
    >
      {/* forward-flow handles */}
      <Handle type="target" position={Position.Left} id="left" style={{ opacity: 0 }} />
      <Handle type="source" position={Position.Right} id="right" style={{ opacity: 0 }} />
      {/* rework handles — bottom edge */}
      <Handle type="source" position={Position.Bottom} id="bot-src" style={{ opacity: 0 }} />
      <Handle type="target" position={Position.Bottom} id="bot-tgt" style={{ opacity: 0 }} />
      {label}
    </div>
  )
}

// ── Custom rework edge — explicit cubic Bézier below the node row ─────────────

function ReworkEdge({ sourceX, sourceY, targetX, targetY, label }: EdgeProps) {
  // Both handles are at the bottom of their nodes (~same Y).
  // Arc 110 px below to keep clear of the node row.
  const arcY = Math.max(sourceY, targetY) + 110
  const path = `M${sourceX},${sourceY} C${sourceX},${arcY} ${targetX},${arcY} ${targetX},${targetY}`
  const midX = (sourceX + targetX) / 2
  const midY = arcY + 6

  return (
    <g>
      <path d={path} stroke="#fb923c" strokeWidth={1.5} strokeDasharray="5 4" fill="none" />
      {/* label pill */}
      <rect
        x={midX - 25}
        y={midY - 10}
        width={50}
        height={18}
        rx={5}
        fill="#fff7ed"
        stroke="#fed7aa"
        strokeWidth={1}
      />
      <text x={midX} y={midY + 4} textAnchor="middle" fill="#c2410c" fontSize={11} fontWeight={500}>
        {typeof label === 'string' ? label : 'rework'}
      </text>
    </g>
  )
}

// ── React Flow type registries ────────────────────────────────────────────────

const nodeTypes = { agent: AgentNode }
const edgeTypes = { rework: ReworkEdge }

// ── AgentDAG ──────────────────────────────────────────────────────────────────

export function AgentDAG({ traces }: { traces: AgentRun[] }) {
  const { nodes, edges } = useMemo(() => {
    const nodes: Node[] = SLOTS.map((slot) => ({
      id: slot.id,
      type: 'agent',
      position: { x: slot.x, y: NODE_Y },
      data: { label: slot.label, slotStyle: findStyle(slot, traces) },
      draggable: false,
      selectable: false,
      connectable: false,
    }))

    const edges: Edge[] = [
      // ── forward flow (top row, right→left handles) ──────────────────────
      {
        id: 'c-a',
        source: 'collector',
        sourceHandle: 'right',
        target: 'analyst',
        targetHandle: 'left',
        type: 'smoothstep',
        style: { stroke: '#94a3b8', strokeWidth: 1.5 },
      },
      {
        id: 'a-w',
        source: 'analyst',
        sourceHandle: 'right',
        target: 'writer',
        targetHandle: 'left',
        type: 'smoothstep',
        style: { stroke: '#94a3b8', strokeWidth: 1.5 },
      },
      {
        id: 'w-q',
        source: 'writer',
        sourceHandle: 'right',
        target: 'qa',
        targetHandle: 'left',
        type: 'smoothstep',
        style: { stroke: '#94a3b8', strokeWidth: 1.5 },
      },
      {
        id: 'q-e',
        source: 'qa',
        sourceHandle: 'right',
        target: 'end',
        targetHandle: 'left',
        type: 'smoothstep',
        label: 'pass',
        labelStyle: { fontSize: 11, fontWeight: 600, fill: '#16a34a' },
        labelBgStyle: { fill: '#f0fdf4' },
        labelBgPadding: [5, 3] as [number, number],
        labelBgBorderRadius: 4,
        style: { stroke: '#22c55e', strokeWidth: 1.5 },
      },
      // ── rework arcs (bottom handles → arc below node row) ───────────────
      {
        id: 'q-w',
        source: 'qa',
        sourceHandle: 'bot-src',
        target: 'writer',
        targetHandle: 'bot-tgt',
        type: 'rework',
        label: 'rework',
      },
      {
        id: 'q-a',
        source: 'qa',
        sourceHandle: 'bot-src',
        target: 'analyst',
        targetHandle: 'bot-tgt',
        type: 'rework',
        label: 'rework',
      },
      {
        id: 'q-c',
        source: 'qa',
        sourceHandle: 'bot-src',
        target: 'collector',
        targetHandle: 'bot-tgt',
        type: 'rework',
        label: 'rework',
      },
    ]

    return { nodes, edges }
  }, [traces])

  return (
    <div
      style={{ height: 340 }}
      className="overflow-hidden rounded-lg border border-gray-200 bg-white"
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        fitView
        fitViewOptions={{ padding: 0.25 }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        panOnDrag={false}
        zoomOnScroll={false}
        zoomOnPinch={false}
        zoomOnDoubleClick={false}
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={20} color="#f1f5f9" />
      </ReactFlow>
    </div>
  )
}
