'use client'

import type { CompetitorScore } from '@/lib/types'

interface Props {
  competitorScores?: Record<string, CompetitorScore>
  purposeSections?: Record<string, unknown>
}

function scoreTone(score: number): string {
  if (score >= 80) return 'bg-emerald-50 text-emerald-700'
  if (score >= 65) return 'bg-blue-50 text-blue-700'
  if (score >= 50) return 'bg-amber-50 text-amber-700'
  return 'bg-rose-50 text-rose-700'
}

function dimensionTone(score: number): string {
  if (score >= 4) return 'bg-emerald-100 text-emerald-800'
  if (score === 3) return 'bg-amber-100 text-amber-800'
  return 'bg-rose-100 text-rose-800'
}

export function ScoringMatrix({ competitorScores, purposeSections }: Props) {
  const scores = competitorScores ?? {}
  const names = Object.keys(scores).sort(
    (a, b) => (scores[b]?.overall_score ?? 0) - (scores[a]?.overall_score ?? 0)
  )
  if (names.length === 0) {
    return (
      <p className="rounded-md border border-dashed border-gray-300 bg-white px-4 py-6 text-center text-sm text-gray-500">
        暂无产品选择评分。
      </p>
    )
  }

  const dimensionNames = Array.from(
    new Set(names.flatMap((name) => scores[name]?.dimensions?.map((d) => d.dimension_name) ?? []))
  )
  const ranking = Array.isArray(purposeSections?.recommendation_ranking)
    ? purposeSections.recommendation_ranking as Array<Record<string, unknown>>
    : []
  const bestFor = isRecord(purposeSections?.best_for) ? purposeSections.best_for : {}
  const avoid = isRecord(purposeSections?.who_should_avoid) ? purposeSections.who_should_avoid : {}

  return (
    <div className="space-y-5">
      <section className="rounded-lg border border-gray-200 bg-white p-4">
        <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
          <div>
            <h2 className="text-base font-semibold text-gray-900">产品选择评分</h2>
            <p className="mt-1 text-xs text-gray-500">按场景适配、功能、价格、风险和证据充分度加权计算。</p>
          </div>
          <span className="text-xs text-gray-500">{names.length} 个产品</span>
        </div>
        <div className="overflow-x-auto rounded-md border border-gray-200">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 bg-gray-50">
                <th className="px-3 py-2 text-left font-medium text-gray-600">维度</th>
                <th className="px-3 py-2 text-right font-medium text-gray-600">权重</th>
                {names.map((name) => (
                  <th key={name} className="px-3 py-2 text-center font-medium text-gray-600">{name}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {dimensionNames.map((dimension) => {
                const first = names
                  .map((name) => scores[name]?.dimensions?.find((d) => d.dimension_name === dimension))
                  .find(Boolean)
                return (
                  <tr key={dimension} className="border-b border-gray-100 last:border-0">
                    <td className="px-3 py-2 font-medium text-gray-800">{dimension}</td>
                    <td className="px-3 py-2 text-right text-xs text-gray-500">
                      {first?.weight != null ? `${Math.round(first.weight * 100)}%` : '-'}
                    </td>
                    {names.map((name) => {
                      const dim = scores[name]?.dimensions?.find((d) => d.dimension_name === dimension)
                      return (
                        <td key={name} className="px-3 py-2 text-center">
                          {dim ? (
                            <div className="flex flex-col items-center gap-1">
                              <span className={`rounded px-1.5 py-0.5 text-xs font-semibold ${dimensionTone(dim.score)}`}>
                                {dim.score}/5
                              </span>
                              <span className="max-w-40 text-[11px] leading-snug text-gray-500">{dim.rationale}</span>
                            </div>
                          ) : '—'}
                        </td>
                      )
                    })}
                  </tr>
                )
              })}
              <tr className="border-t-2 border-gray-300 bg-gray-50">
                <td className="px-3 py-2 font-semibold text-gray-900">总分</td>
                <td />
                {names.map((name) => (
                  <td key={name} className="px-3 py-2 text-center">
                    <span className={`rounded px-2 py-1 text-xs font-bold ${scoreTone(scores[name]?.overall_score ?? 0)}`}>
                      {(scores[name]?.overall_score ?? 0).toFixed(1)}
                    </span>
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-xs text-gray-400">{scores[names[0]]?.scoring_note}</p>
      </section>

      {ranking.length > 0 && (
        <section className="rounded-lg border border-gray-200 bg-white p-4">
          <h3 className="text-sm font-semibold text-gray-900">推荐排序</h3>
          <ol className="mt-3 space-y-2">
            {ranking.map((item, index) => (
              <li key={`${item.competitor_name}-${index}`} className="flex gap-3 rounded-md border border-gray-100 p-3">
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-blue-600 text-xs font-bold text-white">
                  {String(item.rank ?? index + 1)}
                </span>
                <div>
                  <div className="text-sm font-semibold text-gray-900">{String(item.competitor_name ?? '')}</div>
                  <div className="text-xs text-gray-600">{String(item.summary ?? '')}</div>
                </div>
              </li>
            ))}
          </ol>
        </section>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        <GuidanceCard title="适合谁" data={bestFor} tone="green" />
        <GuidanceCard title="哪些人不建议选" data={avoid} tone="rose" />
      </div>
    </div>
  )
}

function GuidanceCard({ title, data, tone }: { title: string; data: Record<string, unknown>; tone: 'green' | 'rose' }) {
  const entries = Object.entries(data)
  if (entries.length === 0) return null
  const cls = tone === 'green'
    ? 'border-emerald-200 bg-emerald-50 text-emerald-900'
    : 'border-rose-200 bg-rose-50 text-rose-900'
  return (
    <section className={`rounded-lg border p-4 ${cls}`}>
      <h3 className="text-sm font-semibold">{title}</h3>
      <ul className="mt-3 space-y-2 text-sm">
        {entries.map(([name, value]) => (
          <li key={name}>
            <span className="font-medium">{name}: </span>
            <span>{String(value)}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}
