'use client'

import { useState, useCallback } from 'react'
import { api } from '@/lib/api'
import type { CandidateCompetitor, CompetitorInput, CompetitorRole } from '@/lib/types'

interface CompetitorDiscoveryPanelProps {
  industry: string
  industryType: string
  onAdd: (competitors: CompetitorInput[]) => void
}

const RELEVANCE_BADGE: (score: number) => string = (score) => {
  if (score >= 70) return 'bg-green-100 text-green-700'
  if (score >= 40) return 'bg-yellow-100 text-yellow-700'
  return 'bg-gray-100 text-gray-500'
}

const CONFIDENCE_BADGE: Record<string, string> = {
  high: 'bg-green-100 text-green-700',
  medium: 'bg-yellow-100 text-yellow-700',
  low: 'bg-gray-100 text-gray-500',
}

export default function CompetitorDiscoveryPanel({
  industry,
  industryType,
  onAdd,
}: CompetitorDiscoveryPanelProps) {
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [candidates, setCandidates] = useState<CandidateCompetitor[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [searchAvailable, setSearchAvailable] = useState<boolean | null>(null)
  const [error, setError] = useState<string | null>(null)

  const handleDiscover = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await api.discoverCompetitors({
        industry,
        industry_type: industryType,
      })
      setSearchAvailable(result.search_available)
      setCandidates(result.candidates)
      setOpen(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Discovery failed')
    } finally {
      setLoading(false)
    }
  }, [industry, industryType])

  const toggleCandidate = useCallback((candidateId: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(candidateId)) {
        next.delete(candidateId)
      } else {
        next.add(candidateId)
      }
      return next
    })
  }, [])

  const handleAdd = useCallback(() => {
    const toAdd = candidates
      .filter((c) => selected.has(c.candidate_id))
      .map((c): CompetitorInput => ({
        name: c.name,
        url: c.website,
        role: 'direct_competitor' as CompetitorRole,
      }))
    if (toAdd.length > 0) {
      onAdd(toAdd)
      setSelected(new Set())
      setOpen(false)
    }
  }, [candidates, selected, onAdd])

  if (searchAvailable === false) {
    return (
      <div className="flex items-center gap-2 text-xs text-gray-400">
        <span className="inline-block rounded border border-gray-200 bg-gray-50 px-2 py-0.5">
          Discovery unavailable
        </span>
        <span>Set ENABLE_LIVE_SEARCH=true and TAVILY_API_KEY to enable</span>
      </div>
    )
  }

  return (
    <div>
      <button
        type="button"
        onClick={handleDiscover}
        disabled={loading || !industry.trim()}
        className="text-xs text-blue-600 hover:text-blue-800 disabled:text-gray-400 underline"
      >
        {loading ? 'Discovering…' : 'Discover competitors'}
      </button>

      {error && (
        <p className="mt-1 text-xs text-red-500">{error}</p>
      )}

      {open && candidates.length === 0 && !loading && (
        <p className="mt-1 text-xs text-gray-400">No candidates found.</p>
      )}

      {open && candidates.length > 0 && (
        <div className="mt-2 rounded border border-gray-200 bg-gray-50 p-2">
          <p className="mb-1 text-xs text-gray-500 italic">
            Suggested roles are heuristic — edit name and URL after adding.
          </p>
          <ul className="space-y-1">
            {candidates.map((c) => {
              const score = c.relevance_score ?? 50
              const sourceIsDifferent = c.source_url && c.source_url !== c.website
              return (
                <li
                  key={c.candidate_id}
                  className="flex items-start gap-2 rounded px-2 py-1.5 hover:bg-white"
                >
                  <input
                    type="checkbox"
                    className="mt-0.5 shrink-0"
                    checked={selected.has(c.candidate_id)}
                    onChange={() => toggleCandidate(c.candidate_id)}
                    aria-label={`Select ${c.name}`}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="text-xs font-semibold text-gray-800">{c.name}</span>
                      <span
                        className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${RELEVANCE_BADGE(score)}`}
                        title={c.relevance_reason}
                      >
                        {score}/100
                      </span>
                      {c.confidence && (
                        <span
                          className={`rounded px-1.5 py-0.5 text-[10px] ${CONFIDENCE_BADGE[c.confidence]}`}
                        >
                          {c.confidence}
                        </span>
                      )}
                      <span className="text-[10px] text-blue-500 italic">
                        Suggested role: Direct Competitor
                      </span>
                    </div>
                    <p className="truncate text-[10px] text-blue-600">{c.website}</p>
                    {sourceIsDifferent && (
                      <p className="truncate text-[10px] text-gray-400" title={c.source_url}>
                        via: {c.source_url}
                      </p>
                    )}
                    {c.description && (
                      <p className="mt-0.5 line-clamp-2 text-[10px] text-gray-500">{c.description}</p>
                    )}
                    {c.relevance_reason && (
                      <p className="mt-0.5 text-[10px] text-gray-400 italic">{c.relevance_reason}</p>
                    )}
                  </div>
                </li>
              )
            })}
          </ul>
          {selected.size > 0 && (
            <div className="mt-2 flex justify-end">
              <button
                type="button"
                onClick={handleAdd}
                className="rounded bg-blue-600 px-3 py-1 text-xs font-medium text-white hover:bg-blue-700"
              >
                Add {selected.size} selected
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
