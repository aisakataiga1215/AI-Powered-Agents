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
const MAX_SELECTED_URLS = 8

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

const normalizeManualUrl = (value: string) => {
  const trimmed = value.trim()
  if (!trimmed) return null
  const withScheme = trimmed.includes('://') ? trimmed : `https://${trimmed}`
  try {
    const parsed = new URL(withScheme)
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') return null
    return parsed.toString()
  } catch {
    return null
  }
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
  const [manualUrl, setManualUrl] = useState('')
  const [manualError, setManualError] = useState<string | null>(null)

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
      const next = new Set(selected)
      for (const url of defaultUrls) {
        if (next.size >= MAX_SELECTED_URLS) break
        next.add(url)
      }
      setSelected(next)
      onSelectionChange(Array.from(next))
      setOpen(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Search failed')
    } finally {
      setLoading(false)
    }
  }, [competitorName, website, goals, industryType, onSelectionChange, selected])

  const toggle = useCallback(
    (url: string) => {
      const next = new Set(selected)
      if (next.has(url)) {
        next.delete(url)
      } else {
        if (next.size >= MAX_SELECTED_URLS) {
          setManualError(`最多选择 ${MAX_SELECTED_URLS} 个额外来源。`)
          return
        }
        next.add(url)
      }
      setSelected(next)
      setManualError(null)
      onSelectionChange(Array.from(next))
    },
    [onSelectionChange, selected]
  )

  const addManualUrl = useCallback(() => {
    const normalized = normalizeManualUrl(manualUrl)
    if (!normalized) {
      setManualError('请输入有效的 http/https 网址。')
      return
    }
    const next = new Set(selected)
    if (!next.has(normalized) && next.size >= MAX_SELECTED_URLS) {
      setManualError(`最多选择 ${MAX_SELECTED_URLS} 个额外来源。`)
      return
    }
    next.add(normalized)
    setSelected(next)
    setManualUrl('')
    setManualError(null)
    onSelectionChange(Array.from(next))
  }, [manualUrl, onSelectionChange, selected])

  const candidateUrls = new Set(candidates.map((candidate) => candidate.url))
  const manualSelectedUrls = Array.from(selected).filter((url) => !candidateUrls.has(url))

  return (
    <div className="mt-1">
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={handleSearch}
          disabled={loading || !competitorName || !website || searchAvailable === false}
          className="text-xs text-blue-600 hover:text-blue-800 disabled:text-gray-400 underline"
        >
          {loading ? '搜索中…' : '搜索候选来源'}
        </button>
        <div className="flex min-w-[280px] max-w-xl flex-1 items-center gap-2">
          <input
            type="text"
            value={manualUrl}
            onChange={(event) => setManualUrl(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault()
                addManualUrl()
              }
            }}
            placeholder="手动添加子页面，如 cursor.com/docs 或 x.com/xxx"
            className="h-7 min-w-0 flex-1 rounded border border-gray-200 px-2 text-xs"
          />
          <button
            type="button"
            onClick={addManualUrl}
            disabled={!manualUrl.trim()}
            className="h-7 rounded border border-gray-200 px-2 text-xs text-gray-700 hover:bg-gray-50 disabled:text-gray-300"
          >
            添加网址
          </button>
        </div>
      </div>

      {searchAvailable === false && (
        <div className="mt-1 flex items-center gap-2 text-xs text-gray-400">
          <span className="inline-block rounded border border-gray-200 bg-gray-50 px-2 py-0.5">
            Source search unavailable
          </span>
          <span>设置 ENABLE_LIVE_SEARCH=true 并配置 TAVILY_API_KEY 后可用；仍可手动添加网址。</span>
        </div>
      )}

      {error && (
        <p className="mt-1 text-xs text-red-500">{error}</p>
      )}
      {manualError && (
        <p className="mt-1 text-xs text-red-500">{manualError}</p>
      )}

      {manualSelectedUrls.length > 0 && (
        <div className="mt-2 rounded border border-blue-100 bg-blue-50 p-2">
          <p className="mb-1 text-xs font-medium text-blue-800">手动添加的额外来源</p>
          <ul className="space-y-1">
            {manualSelectedUrls.map((url) => (
              <li key={url} className="flex items-center gap-2 rounded bg-white px-2 py-1">
                <a
                  href={url}
                  target="_blank"
                  rel="noreferrer"
                  className="min-w-0 flex-1 truncate text-[11px] text-blue-700 underline"
                >
                  {url}
                </a>
                <button
                  type="button"
                  onClick={() => toggle(url)}
                  className="text-[11px] text-gray-500 hover:text-red-600"
                >
                  移除
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {open && candidates.length === 0 && !loading && (
        <p className="mt-1 text-xs text-gray-400">没有找到候选来源。</p>
      )}

      {open && candidates.length > 0 && (
        <div className="mt-2 rounded border border-gray-200 bg-gray-50 p-2">
          <p className="mb-1 text-xs text-gray-500">
            选中的 URL 会在分析前被采集。{' '}
            <span className="italic">来源类型是启发式判断，最终类型会在采集后确认。</span>
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
                          建议类型：{c.suggested_source_type.replace('_', ' ')}
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
