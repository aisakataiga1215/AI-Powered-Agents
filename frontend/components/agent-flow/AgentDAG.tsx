'use client'

import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
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

import { api } from '@/lib/api'
import type { AgentRun, GraphResponse, ProjectStatus } from '@/lib/types'

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
  { id: 'collect_sources', label: 'Collector', x: 0, matcher: 'Collector' },
  { id: 'analyze_competitors', label: 'Analyst', x: GAP * 1, matcher: 'Analyst' },
  { id: 'write_report', label: 'Writer', x: GAP * 2, matcher: 'Writer' },
  { id: 'qa_review', label: 'QA', x: GAP * 3, matcher: 'QA' },
  { id: '__end__', label: 'END', x: GAP * 4, matcher: null },
]

const NODE_POSITION: Record<string, { x: number; y: number; matcher: string | null }> = {
  collect_sources: { x: 0, y: NODE_Y, matcher: 'Collector' },
  analyze_competitors: { x: GAP, y: NODE_Y, matcher: 'Analyst' },
  write_report: { x: GAP * 2, y: NODE_Y, matcher: 'Writer' },
  qa_review: { x: GAP * 3, y: NODE_Y, matcher: 'QA' },
  finalize_report: { x: GAP * 4, y: 25, matcher: null },
  mark_qa_failed: { x: GAP * 4, y: 118, matcher: null },
  handle_rework: { x: GAP * 3, y: 205, matcher: null },
  __end__: { x: GAP * 5, y: NODE_Y, matcher: null },
}

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
  const graphQuery = useQuery({
    queryKey: ['workflow-graph'],
    queryFn: () => api.getGraph(),
    staleTime: 60_000,
    retry: false,
  })
  const isTerminal = projectStatus === 'completed' || projectStatus === 'qa_failed' || projectStatus === 'failed'
  const { nodes, edges } = useMemo(() => {
    const graph = graphQuery.data
    // Derive which rework targets were actually triggered
    const reworkTargets = new Set<string>()
    traces.forEach((t) => {
      if (t.agent_name.includes('QA') && t.status === 'success') {
        const out = t.output as { passed?: boolean; issues?: { target_agent?: string }[] }
        if (out.passed === false) {
          out.issues?.forEach((issue) => {
            const tgt = (issue.target_agent ?? '').toLowerCase()
            if (tgt.includes('collector')) reworkTargets.add('collect_sources')
            if (tgt.includes('analyst')) reworkTargets.add('analyze_competitors')
            if (tgt.includes('writer')) reworkTargets.add('write_report')
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

    const visibleBackendNodes = graph?.nodes
      ?.filter((node) => NODE_POSITION[node.id])
      .map((node) => {
        const pos = NODE_POSITION[node.id]
        const slot: AgentSlot = {
          id: node.id,
          label: node.label,
          x: pos.x,
          matcher: pos.matcher,
        }
        return {
          id: node.id,
          type: 'agent',
          position: { x: pos.x, y: pos.y },
          data: { label: node.label, slotStyle: findStyle(slot, traces, isTerminal) },
          draggable: false,
          selectable: false,
          connectable: false,
        } satisfies Node
      })

    const nodes: Node[] = visibleBackendNodes?.length
      ? visibleBackendNodes
      : SLOTS.map((slot) => ({
          id: slot.id,
          type: 'agent',
          position: { x: slot.x, y: NODE_Y },
          data: { label: slot.label, slotStyle: findStyle(slot, traces, isTerminal) },
          draggable: false,
          selectable: false,
          connectable: false,
        }))

    const backendEdges = buildEdgesFromGraph(graph, reworkTargets, qaPassed)
    const edges: Edge[] = backendEdges.length > 0 ? backendEdges : [
      // ── forward flow ──────────────────────────────────────────────────────
      {
        id: 'c-a',
        source: 'collect_sources',
        sourceHandle: 'right',
        target: 'analyze_competitors',
        targetHandle: 'left',
        type: 'smoothstep',
        style: { stroke: '#94a3b8', strokeWidth: 1.5 },
      },
      {
        id: 'a-w',
        source: 'analyze_competitors',
        sourceHandle: 'right',
        target: 'write_report',
        targetHandle: 'left',
        type: 'smoothstep',
        style: { stroke: '#94a3b8', strokeWidth: 1.5 },
      },
      {
        id: 'w-q',
        source: 'write_report',
        sourceHandle: 'right',
        target: 'qa_review',
        targetHandle: 'left',
        type: 'smoothstep',
        style: { stroke: '#94a3b8', strokeWidth: 1.5 },
      },
      // QA → END: show "pass" label only when QA actually passed
      {
        id: 'q-e',
        source: 'qa_review',
        sourceHandle: 'right',
        target: '__end__',
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
        source: 'qa_review',
        sourceHandle: 'bot-src',
        target: 'write_report',
        targetHandle: 'bot-tgt',
        type: 'rework',
        data: { active: reworkTargets.has('write_report') },
      },
      {
        id: 'q-a',
        source: 'qa_review',
        sourceHandle: 'bot-src',
        target: 'analyze_competitors',
        targetHandle: 'bot-tgt',
        type: 'rework',
        data: { active: reworkTargets.has('analyze_competitors') },
      },
      {
        id: 'q-c',
        source: 'qa_review',
        sourceHandle: 'bot-src',
        target: 'collect_sources',
        targetHandle: 'bot-tgt',
        type: 'rework',
        data: { active: reworkTargets.has('collect_sources') },
      },
    ]

    return { nodes, edges }
  }, [traces, isTerminal, graphQuery.data])

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

function buildEdgesFromGraph(
  graph: GraphResponse | undefined,
  reworkTargets: Set<string>,
  qaPassed: boolean
): Edge[] {
  if (!graph?.edges?.length) return []
  return graph.edges
    .filter((edge) => NODE_POSITION[edge.source] && NODE_POSITION[edge.target])
    .map((edge) => {
      const isRework = edge.source === 'handle_rework'
      const source = isRework ? 'qa_review' : edge.source
      const target = edge.target
      const isPass = edge.source === 'qa_review' && edge.target === 'finalize_report'
      const isFail = edge.source === 'qa_review' && edge.target === 'mark_qa_failed'
      const active = isRework && reworkTargets.has(target)
      return {
        id: `${edge.source}-${edge.target}`,
        source,
        sourceHandle: isRework ? 'bot-src' : 'right',
        target,
        targetHandle: isRework ? 'bot-tgt' : 'left',
        type: isRework ? 'rework' : 'smoothstep',
        data: isRework ? { active } : undefined,
        label: isPass && qaPassed ? 'pass' : isFail ? 'fail' : undefined,
        labelStyle: isPass && qaPassed
          ? { fontSize: 11, fontWeight: 600, fill: '#16a34a' }
          : isFail
            ? { fontSize: 11, fontWeight: 600, fill: '#dc2626' }
            : undefined,
        labelBgStyle: isPass && qaPassed
          ? { fill: '#f0fdf4' }
          : isFail
            ? { fill: '#fef2f2' }
            : undefined,
        labelBgPadding: (isPass || isFail) ? [5, 3] as [number, number] : undefined,
        labelBgBorderRadius: (isPass || isFail) ? 4 : undefined,
        style: {
          stroke: isPass && qaPassed ? '#22c55e' : isFail ? '#ef4444' : '#94a3b8',
          strokeWidth: 1.5,
        },
      } satisfies Edge
    })
}
