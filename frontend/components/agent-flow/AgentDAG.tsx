'use client'

import { useMemo } from 'react'
import ReactFlow, {
  Background,
  Handle,
  Position,
  type Edge,
  type EdgeTypes,
  type Node,
  type NodeProps,
  type EdgeProps,
  type NodeTypes,
} from 'reactflow'
import 'reactflow/dist/style.css'

import type { AgentRun, ProjectStatus } from '@/lib/types'

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

function findStyle(slot: AgentSlot, traces: AgentRun[], isTerminal: boolean): SlotStyle {
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
  const status = latest?.status ?? 'idle'
  // When the workflow has finished, a trace stuck in 'running' is stale — show success.
  if (isTerminal && status === 'running') return STATUS_STYLE.success
  return STATUS_STYLE[status] ?? STATUS_STYLE.idle
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
// `data.active` controls whether the edge is highlighted (orange) or dormant (gray).

function ReworkEdge({ sourceX, sourceY, targetX, targetY, data }: EdgeProps) {
  const active = (data as { active?: boolean } | undefined)?.active ?? false
  const arcY = Math.max(sourceY, targetY) + 110
  const path = `M${sourceX},${sourceY} C${sourceX},${arcY} ${targetX},${arcY} ${targetX},${targetY}`
  const midX = (sourceX + targetX) / 2
  const midY = arcY + 6

  const stroke = active ? '#fb923c' : '#d1d5db'
  const labelFill = active ? '#c2410c' : '#9ca3af'
  const bgFill = active ? '#fff7ed' : '#f9fafb'
  const bgStroke = active ? '#fed7aa' : '#e5e7eb'

  return (
    <g style={{ opacity: active ? 1 : 0.5 }}>
      <path d={path} stroke={stroke} strokeWidth={1.5} strokeDasharray="5 4" fill="none" />
      {/* show label pill only when active */}
      {active && (
        <>
          <rect
            x={midX - 25}
            y={midY - 10}
            width={50}
            height={18}
            rx={5}
            fill={bgFill}
            stroke={bgStroke}
            strokeWidth={1}
          />
          <text
            x={midX}
            y={midY + 4}
            textAnchor="middle"
            fill={labelFill}
            fontSize={11}
            fontWeight={500}
          >
            rework
          </text>
        </>
      )}
    </g>
  )
}

// ── React Flow type registries ────────────────────────────────────────────────

const NODE_TYPES: NodeTypes = Object.freeze({ agent: AgentNode })
const EDGE_TYPES: EdgeTypes = Object.freeze({ rework: ReworkEdge })

// ── AgentDAG ──────────────────────────────────────────────────────────────────

export function AgentDAG({ traces, projectStatus }: { traces: AgentRun[]; projectStatus?: ProjectStatus }) {
  const isTerminal = projectStatus === 'completed' || projectStatus === 'qa_failed' || projectStatus === 'failed'
  const { nodes, edges } = useMemo(() => {
    // Derive which rework targets were actually triggered
    const reworkTargets = new Set<string>()
    traces.forEach((t) => {
      if (t.agent_name.includes('QA') && t.status === 'success') {
        const out = t.output as { passed?: boolean; issues?: { target_agent?: string }[] }
        if (out.passed === false) {
          out.issues?.forEach((issue) => {
            const tgt = (issue.target_agent ?? '').toLowerCase()
            if (tgt.includes('collector')) reworkTargets.add('collector')
            if (tgt.includes('analyst')) reworkTargets.add('analyst')
            if (tgt.includes('writer')) reworkTargets.add('writer')
          })
        }
      }
    })

    // Did QA pass at least once?
    const qaPassed = traces.some(
      (t) =>
        t.agent_name.includes('QA') &&
        t.status === 'success' &&
        (t.output as { passed?: boolean }).passed === true
    )

    const nodes: Node[] = SLOTS.map((slot) => ({
      id: slot.id,
      type: 'agent',
      position: { x: slot.x, y: NODE_Y },
      data: { label: slot.label, slotStyle: findStyle(slot, traces, isTerminal) },
      draggable: false,
      selectable: false,
      connectable: false,
    }))

    const edges: Edge[] = [
      // ── forward flow ──────────────────────────────────────────────────────
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
      // QA → END: show "pass" label only when QA actually passed
      {
        id: 'q-e',
        source: 'qa',
        sourceHandle: 'right',
        target: 'end',
        targetHandle: 'left',
        type: 'smoothstep',
        ...(qaPassed
          ? {
              label: 'pass',
              labelStyle: { fontSize: 11, fontWeight: 600, fill: '#16a34a' },
              labelBgStyle: { fill: '#f0fdf4' },
              labelBgPadding: [5, 3] as [number, number],
              labelBgBorderRadius: 4,
              style: { stroke: '#22c55e', strokeWidth: 1.5 },
            }
          : { style: { stroke: '#94a3b8', strokeWidth: 1.5 } }),
      },
      // ── rework arcs — always structurally present, highlighted only when triggered ──
      {
        id: 'q-w',
        source: 'qa',
        sourceHandle: 'bot-src',
        target: 'writer',
        targetHandle: 'bot-tgt',
        type: 'rework',
        data: { active: reworkTargets.has('writer') },
      },
      {
        id: 'q-a',
        source: 'qa',
        sourceHandle: 'bot-src',
        target: 'analyst',
        targetHandle: 'bot-tgt',
        type: 'rework',
        data: { active: reworkTargets.has('analyst') },
      },
      {
        id: 'q-c',
        source: 'qa',
        sourceHandle: 'bot-src',
        target: 'collector',
        targetHandle: 'bot-tgt',
        type: 'rework',
        data: { active: reworkTargets.has('collector') },
      },
    ]

    return { nodes, edges }
  }, [traces, isTerminal])

  return (
    <div
      style={{ height: 340 }}
      className="overflow-hidden rounded-lg border border-gray-200 bg-white"
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={NODE_TYPES}
        edgeTypes={EDGE_TYPES}
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
