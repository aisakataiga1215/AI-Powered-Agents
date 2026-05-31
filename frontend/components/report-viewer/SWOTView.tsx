'use client'

/**
 * SWOTView — renders the four SWOT quadrants.
 *
 * Accepts either:
 *  - `report.swot_comparison` (loose Record) — first preference if it
 *    contains the canonical keys (strengths/weaknesses/etc.)
 *  - the SWOT block from the first competitor in `competitor_overview`
 */

import { useSourcePanel } from '@/lib/store'
import type { Claim, CompetitorKnowledge, SWOTAnalysis } from '@/lib/types'

interface SWOTViewProps {
  swotComparison: Record<string, unknown>
  competitorOverview: CompetitorKnowledge[]
}

type Quadrant = 'strengths' | 'weaknesses' | 'opportunities' | 'threats'

const QUADRANTS: { key: Quadrant; label: string; tone: string }[] = [
  {
    key: 'strengths',
    label: 'Strengths',
    tone: 'border-green-200 bg-green-50 text-green-900',
  },
  {
    key: 'weaknesses',
    label: 'Weaknesses',
    tone: 'border-red-200 bg-red-50 text-red-900',
  },
  {
    key: 'opportunities',
    label: 'Opportunities',
    tone: 'border-blue-200 bg-blue-50 text-blue-900',
  },
  {
    key: 'threats',
    label: 'Threats',
    tone: 'border-orange-200 bg-orange-50 text-orange-900',
  },
]

export function SWOTView({ swotComparison, competitorOverview }: SWOTViewProps) {
  const swots = collectSwots(swotComparison, competitorOverview)
  if (swots.length === 0) {
    return (
      <p className="rounded-md border border-dashed border-gray-300 bg-white px-4 py-6 text-center text-sm text-gray-500">
        No SWOT data available.
      </p>
    )
  }

  return (
    <div className="space-y-6">
      {swots.map(({ name, swot }) => (
        <div key={name}>
          <h3 className="mb-2 text-base font-semibold text-gray-900">{name}</h3>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {QUADRANTS.map((q) => (
              <Quadrant key={q.key} tone={q.tone} label={q.label} items={swot[q.key]} />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

function Quadrant({
  label,
  tone,
  items,
}: {
  label: string
  tone: string
  items: Claim[]
}) {
  const openSource = useSourcePanel((s) => s.openSource)
  return (
    <section
      className={`rounded-lg border p-3 ${tone}`}
      aria-label={label}
    >
      <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider">
        {label}
      </h4>
      {(!items || items.length === 0) && (
        <p className="text-sm opacity-70">No items.</p>
      )}
      <ul className="space-y-2">
        {(items ?? []).map((claim, i) => (
          <li key={claim.claim_id ?? i} className="text-sm leading-relaxed">
            <p>{claim.text}</p>
            {(claim.evidence?.length ?? 0) > 0 && (
              <div className="mt-1 flex flex-wrap gap-1">
                {claim.evidence!.map((srcId) => (
                  <button
                    key={srcId}
                    type="button"
                    onClick={() => openSource(srcId)}
                    className="rounded border border-white/40 bg-white/60 px-1.5 py-0.5 font-mono text-[10px] text-gray-800 hover:bg-white"
                  >
                    {srcId}
                  </button>
                ))}
              </div>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}

interface NamedSwot {
  name: string
  swot: SWOTAnalysis
}

function isClaim(v: unknown): v is Claim {
  return (
    typeof v === 'object' &&
    v !== null &&
    typeof (v as Claim).text === 'string'
  )
}

function toClaimArray(value: unknown): Claim[] {
  if (!Array.isArray(value)) return []
  const out: Claim[] = []
  for (const item of value) {
    if (typeof item === 'string') {
      out.push({ text: item, evidence: [] })
    } else if (isClaim(item)) {
      out.push({
        ...item,
        evidence: Array.isArray(item.evidence) ? item.evidence : [],
      })
    } else if (typeof item === 'object' && item !== null) {
      const obj = item as Record<string, unknown>
      const text =
        typeof obj.text === 'string'
          ? obj.text
          : typeof obj.claim === 'string'
            ? (obj.claim as string)
            : ''
      const evidence = Array.isArray(obj.evidence)
        ? (obj.evidence as string[])
        : []
      if (text) out.push({ text, evidence })
    }
  }
  return out
}

function pickSwot(raw: unknown): SWOTAnalysis | null {
  if (typeof raw !== 'object' || raw === null) return null
  const obj = raw as Record<string, unknown>
  const has = (k: string) => k in obj
  if (
    !has('strengths') &&
    !has('weaknesses') &&
    !has('opportunities') &&
    !has('threats')
  ) {
    return null
  }
  return {
    strengths: toClaimArray(obj.strengths),
    weaknesses: toClaimArray(obj.weaknesses),
    opportunities: toClaimArray(obj.opportunities),
    threats: toClaimArray(obj.threats),
  }
}

function collectSwots(
  swotComparison: Record<string, unknown>,
  competitorOverview: CompetitorKnowledge[]
): NamedSwot[] {
  const out: NamedSwot[] = []
  // 1) Prefer per-competitor entries in swot_comparison: { CompetitorName: { strengths: ... } }
  if (swotComparison && typeof swotComparison === 'object') {
    for (const [name, value] of Object.entries(swotComparison)) {
      const swot = pickSwot(value)
      if (swot) out.push({ name, swot })
    }
  }
  if (out.length > 0) return out
  // 2) Fall back to per-competitor SWOT in the overview block.
  for (const c of competitorOverview ?? []) {
    if (c.swot) {
      out.push({
        name: c.competitor_name || c.competitor_id || 'Competitor',
        swot: {
          strengths: toClaimArray(c.swot.strengths),
          weaknesses: toClaimArray(c.swot.weaknesses),
          opportunities: toClaimArray(c.swot.opportunities),
          threats: toClaimArray(c.swot.threats),
        },
      })
    }
  }
  return out
}
