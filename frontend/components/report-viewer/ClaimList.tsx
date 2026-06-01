'use client'

import { useSourcePanel } from '@/lib/store'
import type { Claim, SourceEvidence } from '@/lib/types'

interface ClaimListProps {
  claims: Claim[]
  sourceList?: SourceEvidence[]
  emptyMessage?: string
}

export function ClaimList({ claims, sourceList, emptyMessage }: ClaimListProps) {
  const openSource = useSourcePanel((s) => s.openSource)

  const sourceIndex = new Map(sourceList?.map((s, i) => [s.source_id, i + 1]) ?? [])

  if (!claims || claims.length === 0) {
    return (
      <p className="rounded-md border border-dashed border-gray-300 bg-white px-4 py-6 text-center text-sm text-gray-500">
        {emptyMessage ?? 'No data available.'}
      </p>
    )
  }

  return (
    <div className="space-y-3">
      {claims.map((c, i) => (
        <article
          key={c.claim_id ?? i}
          className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm"
        >
          <p className="text-sm leading-relaxed text-gray-800">{c.text || '—'}</p>
          {(c.evidence?.length ?? 0) > 0 ? (
            <div className="mt-3 flex flex-wrap items-center gap-1.5">
              <span className="text-[10px] tracking-wider text-gray-400 uppercase">Sources:</span>
              {c.evidence!.map((srcId) => {
                const num = sourceIndex.get(srcId)
                return (
                  <button
                    key={srcId}
                    type="button"
                    onClick={() => openSource(srcId)}
                    title={srcId}
                    className="rounded border border-blue-200 bg-blue-50 px-1.5 py-0.5 font-mono text-[11px] font-semibold text-blue-700 transition-colors hover:bg-blue-100"
                  >
                    {num !== undefined ? `[${num}]` : srcId}
                  </button>
                )
              })}
            </div>
          ) : (
            c.is_hypothesis && (
              <div className="mt-3">
                <span className="rounded border border-yellow-200 bg-yellow-50 px-2 py-0.5 text-xs font-medium text-yellow-800">
                  hypothesis · unverified
                </span>
              </div>
            )
          )}
        </article>
      ))}
    </div>
  )
}
