'use client'

/**
 * ClaimList — renders a stack of analytical claims with citation badges.
 *
 * Clicking a badge opens the source side panel via the global Zustand
 * store. Backend `Claim.text` (not `claim`) holds the natural-language
 * statement; `Claim.evidence` is a list of source_ids.
 */

import { useSourcePanel } from '@/lib/store'
import type { Claim } from '@/lib/types'

interface ClaimListProps {
  claims: Claim[]
  emptyMessage?: string
}

export function ClaimList({ claims, emptyMessage }: ClaimListProps) {
  const openSource = useSourcePanel((s) => s.openSource)
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
          <p className="text-sm leading-relaxed text-gray-800">
            {c.text || '—'}
          </p>
          {(c.evidence?.length ?? 0) > 0 ? (
            <div className="mt-3 flex flex-wrap items-center gap-1.5">
              <span className="text-[10px] uppercase tracking-wider text-gray-400">
                Evidence:
              </span>
              {c.evidence!.map((srcId) => (
                <button
                  key={srcId}
                  type="button"
                  onClick={() => openSource(srcId)}
                  className="rounded border border-blue-200 bg-blue-50 px-2 py-0.5 font-mono text-xs text-blue-700 transition-colors hover:bg-blue-100 hover:text-blue-800"
                >
                  {srcId}
                </button>
              ))}
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
