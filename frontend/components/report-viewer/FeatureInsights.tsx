'use client'

import type { FeatureInsights as FeatureInsightsData } from '@/lib/types'

interface Props {
  data: FeatureInsightsData
}

export default function FeatureInsights({ data }: Props) {
  if (!data || (!data.table_stakes?.length && !data.differentiators?.length && !data.gaps?.length)) {
    return null
  }

  return (
    <div className="space-y-6">
      <h3 className="text-base font-semibold text-gray-900">Feature Insights</h3>

      {data.table_stakes?.length > 0 && (
        <section>
          <h4 className="mb-2 text-sm font-semibold text-gray-700">Table Stakes</h4>
          <p className="mb-2 text-xs text-gray-500">Features all or most competitors offer.</p>
          <div className="flex flex-wrap gap-2">
            {data.table_stakes.map((f, i) => (
              <span
                key={i}
                className="inline-block rounded-md bg-gray-100 px-2.5 py-1 text-xs font-medium text-gray-700"
              >
                {f}
              </span>
            ))}
          </div>
        </section>
      )}

      {data.differentiators?.length > 0 && (
        <section>
          <h4 className="mb-2 text-sm font-semibold text-gray-700">Differentiators</h4>
          <p className="mb-2 text-xs text-gray-500">Features only specific competitors offer.</p>
          <div className="overflow-x-auto rounded-lg border border-gray-200">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-gray-200 bg-gray-50">
                  <th className="px-3 py-2 text-left font-medium text-gray-600">Feature</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-600">Offered By</th>
                </tr>
              </thead>
              <tbody>
                {data.differentiators.map((d, i) => (
                  <tr key={i} className="border-b border-gray-100 last:border-0">
                    <td className="px-3 py-2 font-medium text-gray-700">{d.feature}</td>
                    <td className="px-3 py-2">
                      <div className="flex flex-wrap gap-1">
                        {(d.competitors ?? []).map((c: string) => (
                          <span
                            key={c}
                            className="inline-block rounded bg-blue-50 px-1.5 py-0.5 text-[10px] font-medium text-blue-700"
                          >
                            {c}
                          </span>
                        ))}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {data.gaps?.length > 0 && (
        <section>
          <h4 className="mb-2 text-sm font-semibold text-gray-700">Market Gaps</h4>
          <p className="mb-2 text-xs text-gray-500">Feature areas no competitor addresses — potential opportunities.</p>
          <div className="space-y-2">
            {data.gaps.map((g, i) => (
              <div key={i} className="rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm text-blue-900">
                {g}
              </div>
            ))}
          </div>
        </section>
      )}

      {data.cross_competitor_patterns?.length > 0 && (
        <section>
          <h4 className="mb-2 text-sm font-semibold text-gray-700">Cross-Competitor Patterns</h4>
          <ul className="space-y-1.5">
            {data.cross_competitor_patterns.map((p, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-gray-700">
                <span className="mt-0.5 text-gray-400">•</span>
                <span>{p}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
