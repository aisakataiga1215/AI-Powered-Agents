'use client'

import type { MarketBackground as MarketBackgroundData } from '@/lib/types'

interface Props {
  data: MarketBackgroundData
}

export default function MarketBackground({ data }: Props) {
  if (!data || (!data.market_overview && !data.trends?.length && !data.key_drivers?.length)) {
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
