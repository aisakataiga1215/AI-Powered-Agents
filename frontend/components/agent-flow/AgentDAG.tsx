'use client'

/**
 * AgentDAG — visualizes the LangGraph workflow as a static DAG.
 *
 * Node fill color is derived from the latest AgentRun status for each
 * agent. The "rework" edges from QA back to upstream agents are dashed
 * to signal that they only fire when QA fails.
 */

import { useMemo } from 'react'
import ReactFlow, {
  Background,
  type Edge,
  type Node,
  type NodeProps,
} from 'reactflow'
import 'reactflow/dist/style.css'

import type { AgentRun } from '@/lib/types'

interface AgentDAGProps {
  traces: AgentRun[]
}

interface AgentSlot {
  id: 'collector' | 'analyst' | 'writer' | 'qa' | 'end'
  label: string
  x: number
  matcher: string | null
}

const SLOTS: AgentSlot[] = [
  { id: 'collector', label: 'Collector', x: 30, matcher: 'Collector' },
  { id: 'analyst', label: 'Analyst', x: 200, matcher: 'Analyst' },
  { id: 'writer', label: 'Writer', x: 370, matcher: 'Writer' },
  { id: 'qa', label: 'QA', x: 540, matcher: 'QA' },
  { id: 'end', label: 'END', x: 710, matcher: null },
]

interface SlotStyle {
  background: string
  border: string
  textColor: string
}

const STATUS_STYLE: Record<string, SlotStyle> = {
  success: {
    background: '#dcfce7',
    border: '1px solid #4ade80',
    textColor: '#166534',
  },
  failed: {
    background: '#fee2e2',
    border: '1px solid #f87171',
    textColor: '#991b1b',
  },
  running: {
    background: '#dbeafe',
    border: '1px solid #60a5fa',
    textColor: '#1e3a8a',
  },
  skipped: {
    background: '#f3f4f6',
    border: '1px solid #d1d5db',
    textColor: '#374151',
  },
  idle: {
    background: '#f3f4f6',
    border: '1px solid #d1d5db',
    textColor: '#6b7280',
  },
}

function findStatus(slot: AgentSlot, traces: AgentRun[]): SlotStyle {
  if (slot.matcher === null) {
    // END node lights up green once we see a passing QA run.
    const qaPassed = traces.some(
      (t) =>
        t.agent_name.includes('QA') &&
        t.status === 'success' &&
        (t.output as { passed?: boolean })?.passed === true
    )
    return qaPassed ? STATUS_STYLE.success : STATUS_STYLE.idle
  }
  const matched = traces
    .filter((t) => t.agent_name.includes(slot.matcher!))
    .slice()
    .reverse() // newest last in the timeline; reverse to inspect newest first
  if (matched.length === 0) return STATUS_STYLE.idle
  const latest = matched[0]
  return STATUS_STYLE[latest.status] ?? STATUS_STYLE.idle
}

export function AgentDAG({ traces }: AgentDAGProps) {
  const { nodes, edges } = useMemo(() => {
    const built: Node[] = SLOTS.map((slot) => {
      const style = findStatus(slot, traces)
      return {
        id: slot.id,
        type: 'default',
        data: { label: slot.label },
        position: { x: slot.x, y: 80 },
        sourcePosition: 'right' as NodeProps['sourcePosition'],
        targetPosition: 'left' as NodeProps['targetPosition'],
        style: {
          background: style.background,
          border: style.border,
          color: style.textColor,
          padding: '8px 12px',
          minWidth: 100,
          fontWeight: 500,
          textAlign: 'center' as const,
        },
        draggable: false,
        connectable: false,
        selectable: false,
      }
    })

    const builtEdges: Edge[] = [
      {
        id: 'collector-analyst',
        source: 'collector',
        target: 'analyst',
        animated: false,
        type: 'default',
        style: { stroke: '#94a3b8' },
      },
      {
        id: 'analyst-writer',
        source: 'analyst',
        target: 'writer',
        type: 'default',
        style: { stroke: '#94a3b8' },
      },
      {
        id: 'writer-qa',
        source: 'writer',
        target: 'qa',
        type: 'default',
        style: { stroke: '#94a3b8' },
      },
      {
        id: 'qa-end',
        source: 'qa',
        target: 'end',
        label: 'pass',
        labelStyle: { fontSize: 11, fill: '#16a34a' },
        labelBgPadding: [4, 2],
        labelBgStyle: { fill: '#f0fdf4' },
        type: 'default',
        style: { stroke: '#22c55e' },
      },
      {
        id: 'qa-collector',
        source: 'qa',
        target: 'collector',
        label: 'rework',
        labelStyle: { fontSize: 11, fill: '#c2410c' },
        labelBgPadding: [4, 2],
        labelBgStyle: { fill: '#fff7ed' },
        type: 'default',
        animated: false,
        style: { strokeDasharray: '5,5', stroke: '#fb923c' },
      },
      {
        id: 'qa-analyst',
        source: 'qa',
        target: 'analyst',
        label: 'rework',
        labelStyle: { fontSize: 11, fill: '#c2410c' },
        labelBgPadding: [4, 2],
        labelBgStyle: { fill: '#fff7ed' },
        type: 'default',
        animated: false,
        style: { strokeDasharray: '5,5', stroke: '#fb923c' },
      },
      {
        id: 'qa-writer',
        source: 'qa',
        target: 'writer',
        label: 'rework',
        labelStyle: { fontSize: 11, fill: '#c2410c' },
        labelBgPadding: [4, 2],
        labelBgStyle: { fill: '#fff7ed' },
        type: 'default',
        animated: false,
        style: { strokeDasharray: '5,5', stroke: '#fb923c' },
      },
    ]

    return { nodes: built, edges: builtEdges }
  }, [traces])

  return (
    <div
      style={{ height: 260 }}
      className="rounded-lg border border-gray-200 bg-white"
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
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
        <Background gap={16} color="#f1f5f9" />
      </ReactFlow>
    </div>
  )
}
