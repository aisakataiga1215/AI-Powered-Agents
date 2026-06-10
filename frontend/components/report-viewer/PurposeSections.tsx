'use client'

import { useSourcePanel } from '@/lib/store'
import type { SourceEvidence } from '@/lib/types'

interface Props {
  analysisPurpose?: string
  purposeSections: Record<string, unknown>
  sourceList?: SourceEvidence[]
}

function RiskBadge({ level }: { level: string }) {
  const cls =
    level === 'high' ? 'bg-rose-100 text-rose-700' :
    level === 'medium' ? 'bg-amber-100 text-amber-700' :
    'bg-green-100 text-green-700'
  return <span className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${cls}`}>{level}</span>
}

export default function PurposeSections({ analysisPurpose, purposeSections, sourceList = [] }: Props) {
  const openSource = useSourcePanel((s) => s.openSource)
  const sourceIndex = new Map(sourceList.map((s, i) => [s.source_id, i + 1]))
  if (!purposeSections || Object.keys(purposeSections).length === 0) return null

  if (analysisPurpose === 'choose_product_to_use') {
    const ranking = purposeSections.recommendation_ranking as Array<{ rank: number; competitor_name: string; summary: string }> | undefined
    const bestFor = purposeSections.best_for as Record<string, string> | undefined
    const avoid = purposeSections.who_should_avoid as Record<string, string> | undefined
    const matrix = purposeSections.decision_matrix as Array<Record<string, unknown>> | undefined

    return (
      <div className="space-y-6">
        {ranking && ranking.length > 0 && (
          <section>
            <h4 className="mb-2 text-sm font-semibold text-gray-900">Recommendation Ranking</h4>
            <ol className="space-y-2">
              {ranking.map((item) => (
                <li key={item.rank} className="flex items-start gap-3 rounded-lg border border-gray-200 bg-white p-3">
                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-blue-600 text-xs font-bold text-white">
                    {item.rank}
                  </span>
                  <div>
                    <div className="text-sm font-medium text-gray-900">{item.competitor_name}</div>
                    <div className="text-xs text-gray-600">{item.summary}</div>
                  </div>
                </li>
              ))}
            </ol>
          </section>
        )}

        {bestFor && Object.keys(bestFor).length > 0 && (
          <section>
            <h4 className="mb-2 text-sm font-semibold text-gray-900">Best For</h4>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {Object.entries(bestFor).map(([name, use]) => (
                <div key={name} className="rounded-lg border border-green-200 bg-green-50 p-3">
                  <div className="text-xs font-semibold text-green-900">{name}</div>
                  <div className="mt-0.5 text-xs text-green-800">{use}</div>
                </div>
              ))}
            </div>
          </section>
        )}

        {avoid && Object.keys(avoid).length > 0 && (
          <section>
            <h4 className="mb-2 text-sm font-semibold text-gray-900">Who Should Avoid</h4>
            <ul className="space-y-1.5">
              {Object.entries(avoid).map(([name, reason]) => (
                <li key={name} className="flex items-start gap-2 text-sm text-gray-700">
                  <span className="mt-0.5 text-rose-400">✕</span>
                  <span><span className="font-medium">{name}:</span> {reason}</span>
                </li>
              ))}
            </ul>
          </section>
        )}

        {matrix && matrix.length > 0 && (
          <section>
            <h4 className="mb-2 text-sm font-semibold text-gray-900">Decision Matrix</h4>
            <div className="overflow-x-auto rounded-lg border border-gray-200">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-gray-200 bg-gray-50">
                    <th className="px-3 py-2 text-left font-medium text-gray-600">Criterion</th>
                    {Object.keys(matrix[0] || {}).filter((k) => k !== 'criterion').map((k) => (
                      <th key={k} className="px-3 py-2 text-center font-medium text-gray-600">{k}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {matrix.map((row, i) => (
                    <tr key={i} className="border-b border-gray-100 last:border-0">
                      <td className="px-3 py-2 font-medium text-gray-700">{row.criterion as string}</td>
                      {Object.entries(row).filter(([k]) => k !== 'criterion').map(([k, v]) => {
                        const cell = v as { value?: string } | undefined
                        return (
                          <td key={k} className="px-3 py-2 text-center text-gray-600">
                            {typeof cell === 'object' && cell?.value ? cell.value : String(v ?? '—')}
                          </td>
                        )
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </div>
    )
  }

  if (analysisPurpose === 'build_similar_product') {
    const gaps = purposeSections.market_gaps as Array<{ gap_description: string; affected_user_segment?: string; evidence?: string[] }> | undefined
    const toLearn = purposeSections.features_to_learn_from as Array<{ competitor_name: string; feature: string; rationale: string }> | undefined
    const pitfalls = purposeSections.pitfalls_to_avoid as Array<{ competitor_name: string; pitfall: string; risk_level: string }> | undefined
    const diffOps = purposeSections.differentiation_opportunities as Array<{ opportunity: string; rationale: string }> | undefined
    const mvp = purposeSections.mvp_direction as string | undefined

    return (
      <div className="space-y-6">
        {gaps && gaps.length > 0 && (
          <section>
            <h4 className="mb-2 text-sm font-semibold text-gray-900">Market Gaps</h4>
            <ul className="space-y-2">
              {gaps.map((g, i) => (
                <li key={i} className="rounded-lg border border-blue-200 bg-blue-50 p-3">
                  <div className="text-sm text-blue-900">{g.gap_description}</div>
                  {g.affected_user_segment && (
                    <div className="mt-1 text-xs text-blue-700">Segment: {g.affected_user_segment}</div>
                  )}
                </li>
              ))}
            </ul>
          </section>
        )}

        {toLearn && toLearn.length > 0 && (
          <section>
            <h4 className="mb-2 text-sm font-semibold text-gray-900">Features to Learn From</h4>
            <div className="overflow-x-auto rounded-lg border border-gray-200">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-gray-200 bg-gray-50">
                    <th className="px-3 py-2 text-left font-medium text-gray-600">Competitor</th>
                    <th className="px-3 py-2 text-left font-medium text-gray-600">Feature</th>
                    <th className="px-3 py-2 text-left font-medium text-gray-600">Why it matters</th>
                  </tr>
                </thead>
                <tbody>
                  {toLearn.map((item, i) => (
                    <tr key={i} className="border-b border-gray-100 last:border-0">
                      <td className="px-3 py-2 font-medium text-gray-700">{item.competitor_name}</td>
                      <td className="px-3 py-2 text-gray-700">{item.feature}</td>
                      <td className="px-3 py-2 text-gray-600">{item.rationale}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {pitfalls && pitfalls.length > 0 && (
          <section>
            <h4 className="mb-2 text-sm font-semibold text-gray-900">Pitfalls to Avoid</h4>
            <ul className="space-y-2">
              {pitfalls.map((p, i) => (
                <li key={i} className="flex items-start gap-3 rounded-lg border border-gray-200 bg-white p-3">
                  <RiskBadge level={p.risk_level} />
                  <div>
                    <span className="text-xs font-medium text-gray-700">{p.competitor_name}: </span>
                    <span className="text-xs text-gray-600">{p.pitfall}</span>
                  </div>
                </li>
              ))}
            </ul>
          </section>
        )}

        {diffOps && diffOps.length > 0 && (
          <section>
            <h4 className="mb-2 text-sm font-semibold text-gray-900">Differentiation Opportunities</h4>
            <ul className="space-y-1.5">
              {diffOps.map((d, i) => (
                <li key={i} className="flex items-start gap-2 text-sm text-gray-700">
                  <span className="mt-0.5 text-blue-500">→</span>
                  <span><span className="font-medium">{d.opportunity}:</span> {d.rationale}</span>
                </li>
              ))}
            </ul>
          </section>
        )}

        {mvp && (
          <section>
            <h4 className="mb-2 text-sm font-semibold text-gray-900">Suggested MVP Direction</h4>
            <div className="rounded-lg border-l-4 border-blue-500 bg-blue-50 p-4 text-sm text-blue-900">
              {mvp}
            </div>
          </section>
        )}
      </div>
    )
  }

  if (analysisPurpose === 'market_research' || analysisPurpose === 'competitor_success_analysis') {
    return (
      <div className="space-y-4">
        {Object.entries(purposeSections).map(([key, value]) => (
          <section key={key}>
            <h4 className="mb-2 text-sm font-semibold text-gray-900 capitalize">{key.replace(/_/g, ' ')}</h4>
            <div className="rounded-lg border border-gray-200 bg-white p-3 text-sm text-gray-700">
              <PurposeValue value={value} sourceIndex={sourceIndex} openSource={openSource} />
            </div>
          </section>
        ))}
      </div>
    )
  }

  return null
}

function PurposeValue({
  value,
  sourceIndex,
  openSource,
}: {
  value: unknown
  sourceIndex: Map<string, number>
  openSource: (sourceId: string) => void
}) {
  if (Array.isArray(value)) {
    if (value.every((item) => typeof item === 'string' && sourceIndex.has(item))) {
      return (
        <span className="inline-flex flex-wrap gap-1 align-middle">
          {value.map((srcId) => (
            <button
              key={srcId}
              type="button"
              onClick={() => openSource(srcId)}
              title={srcId}
              className="rounded border border-blue-200 bg-blue-50 px-1.5 py-0.5 font-mono text-[11px] font-semibold text-blue-700 transition-colors hover:bg-blue-100"
            >
              [{sourceIndex.get(srcId)}]
            </button>
          ))}
        </span>
      )
    }

    return (
      <ul className="space-y-1.5">
        {value.map((item, index) => (
          <li key={index} className="text-sm text-gray-700">
            <PurposeValue value={item} sourceIndex={sourceIndex} openSource={openSource} />
          </li>
        ))}
      </ul>
    )
  }

  if (value && typeof value === 'object') {
    return (
      <div className="space-y-2">
        {Object.entries(value as Record<string, unknown>).map(([key, item]) => (
          <div key={key}>
            <span className="font-medium text-gray-900 capitalize">{key.replace(/_/g, ' ')}: </span>
            <PurposeValue value={item} sourceIndex={sourceIndex} openSource={openSource} />
          </div>
        ))}
      </div>
    )
  }

  return <span>{String(value ?? '—')}</span>
}
