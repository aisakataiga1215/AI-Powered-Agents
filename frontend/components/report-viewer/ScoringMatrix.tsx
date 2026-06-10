'use client'

import type { CompetitorScore, OpportunityScore } from '@/lib/types'
import { cn } from '@/lib/cn'

interface Props {
  analysisPurpose?: string
  competitorScores?: Record<string, CompetitorScore>
  opportunityScore?: OpportunityScore | null
}

function scoreColor(score: number): string {
  if (score <= 2) return 'bg-rose-100 text-rose-800'
  if (score === 3) return 'bg-amber-100 text-amber-800'
  return 'bg-green-100 text-green-800'
}

function confidenceBadge(conf: string): string {
  if (conf === 'high') return 'bg-green-50 text-green-700'
  if (conf === 'medium') return 'bg-amber-50 text-amber-700'
  if (conf === 'low') return 'bg-rose-50 text-rose-700'
  return 'bg-gray-50 text-gray-500'
}

export default function ScoringMatrix({ analysisPurpose, competitorScores, opportunityScore }: Props) {
  if (analysisPurpose === 'market_research' || analysisPurpose === 'competitor_success_analysis') return null

  if (analysisPurpose === 'choose_product_to_use') {
    if (!competitorScores || Object.keys(competitorScores).length === 0) return null
    const names = Object.keys(competitorScores)
    const firstScore = competitorScores[names[0]]
    const dims = Array.from(
      new Set(names.flatMap((name) => competitorScores[name]?.dimensions?.map((d) => d.dimension_name) ?? []))
    )

    return (
      <div className="space-y-3">
        <h3 className="text-base font-semibold text-gray-900">Competitor Scoring Matrix</h3>
        <div className="overflow-x-auto rounded-lg border border-gray-200">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 bg-gray-50">
                <th className="px-4 py-2.5 text-left font-medium text-gray-600">Dimension</th>
                {names.map((name) => (
                  <th key={name} className="px-4 py-2.5 text-center font-medium text-gray-600">{name}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {dims.map((dim) => (
                <tr key={dim} className="border-b border-gray-100 last:border-0">
                  <td className="px-4 py-2.5 text-gray-700 capitalize">{dim.replace(/_/g, ' ')}</td>
                  {names.map((name) => {
                    const d = competitorScores[name]?.dimensions.find((x) => x.dimension_name === dim)
                    return (
                      <td key={name} className="px-4 py-2.5 text-center">
                        {d ? (
                          <div className="flex flex-col items-center gap-1">
                            <span className={cn('inline-block rounded px-1.5 py-0.5 text-xs font-semibold', scoreColor(d.score))}>
                              {d.score}/5
                            </span>
                            <span className={cn('rounded px-1 text-[10px]', confidenceBadge(d.source_confidence))}>
                              {d.source_confidence}
                            </span>
                          </div>
                        ) : '—'}
                      </td>
                    )
                  })}
                </tr>
              ))}
              <tr className="border-t-2 border-gray-300 bg-gray-50 font-semibold">
                <td className="px-4 py-2.5 text-gray-900">Overall</td>
                {names.map((name) => (
                  <td key={name} className="px-4 py-2.5 text-center">
                    <span className="text-blue-700">{competitorScores[name]?.overall_score?.toFixed(0) ?? '—'}</span>
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
        {firstScore?.scoring_note && (
          <p className="text-xs text-gray-400 italic">{firstScore.scoring_note}</p>
        )}
      </div>
    )
  }

  if (analysisPurpose === 'build_similar_product') {
    if (!opportunityScore) return null
    return (
      <div className="space-y-3">
        <h3 className="text-base font-semibold text-gray-900">Market Opportunity Score</h3>
        <div className="overflow-x-auto rounded-lg border border-gray-200">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 bg-gray-50">
                <th className="px-4 py-2.5 text-left font-medium text-gray-600">Dimension</th>
                <th className="px-4 py-2.5 text-center font-medium text-gray-600">Score</th>
                <th className="px-4 py-2.5 text-left font-medium text-gray-600">Rationale</th>
              </tr>
            </thead>
            <tbody>
              {opportunityScore.dimensions.map((d) => (
                <tr key={d.dimension_name} className="border-b border-gray-100 last:border-0">
                  <td className="px-4 py-2.5 text-gray-700 capitalize">{d.dimension_name.replace(/_/g, ' ')}</td>
                  <td className="px-4 py-2.5 text-center">
                    <div className="flex flex-col items-center gap-1">
                      <span className={cn('inline-block rounded px-1.5 py-0.5 text-xs font-semibold', scoreColor(d.score))}>
                        {d.score}/5
                      </span>
                      <span className={cn('rounded px-1 text-[10px]', confidenceBadge(d.source_confidence))}>
                        {d.source_confidence}
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-2.5 text-gray-600 text-xs">{d.rationale}</td>
                </tr>
              ))}
              <tr className="border-t-2 border-gray-300 bg-gray-50 font-semibold">
                <td className="px-4 py-2.5 text-gray-900">Overall</td>
                <td className="px-4 py-2.5 text-center text-blue-700">{opportunityScore.overall_score?.toFixed(0)}</td>
                <td className="px-4 py-2.5" />
              </tr>
            </tbody>
          </table>
        </div>
        {opportunityScore.scoring_note && (
          <p className="text-xs text-gray-400 italic">{opportunityScore.scoring_note}</p>
        )}
      </div>
    )
  }

  return null
}
