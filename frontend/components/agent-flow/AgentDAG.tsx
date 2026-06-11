'use client'

import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import ReactFlow, {
  Background,
  Panel,
  Handle,
  Position,
  MarkerType,
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

const GAP = 200
const NODE_Y = 80
const NODE_W = 150

// ── Slot definitions ──────────────────────────────────────────────────────────

interface AgentSlot {
  id: string
  label: string
  subtitle: string
  icon: string
  x: number
  matcher: string | null
}

const SLOTS: AgentSlot[] = [
  { id: 'collect_sources',       label: 'Collector', subtitle: '数据采集', icon: '📡', x: 0,        matcher: 'Collector' },
  { id: 'analyze_competitors',   label: 'Analyst',   subtitle: '竞品分析', icon: '🧠', x: GAP,      matcher: 'Analyst' },
  { id: 'write_report',          label: 'Writer',    subtitle: '报告撰写', icon: '📝', x: GAP * 2,  matcher: 'Writer' },
  { id: 'qa_review',             label: 'QA',        subtitle: '质量审核', icon: '🛡️', x: GAP * 3, matcher: 'QA' },
  { id: '__end__',               label: 'END',       subtitle: '完成',     icon: '🏁', x: GAP * 4,  matcher: null },
]

const NODE_POSITION: Record<string, { x: number; y: number; matcher: string | null }> = {}
for (const s of SLOTS) {
  NODE_POSITION[s.id] = { x: s.x, y: NODE_Y, matcher: s.matcher }
}

// ── Theme ─────────────────────────────────────────────────────────────────────

const THEME = {
  success:  { accent: '#059669', bg: '#ecfdf5', border: '#a7f3d0', glow: 'rgba(16,185,129,0.25)' },
  failed:   { accent: '#e11d48', bg: '#fff1f2', border: '#fecdd3', glow: 'rgba(225,29,72,0.2)' },
  running:  { accent: '#2563eb', bg: '#eff6ff', border: '#bfdbfe', glow: 'rgba(37,99,235,0.3)' },
  idle:     { accent: '#94a3b8', bg: '#f8fafc', border: '#e2e8f0', glow: 'rgba(148,163,184,0.08)' },
  rework:   { stroke: '#f59e0b', bg: '#fffbeb' },
  pass:     { stroke: '#10b981' },
  normal:   { stroke: '#cbd5e1' },
}

interface SlotStyle {
  accent: string
  bg: string
  border: string
  glow: string
  pulse: boolean
}

const FALLBACK_STYLE: SlotStyle = {
  accent: THEME.idle.accent, bg: THEME.idle.bg, border: THEME.idle.border, glow: THEME.idle.glow, pulse: false,
}

function findStyle(slot: AgentSlot, traces: AgentRun[], isTerminal: boolean): SlotStyle {
  if (!slot.matcher) {
    const passed = traces.some(
      (t) => t.agent_name.includes('QA') && t.status === 'success' &&
        (t.output as { passed?: boolean }).passed === true
    )
    return passed
      ? { accent: THEME.success.accent, bg: THEME.success.bg, border: THEME.success.border, glow: THEME.success.glow, pulse: false }
      : FALLBACK_STYLE
  }
  const latest = [...traces].reverse().find((t) => t.agent_name.includes(slot.matcher!))
  const status = latest?.status ?? 'idle'
  if (isTerminal && status === 'running')
    return { accent: THEME.success.accent, bg: THEME.success.bg, border: THEME.success.border, glow: THEME.success.glow, pulse: false }
  if (status === 'success') return { accent: THEME.success.accent, bg: THEME.success.bg, border: THEME.success.border, glow: THEME.success.glow, pulse: false }
  if (status === 'failed')  return { accent: THEME.failed.accent,  bg: THEME.failed.bg,  border: THEME.failed.border,  glow: THEME.failed.glow,  pulse: false }
  if (status === 'running') return { accent: THEME.running.accent, bg: THEME.running.bg, border: THEME.running.border, glow: THEME.running.glow, pulse: true }
  return FALLBACK_STYLE
}

// ── Custom node ───────────────────────────────────────────────────────────────

function AgentNode({ data }: NodeProps) {
  const { label, icon, subtitle, slotStyle: s, isTerminal } = data as {
    label: string; icon: string; subtitle: string; slotStyle: SlotStyle; isTerminal: boolean
  }
  return (
    <div
      className={`agent-node ${s.pulse ? 'agent-node--pulse' : ''}`}
      style={{
        position: 'relative', width: NODE_W, background: s.bg, borderRadius: 12,
        border: '1px solid', borderColor: s.border, padding: '12px 16px', userSelect: 'none',
        boxShadow: s.pulse
          ? `0 0 0 3px ${s.glow}, 0 4px 16px ${s.glow}, 0 1px 3px rgba(0,0,0,.06)`
          : '0 1px 3px rgba(0,0,0,.04), 0 2px 8px rgba(0,0,0,.04)',
        transition: 'box-shadow 0.3s ease, border-color 0.3s ease, background 0.3s ease',
      }}
    >
      <div style={{ position: 'absolute', top: 10, right: 10, width: 8, height: 8, borderRadius: '50%',
        background: s.accent, boxShadow: s.pulse ? `0 0 6px ${s.glow}` : 'none',
        transition: 'background 0.3s ease' }} />
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
        <span style={{ fontSize: 16, lineHeight: 1 }}>{icon}</span>
        <span style={{ fontWeight: 700, fontSize: 13, color: '#1e293b', lineHeight: 1.3 }}>{label}</span>
      </div>
      <div style={{ fontSize: 11, color: '#64748b', paddingLeft: 24, lineHeight: 1.2 }}>{subtitle}</div>
      {!isTerminal && s.accent !== THEME.idle.accent && (
        <div style={{ marginTop: 8, paddingLeft: 24, display: 'flex', alignItems: 'center', gap: 4 }}>
          <div style={{ fontSize: 10, fontWeight: 600, color: s.accent,
            background: s.accent === THEME.running.accent ? 'rgba(37,99,235,0.08)' : 'rgba(5,150,105,0.08)',
            borderRadius: 4, padding: '1px 6px' }}>
            {s.accent === THEME.running.accent ? 'running' : 'done'}
          </div>
        </div>
      )}
      <Handle type="target" position={Position.Left} id="left" style={{ opacity: 0 }} />
      <Handle type="source" position={Position.Right} id="right" style={{ opacity: 0 }} />
      <Handle type="source" position={Position.Bottom} id="bot-src" style={{ opacity: 0 }} />
      <Handle type="target" position={Position.Bottom} id="bot-tgt" style={{ opacity: 0 }} />
    </div>
  )
}

// ── Rework edge ───────────────────────────────────────────────────────────────

function ReworkEdge({ sourceX, sourceY, targetX, targetY, data }: EdgeProps) {
  const active = (data as { active?: boolean } | undefined)?.active ?? false
  if (!active) return null
  const dy = 120
  const arcY = Math.max(sourceY, targetY) + dy
  const path = `M${sourceX},${sourceY} C${sourceX},${arcY} ${targetX},${arcY} ${targetX},${targetY}`
  const midX = (sourceX + targetX) / 2
  return (
    <g>
      <path d={path} stroke="rgba(245,158,11,0.12)" strokeWidth={5} fill="none" />
      <path d={path} stroke={THEME.rework.stroke} strokeWidth={2} strokeDasharray="6 4" fill="none"
        markerEnd="url(#rework-arrow)" />
      <rect x={midX - 36} y={arcY + 4} width={72} height={20} rx={6}
        fill={THEME.rework.bg} stroke="#fcd34d" strokeWidth={1} />
      <text x={midX} y={arcY + 18} textAnchor="middle" fill="#b45309" fontSize={11} fontWeight={600}>
        QA 打回
      </text>
    </g>
  )
}

// ── Legend ────────────────────────────────────────────────────────────────────

const LEGEND_ITEMS = [
  { color: THEME.success.accent, label: '已完成' },
  { color: THEME.running.accent, label: '运行中' },
  { color: THEME.failed.accent,  label: '失败' },
  { color: THEME.idle.accent,    label: '等待中' },
]

function Legend() {
  return (
    <div style={{ background: 'rgba(255,255,255,0.92)', backdropFilter: 'blur(8px)', border: '1px solid #e2e8f0',
      borderRadius: 10, padding: '8px 14px', fontSize: 11, display: 'flex', alignItems: 'center', gap: 14,
      boxShadow: '0 1px 5px rgba(0,0,0,.05)' }}>
      {LEGEND_ITEMS.map(({ color, label }) => (
        <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
          <div style={{ width: 9, height: 9, borderRadius: '50%', background: color }} />
          <span style={{ color: '#475569', fontWeight: 500 }}>{label}</span>
        </div>
      ))}
      <div style={{ width: 1, height: 16, background: '#e2e8f0' }} />
      <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
        <svg width="20" height="8" style={{ flexShrink: 0 }}>
          <line x1="0" y1="4" x2="20" y2="4" stroke={THEME.rework.stroke} strokeWidth="2" strokeDasharray="4 3" />
        </svg>
        <span style={{ color: '#475569', fontWeight: 500 }}>QA 打回</span>
      </div>
    </div>
  )
}

// ── Registries ────────────────────────────────────────────────────────────────

const NODE_TYPES: NodeTypes = Object.freeze({ agent: AgentNode })
const EDGE_TYPES: EdgeTypes = Object.freeze({ rework: ReworkEdge })

// ── Global styles ─────────────────────────────────────────────────────────────

const GLOBAL_STYLE_ID = 'agent-dag-styles'

function ensureGlobalStyles() {
  if (typeof document === 'undefined') return
  if (document.getElementById(GLOBAL_STYLE_ID)) return
  const style = document.createElement('style')
  style.id = GLOBAL_STYLE_ID
  style.textContent = `
    @keyframes agent-dag-pulse {
      0%, 100% { box-shadow: 0 0 0 3px var(--pulse-glow,rgba(37,99,235,0.3)), 0 4px 16px var(--pulse-glow,rgba(37,99,235,0.3)), 0 1px 3px rgba(0,0,0,.06); }
      50%      { box-shadow: 0 0 0 6px var(--pulse-glow,rgba(37,99,235,0.15)), 0 4px 24px var(--pulse-glow,rgba(37,99,235,0.15)), 0 1px 3px rgba(0,0,0,.06); }
    }
    .agent-node--pulse { animation: agent-dag-pulse 2s ease-in-out infinite; }
    .react-flow__attribution { display: none !important; }
  `
  document.head.appendChild(style)
}

// ── AgentDAG ──────────────────────────────────────────────────────────────────

export function AgentDAG({ traces, projectStatus }: { traces: AgentRun[]; projectStatus?: ProjectStatus }) {
  ensureGlobalStyles()

  const graphQuery = useQuery({
    queryKey: ['workflow-graph'], queryFn: () => api.getGraph(), staleTime: 60_000, retry: false,
  })
  const isTerminal = projectStatus === 'completed' || projectStatus === 'qa_failed' || projectStatus === 'failed'

  const { nodes, edges } = useMemo(() => {
    const graph = graphQuery.data
    const reworkTargets = new Set<string>()
    traces.forEach((t) => {
      if (t.agent_name.includes('QA') && t.status === 'success') {
        const out = t.output as { passed?: boolean; issues?: { target_agent?: string }[] }
        if (out.passed === false) {
          out.issues?.forEach((issue) => {
            const tgt = (issue.target_agent ?? '').toLowerCase()
            if (tgt.includes('collector')) reworkTargets.add('collect_sources')
            if (tgt.includes('analyst'))   reworkTargets.add('analyze_competitors')
            if (tgt.includes('writer'))    reworkTargets.add('write_report')
          })
        }
      }
    })

    const qaPassed = traces.some(
      (t) => t.agent_name.includes('QA') && t.status === 'success' &&
        (t.output as { passed?: boolean }).passed === true
    )

    const visibleBackendNodes = graph?.nodes
      ?.filter((node) => NODE_POSITION[node.id])
      .map((node) => {
        const slotSlot = SLOTS.find((s) => s.id === node.id)
        const slot: AgentSlot = slotSlot ?? {
          id: node.id, label: node.label, subtitle: '', icon: '⬡',
          x: NODE_POSITION[node.id]?.x ?? 0, matcher: NODE_POSITION[node.id]?.matcher ?? null,
        }
        return {
          id: node.id, type: 'agent',
          position: { x: NODE_POSITION[node.id]?.x ?? 0, y: NODE_Y },
          data: { label: node.label, icon: slot.icon, subtitle: slot.subtitle,
            slotStyle: findStyle(slot, traces, isTerminal), isTerminal },
          draggable: false, selectable: false, connectable: false,
        } satisfies Node
      })

    const nodes: Node[] = (visibleBackendNodes?.length ? visibleBackendNodes : SLOTS.map((slot) => ({
      id: slot.id, type: 'agent', position: { x: slot.x, y: NODE_Y },
      data: { label: slot.label, icon: slot.icon, subtitle: slot.subtitle,
        slotStyle: findStyle(slot, traces, isTerminal), isTerminal },
      draggable: false, selectable: false, connectable: false,
    })))

    const edgeStyle = { stroke: THEME.normal.stroke, strokeWidth: 1.5 }

    const defaultEdges: Edge[] = [
      { id: 'c-a', source: 'collect_sources', target: 'analyze_competitors', sourceHandle: 'right', targetHandle: 'left',
        type: 'smoothstep', markerEnd: { type: MarkerType.ArrowClosed, color: THEME.normal.stroke, width: 12, height: 12 }, style: edgeStyle },
      { id: 'a-w', source: 'analyze_competitors', target: 'write_report', sourceHandle: 'right', targetHandle: 'left',
        type: 'smoothstep', markerEnd: { type: MarkerType.ArrowClosed, color: THEME.normal.stroke, width: 12, height: 12 }, style: edgeStyle },
      { id: 'w-q', source: 'write_report', target: 'qa_review', sourceHandle: 'right', targetHandle: 'left',
        type: 'smoothstep', markerEnd: { type: MarkerType.ArrowClosed, color: THEME.normal.stroke, width: 12, height: 12 }, style: edgeStyle },
      { id: 'q-e', source: 'qa_review', sourceHandle: 'right', target: '__end__', targetHandle: 'left',
        type: 'smoothstep',
        markerEnd: { type: MarkerType.ArrowClosed, color: qaPassed ? THEME.pass.stroke : THEME.normal.stroke, width: 12, height: 12 },
        ...(qaPassed
          ? { label: '✓ PASS', labelStyle: { fontSize: 11, fontWeight: 700, fill: THEME.success.accent },
              labelBgStyle: { fill: THEME.success.bg }, labelBgPadding: [6, 4] as [number, number],
              labelBgBorderRadius: 5, style: { stroke: THEME.pass.stroke, strokeWidth: 2 } }
          : { style: edgeStyle }),
      },
      { id: 'q-w', source: 'qa_review', sourceHandle: 'bot-src', target: 'write_report',          targetHandle: 'bot-tgt', type: 'rework', data: { active: reworkTargets.has('write_report') } },
      { id: 'q-a', source: 'qa_review', sourceHandle: 'bot-src', target: 'analyze_competitors',   targetHandle: 'bot-tgt', type: 'rework', data: { active: reworkTargets.has('analyze_competitors') } },
      { id: 'q-c', source: 'qa_review', sourceHandle: 'bot-src', target: 'collect_sources',       targetHandle: 'bot-tgt', type: 'rework', data: { active: reworkTargets.has('collect_sources') } },
    ]

    const backendEdges = buildEdgesFromGraph(graph, reworkTargets, qaPassed)
    return { nodes, edges: backendEdges.length > 0 ? backendEdges : defaultEdges }
  }, [traces, isTerminal, graphQuery.data])

  return (
    <div style={{ height: 380 }} className="overflow-hidden rounded-xl border border-gray-200 bg-gradient-to-b from-gray-50 to-white">
      <svg width="0" height="0" style={{ position: 'absolute', pointerEvents: 'none' }}>
        <defs>
          <marker id="rework-arrow" viewBox="0 0 10 10" refX={8} refY={5} markerWidth={6} markerHeight={6} orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill={THEME.rework.stroke} />
          </marker>
        </defs>
      </svg>
      <ReactFlow
        nodes={nodes} edges={edges} nodeTypes={NODE_TYPES} edgeTypes={EDGE_TYPES}
        fitView fitViewOptions={{ padding: 0.25 }}
        nodesDraggable={false} nodesConnectable={false} elementsSelectable={false}
        panOnDrag={false} zoomOnScroll={false} zoomOnPinch={false} zoomOnDoubleClick={false}
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={24} color="#e2e8f0" size={1} />
        <Panel position="bottom-center"><Legend /></Panel>
      </ReactFlow>
    </div>
  )
}

// ── Edge builder from backend graph ───────────────────────────────────────────

function buildEdgesFromGraph(
  graph: GraphResponse | undefined, reworkTargets: Set<string>, qaPassed: boolean,
): Edge[] {
  if (!graph?.edges?.length) return []
  const VISIBLE = new Set(['collect_sources', 'analyze_competitors', 'write_report', 'qa_review', '__end__'])
  const seen = new Set<string>()
  const edges: Edge[] = []
  const normalColor = THEME.normal.stroke
  for (const edge of graph.edges) {
    const src = edge.source; const tgt = edge.target
    if (VISIBLE.has(src) && VISIBLE.has(tgt)) {
      const id = `${src}-${tgt}`
      if (!seen.has(id)) { seen.add(id)
        edges.push({ id, source: src, sourceHandle: 'right', target: tgt, targetHandle: 'left',
          type: 'smoothstep', markerEnd: { type: MarkerType.ArrowClosed, color: normalColor, width: 12, height: 12 },
          style: { stroke: normalColor, strokeWidth: 1.5 } } satisfies Edge)
      }
    }
    if (src === 'qa_review' && tgt === 'finalize_report') {
      const id = 'qa-end'
      if (!seen.has(id)) { seen.add(id)
        edges.push({ id, source: 'qa_review', sourceHandle: 'right', target: '__end__', targetHandle: 'left',
          type: 'smoothstep', markerEnd: { type: MarkerType.ArrowClosed, color: qaPassed ? THEME.pass.stroke : normalColor, width: 12, height: 12 },
          ...(qaPassed ? { label: '✓ PASS', labelStyle: { fontSize: 11, fontWeight: 700, fill: THEME.success.accent },
            labelBgStyle: { fill: THEME.success.bg }, labelBgPadding: [6, 4] as [number, number],
            labelBgBorderRadius: 5, style: { stroke: THEME.pass.stroke, strokeWidth: 2 } }
            : { style: { stroke: normalColor, strokeWidth: 1.5 } }) } satisfies Edge)
      }
    }
    if (src === 'handle_rework' && VISIBLE.has(tgt)) {
      const id = `rework-${tgt}`
      if (!seen.has(id)) { seen.add(id)
        edges.push({ id, source: 'qa_review', sourceHandle: 'bot-src', target: tgt, targetHandle: 'bot-tgt',
          type: 'rework', data: { active: reworkTargets.has(tgt) } } satisfies Edge)
      }
    }
  }
  return edges
}
