'use client'

import type { OperationMonetization as OperationMonetizationData } from '@/lib/types'

interface Props {
  data: OperationMonetizationData
}

const AARRR_STAGES = ['acquisition', 'activation', 'retention', 'referral', 'revenue'] as const

const MOTION_COLORS: Record<string, string> = {
  PLG: 'bg-green-100 text-green-800',
  sales_led: 'bg-purple-100 text-purple-800',
  marketing_led: 'bg-orange-100 text-orange-800',
  channel: 'bg-teal-100 text-teal-800',
  hybrid: 'bg-blue-100 text-blue-800',
}

function MotionBadge({ motion }: { motion: string }) {
  const cls = MOTION_COLORS[motion] ?? 'bg-gray-100 text-gray-700'
  return (
    <span className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${cls}`}>
      {motion.replace(/_/g, ' ')}
    </span>
  )
}

export default function OperationMonetization({ data }: Props) {
  if (
    !data ||
    (!data.gtm_profiles?.length &&
      !data.monetization_patterns?.length &&
      !Object.keys(data.free_paid_boundaries ?? {}).length &&
      !Object.keys(data.willingness_to_pay ?? {}).length &&
      !Object.keys(data.experience_risks ?? {}).length)
  ) {
    return null
  }

  const competitorNames = data.gtm_profiles?.map((p) => p.competitor_name) ?? []
  const hasAarrr = data.aarrr_notes && Object.keys(data.aarrr_notes).length > 0

  return (
    <div className="space-y-6">
      <h3 className="text-base font-semibold text-gray-900">Operations & Monetization</h3>

      {data.gtm_profiles?.length > 0 && (
        <section>
          <h4 className="mb-3 text-sm font-semibold text-gray-700">GTM Profiles</h4>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {data.gtm_profiles.map((profile) => (
              <div
                key={profile.competitor_name}
                className="rounded-lg border border-gray-200 bg-white p-4 space-y-2"
              >
                <div className="flex items-center justify-between">
                  <span className="text-sm font-semibold text-gray-900">{profile.competitor_name}</span>
                  {profile.motion && <MotionBadge motion={profile.motion} />}
                </div>
                {profile.pricing_strategy && (
                  <div className="text-xs text-gray-600">
                    <span className="font-medium">Pricing:</span>{' '}
                    <span className="capitalize">{profile.pricing_strategy.replace(/_/g, ' ')}</span>
                  </div>
                )}
                {profile.acquisition_channels?.length > 0 && (
                  <div className="text-xs text-gray-600">
                    <span className="font-medium">Acquisition:</span>{' '}
                    {profile.acquisition_channels.join(', ')}
                  </div>
                )}
                {profile.expansion_model && (
                  <div className="text-xs text-gray-600">
                    <span className="font-medium">Expansion:</span> {profile.expansion_model}
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {data.monetization_patterns?.length > 0 && (
        <section>
          <h4 className="mb-2 text-sm font-semibold text-gray-700">Monetization Patterns</h4>
          <ul className="space-y-1.5">
            {data.monetization_patterns.map((p, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-gray-700">
                <span className="mt-0.5 text-gray-400">•</span>
                <span>{p}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {(Object.keys(data.free_paid_boundaries ?? {}).length > 0 ||
        Object.keys(data.willingness_to_pay ?? {}).length > 0 ||
        Object.keys(data.experience_risks ?? {}).length > 0) && (
        <section>
          <h4 className="mb-2 text-sm font-semibold text-gray-700">Commercialization Details</h4>
          <div className="overflow-x-auto rounded-lg border border-gray-200">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-gray-200 bg-gray-50">
                  <th className="px-3 py-2 text-left font-medium text-gray-600">Competitor</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-600">Free/Paid Boundary</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-600">Why Users Pay</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-600">Experience Risk</th>
                </tr>
              </thead>
              <tbody>
                {Array.from(
                  new Set([
                    ...Object.keys(data.free_paid_boundaries ?? {}),
                    ...Object.keys(data.willingness_to_pay ?? {}),
                    ...Object.keys(data.experience_risks ?? {}),
                  ])
                ).map((name) => (
                  <tr key={name} className="border-b border-gray-100 last:border-0">
                    <td className="px-3 py-2 font-medium text-gray-700">{name}</td>
                    <td className="px-3 py-2 text-gray-600">{data.free_paid_boundaries?.[name] ?? '—'}</td>
                    <td className="px-3 py-2 text-gray-600">{data.willingness_to_pay?.[name] ?? '—'}</td>
                    <td className="px-3 py-2 text-gray-600">{data.experience_risks?.[name] ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {hasAarrr && competitorNames.length > 0 && (
        <section>
          <h4 className="mb-2 text-sm font-semibold text-gray-700">AARRR Funnel</h4>
          <div className="overflow-x-auto rounded-lg border border-gray-200">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-gray-200 bg-gray-50">
                  <th className="px-3 py-2 text-left font-medium text-gray-600 capitalize">Stage</th>
                  {competitorNames.map((name) => (
                    <th key={name} className="px-3 py-2 text-left font-medium text-gray-600">{name}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {AARRR_STAGES.map((stage) => {
                  const row = data.aarrr_notes?.[stage]
                  if (!row) return null
                  return (
                    <tr key={stage} className="border-b border-gray-100 last:border-0">
                      <td className="px-3 py-2 font-medium text-gray-700 capitalize">{stage}</td>
                      {competitorNames.map((name) => (
                        <td key={name} className="px-3 py-2 text-gray-600">
                          {row[name] ?? '—'}
                        </td>
                      ))}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  )
}
