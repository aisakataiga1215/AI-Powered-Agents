'use client'

import { useState, useCallback } from 'react'
import { api } from '@/lib/api'
import type { CandidateSource } from '@/lib/types'

interface CandidateSourcePanelProps {
  competitorName: string
  website: string
  goals: string[]
  industryType: string
  onSelectionChange: (urls: string[]) => void
}

const CONFIDENCE_BADGE: Record<string, string> = {
  high: 'bg-green-100 text-green-700',
  medium: 'bg-yellow-100 text-yellow-700',
  low: 'bg-gray-100 text-gray-500',
}

const DE_EMPHASIZED_TYPES = new Set(['blog', 'news', 'review'])
const DEFAULT_SELECTED_TYPES = new Set(['official_website', 'pricing_page', 'docs', 'features_page'])

const hostname = (url: string) => {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return ''
  }
}

const shouldSelectByDefault = (candidate: CandidateSource, website: string) => {
  if (candidate.selected_by_default) return true
  if (
    candidate.confidence === 'high' &&
    DEFAULT_SELECTED_TYPES.has(candidate.suggested_source_type ?? '')
  ) {
    return true
  }
  const candidateHost = hostname(candidate.url)
  const websiteHost = hostname(website)
  const isOfficial =
    candidateHost.length > 0 &&
    websiteHost.length > 0 &&
    (candidateHost === websiteHost || candidateHost.endsWith(`.${websiteHost}`))
  return (
    isOfficial &&
    candidate.confidence === 'high' &&
    DEFAULT_SELECTED_TYPES.has(candidate.suggested_source_type ?? '')
  )
}

export default function CandidateSourcePanel({
  competitorName,
  website,
  goals,
  industryType,
  onSelectionChange,
}: CandidateSourcePanelProps) {
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [candidates, setCandidates] = useState<CandidateSource[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [searchAvailable, setSearchAvailable] = useState<boolean | null>(null)
  const [error, setError] = useState<string | null>(null)

  const handleSearch = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await api.searchSources({
        competitor_name: competitorName,
        website,
        goals,
        industry_type: industryType,
      })
      const defaultUrls = result.candidates
        .filter((candidate) => shouldSelectByDefault(candidate, website))
        .map((candidate) => candidate.url)
      setSearchAvailable(result.search_available)
      setCandidates(result.candidates)
      setSelected(new Set(defaultUrls))
      onSelectionChange(defaultUrls)
      setOpen(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Search failed')
    } finally {
      setLoading(false)
    }
  }, [competitorName, website, goals, industryType, onSelectionChange])

  const toggle = useCallback(
    (url: string) => {
      const next = new Set(selected)
      if (next.has(url)) {
        next.delete(url)
      } else {
        next.add(url)
      }
      setSelected(next)
      onSelectionChange(Array.from(next))
    },
    [onSelectionChange, selected]
  )

  if (searchAvailable === false) {
    return (
      <div className="mt-1 flex items-center gap-2 text-xs text-gray-400">
        <span className="inline-block rounded border border-gray-200 bg-gray-50 px-2 py-0.5">
          Source search unavailable
        </span>
        <span>Set ENABLE_LIVE_SEARCH=true and TAVILY_API_KEY to enable</span>
      </div>
    )
  }

  return (
    <div className="mt-1">
      <button
        type="button"
        onClick={handleSearch}
        disabled={loading || !competitorName || !website}
        className="text-xs text-blue-600 hover:text-blue-800 disabled:text-gray-400 underline"
      >
        {loading ? 'Searching…' : 'Search candidate sources'}
      </button>

      {error && (
        <p className="mt-1 text-xs text-red-500">{error}</p>
      )}

      {open && candidates.length === 0 && !loading && (
        <p className="mt-1 text-xs text-gray-400">No candidates found.</p>
      )}

      {open && candidates.length > 0 && (
        <div className="mt-2 rounded border border-gray-200 bg-gray-50 p-2">
          <p className="mb-1 text-xs text-gray-500">
            Selected URLs will be crawled before analysis.{' '}
            <span className="italic">Suggested types are heuristic — final type is assigned after crawling.</span>
          </p>
          <ul className="space-y-1">
            {candidates.map((c) => {
              const isDeEmphasized = DE_EMPHASIZED_TYPES.has(c.suggested_source_type ?? '')
              return (
                <li
                  key={c.candidate_id}
                  className={`flex items-start gap-2 rounded px-2 py-1 hover:bg-white ${
                    isDeEmphasized ? 'opacity-60' : ''
                  }`}
                >
                  <input
                    type="checkbox"
                    className="mt-0.5 shrink-0"
                    checked={selected.has(c.url)}
                    onChange={() => toggle(c.url)}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-1">
                      <span
                        className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${
                          CONFIDENCE_BADGE[c.confidence ?? 'low']
                        }`}
                      >
                        {c.confidence ?? 'low'}
                      </span>
                      {c.suggested_source_type && (
                        <span className="text-[10px] text-gray-500">
                          Suggested type: {c.suggested_source_type.replace('_', ' ')}
                        </span>
                      )}
                    </div>
                    <p className={`text-xs font-medium ${isDeEmphasized ? 'italic text-gray-500' : 'text-gray-800'}`}>
                      {c.title || c.url}
                    </p>
                    <p className="truncate text-[10px] text-blue-600">{c.url}</p>
                    {c.snippet && (
                      <p className="mt-0.5 line-clamp-2 text-[10px] text-gray-500">{c.snippet}</p>
                    )}
                  </div>
                </li>
              )
            })}
          </ul>
        </div>
      )}
    </div>
  )
}
