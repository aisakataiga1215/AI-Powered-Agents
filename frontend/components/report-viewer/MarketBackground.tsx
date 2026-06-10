'use client'

import type { MarketBackground as MarketBackgroundData } from '@/lib/types'

interface Props {
  data: MarketBackgroundData
}

export default function MarketBackground({ data }: Props) {
  if (
    !data ||
    (!data.market_overview &&
      !data.trends?.length &&
      !data.key_drivers?.length &&
      !data.data_signals?.length)
  ) {
    return null
  }

  return (
    <div className="space-y-6">
      <h3 className="text-base font-semibold text-gray-900">Market & Background</h3>

      {data.market_overview && (
        <section>
          <h4 className="mb-1.5 text-sm font-semibold text-gray-700">Market Overview</h4>
          <p className="text-sm leading-relaxed text-gray-700">{data.market_overview}</p>
          {data.market_size_notes && (
            <span className="mt-2 inline-block rounded-full bg-blue-50 px-3 py-1 text-xs font-medium text-blue-700">
              {data.market_size_notes}
            </span>
          )}
        </section>
      )}

      {data.data_signals && data.data_signals.length > 0 && (
        <section>
          <h4 className="mb-2 text-sm font-semibold text-gray-700">Data Signals</h4>
          <div className="overflow-x-auto rounded-lg border border-gray-200">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-gray-200 bg-gray-50">
                  <th className="px-3 py-2 text-left font-medium text-gray-600">Metric</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-600">Competitor</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-600">Value</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-600">Confidence</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-600">Source</th>
                </tr>
              </thead>
              <tbody>
                {data.data_signals.map((signal, i) => (
                  <tr key={i} className="border-b border-gray-100 last:border-0">
                    <td className="px-3 py-2 font-medium text-gray-700">
                      {signal.metric_name || signal.signal_type || 'Metric'}
                    </td>
                    <td className="px-3 py-2 text-gray-600">{signal.competitor_name || 'Market'}</td>
                    <td className="px-3 py-2 text-gray-700">
                      <div>{signal.value || 'Unknown'}</div>
                      {signal.is_estimate && (
                        <div className="mt-1 text-[10px] font-medium uppercase text-amber-700">
                          Estimate
                        </div>
                      )}
                      {signal.notes && <div className="mt-1 text-[11px] text-gray-500">{signal.notes}</div>}
                    </td>
                    <td className="px-3 py-2">
                      <span className="rounded bg-gray-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-gray-700">
                        {signal.confidence || 'unknown'}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-gray-500">
                      {signal.source_ids?.length ? signal.source_ids.join(', ') : 'No source'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {data.trends && data.trends.length > 0 && (
        <section>
          <h4 className="mb-2 text-sm font-semibold text-gray-700">Key Trends</h4>
          <ul className="space-y-2">
            {data.trends.map((t, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-gray-700">
                <span className="mt-0.5 text-blue-400">→</span>
                <span>{t.trend}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {(data.key_drivers?.length > 0 || data.key_challenges?.length > 0) && (
        <section>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {data.key_drivers?.length > 0 && (
              <div>
                <h4 className="mb-2 text-sm font-semibold text-gray-700">Growth Drivers</h4>
                <ul className="space-y-1">
                  {data.key_drivers.map((d, i) => (
                    <li key={i} className="flex items-center gap-2">
                      <span className="inline-block rounded-full bg-green-100 px-2.5 py-0.5 text-xs font-medium text-green-800">
                        {d}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {data.key_challenges?.length > 0 && (
              <div>
                <h4 className="mb-2 text-sm font-semibold text-gray-700">Market Challenges</h4>
                <ul className="space-y-1">
                  {data.key_challenges.map((c, i) => (
                    <li key={i} className="flex items-center gap-2">
                      <span className="inline-block rounded-full bg-rose-100 px-2.5 py-0.5 text-xs font-medium text-rose-800">
                        {c}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </section>
      )}
    </div>
  )
}
