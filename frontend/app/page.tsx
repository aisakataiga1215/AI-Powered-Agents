'use client'

/**
 * Project creation page.
 *
 * Renders a single-column form with industry, dynamic competitor list,
 * and analysis goals. On submit it POSTs to /api/projects and forwards
 * the user to the execution page where they can start the workflow.
 */

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useState, useCallback, type FormEvent } from 'react'
import { useMutation } from '@tanstack/react-query'

import { api } from '@/lib/api'
import { cn } from '@/lib/cn'
import type { AnalysisPurpose, CompetitorInput, CompetitorRole, IndustryType, ProjectCreate } from '@/lib/types'
import CandidateSourcePanel from '@/components/search/CandidateSourcePanel'
import CompetitorDiscoveryPanel from '@/components/competitor/CompetitorDiscoveryPanel'

interface GoalOption {
  value: string
  label: string
  description: string
}

const GOAL_OPTIONS: GoalOption[] = [
  {
    value: 'feature_comparison',
    label: '功能对比',
    description: 'Map feature coverage across competitors.',
  },
  {
    value: 'pricing_analysis',
    label: '定价分析',
    description: 'Compare plan structure and price points.',
  },
  {
    value: 'user_personas',
    label: '用户画像',
    description: 'Identify each product’s primary audiences.',
  },
  {
    value: 'swot',
    label: 'SWOT 分析',
    description: 'Strengths, weaknesses, opportunities, threats.',
  },
]

interface IndustryTypeOption {
  value: IndustryType
  label: string
  description: string
}

const INDUSTRY_TYPE_OPTIONS: IndustryTypeOption[] = [
  { value: 'ai_saas', label: 'AI / SaaS', description: 'Software tools, APIs, developer platforms' },
  { value: 'ecommerce', label: 'E-commerce', description: 'Online marketplaces, retail, shopping' },
  { value: 'local_services', label: 'Local Services', description: 'Delivery, gig economy, on-demand' },
  { value: 'social', label: 'Social / Creator', description: 'Social platforms, creator tools, communities' },
  { value: 'general', label: 'General', description: 'Other industries' },
]

interface AnalysisPurposeOption {
  value: AnalysisPurpose
  label: string
  description: string
}

const ANALYSIS_PURPOSE_OPTIONS: AnalysisPurposeOption[] = [
  { value: 'general', label: 'General Overview', description: 'Standard competitive landscape' },
  { value: 'build_product', label: 'Build a Product', description: 'Find gaps, pitfalls, and MVP direction' },
  { value: 'choose_product', label: 'Choose a Product', description: 'Ranked recommendations and decision support' },
]

const COMPETITOR_ROLE_OPTIONS: { value: CompetitorRole; label: string }[] = [
  { value: 'direct_competitor', label: 'Direct Competitor' },
  { value: 'indirect_competitor', label: 'Indirect Competitor' },
  { value: 'inspiration_product', label: 'Inspiration Product' },
  { value: 'benchmark_leader', label: 'Benchmark Leader' },
]

const DEFAULT_COMPETITORS: CompetitorInput[] = [
  { name: 'Cursor', url: 'https://cursor.com', role: 'direct_competitor' },
  { name: 'Trae', url: 'https://www.trae.ai', role: 'direct_competitor' },
  { name: 'Windsurf', url: 'https://windsurf.ai', role: 'direct_competitor' },
]

export default function NewProjectPage() {
  const router = useRouter()
  const [industry, setIndustry] = useState('AI Coding Tools')
  const [industryType, setIndustryType] = useState<IndustryType>('ai_saas')
  const [analysisPurpose, setAnalysisPurpose] = useState<AnalysisPurpose>('general')
  const [customDimensions, setCustomDimensions] = useState<string[]>([])
  const [dimInput, setDimInput] = useState('')
  const [competitors, setCompetitors] = useState<CompetitorInput[]>(
    DEFAULT_COMPETITORS
  )
  const [goals, setGoals] = useState<string[]>(
    GOAL_OPTIONS.map((g) => g.value)
  )
  const [dataMode, setDataMode] = useState<'demo' | 'live_with_fallback'>('demo')
  const [extraUrlsByKey, setExtraUrlsByKey] = useState<Record<string, string[]>>({})
  const competitorKey = useCallback((c: CompetitorInput) => `${c.name}::${c.url}`, [])
  const createMutation = useMutation({
    mutationFn: (payload: ProjectCreate) => api.createProject(payload),
    onSuccess: (result) => {
      router.push(`/projects/${result.project_id}`)
    },
  })

  const handleCompetitorChange = (
    index: number,
    field: keyof CompetitorInput,
    value: string
  ) => {
    setCompetitors((prev) => {
      const updated = prev.map((row, i) => (i === index ? { ...row, [field]: value } : row))
      if (field === 'name' || field === 'url') {
        const oldKey = competitorKey(prev[index])
        const newKey = competitorKey(updated[index])
        if (oldKey !== newKey) {
          setExtraUrlsByKey((prevKeys) => {
            const next = { ...prevKeys }
            delete next[oldKey]
            return next
          })
        }
      }
      return updated
    })
  }

  const handleAddCompetitor = () => {
    setCompetitors((prev) => [...prev, { name: '', url: '', role: 'direct_competitor' }])
  }

  const handleAddDimension = () => {
    const t = dimInput.trim()
    if (t && !customDimensions.includes(t)) {
      setCustomDimensions((prev) => [...prev, t])
    }
    setDimInput('')
  }

  const handleRemoveDimension = (dim: string) => {
    setCustomDimensions((prev) => prev.filter((d) => d !== dim))
  }

  const handleRemoveCompetitor = (index: number) => {
    setExtraUrlsByKey((prev) => {
      const next = { ...prev }
      delete next[competitorKey(competitors[index])]
      return next
    })
    setCompetitors((prev) => prev.filter((_, i) => i !== index))
  }

  const handleAddFromDiscovery = useCallback((newComps: CompetitorInput[]) => {
    setCompetitors((prev) => {
      const normDomain = (url: string) => {
        try { return new URL(url).hostname.replace(/^www\./, '') }
        catch { return url.toLowerCase().trim() }
      }
      const existingDomains = new Set(prev.map((c) => normDomain(c.url)))
      const existingNames = new Set(prev.map((c) => c.name.toLowerCase().trim()))
      const unique = newComps.filter(
        (nc) =>
          !existingDomains.has(normDomain(nc.url)) &&
          !existingNames.has(nc.name.toLowerCase().trim())
      )
      return [...prev, ...unique]
    })
  }, [])

  const handleToggleGoal = (value: string) => {
    setGoals((prev) =>
      prev.includes(value) ? prev.filter((g) => g !== value) : [...prev, value]
    )
  }

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const cleanedCompetitors = competitors
      .map((c) => ({
        name: c.name.trim(),
        url: c.url.trim(),
        role: c.role ?? 'direct_competitor',
        extra_urls: extraUrlsByKey[competitorKey(c)] ?? [],
      }))
      .filter((c) => c.name.length > 0 && c.url.length > 0)
    const payload: ProjectCreate = {
      industry: industry.trim(),
      industry_type: industryType,
      analysis_purpose: analysisPurpose,
      custom_dimensions: customDimensions,
      competitors: cleanedCompetitors,
      goals,
      output_language: 'en',
      report_depth: 'standard',
      data_mode: dataMode,
    }
    createMutation.mutate(payload)
  }

  const submitDisabled =
    createMutation.isPending ||
    industry.trim().length === 0 ||
    competitors.every((c) => !c.name.trim() || !c.url.trim())

  return (
    <div className="mx-auto max-w-3xl">
      <header className="mb-8">
        <p className="text-xs font-medium uppercase tracking-wider text-blue-700">
          New Analysis
        </p>
        <h1 className="mt-2 text-3xl font-semibold text-gray-900">
          Create a competitive analysis project
        </h1>
        <p className="mt-2 max-w-xl text-sm text-gray-600">
          Define the industry, the competitors you want analyzed, and the
          analytical goals. The Collector, Analyst, Writer, and QA agents
          will run as a LangGraph workflow once you start the run.
        </p>
      </header>

      <form
        onSubmit={handleSubmit}
        className="space-y-6 rounded-xl border border-gray-200 bg-white p-6 shadow-sm"
      >
        <section className="space-y-2">
          <label
            htmlFor="industry"
            className="text-sm font-medium text-gray-900"
          >
            Industry / Topic
          </label>
          <input
            id="industry"
            value={industry}
            onChange={(e) => setIndustry(e.target.value)}
            placeholder="e.g. AI Coding Tools"
            className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 placeholder-gray-400 transition-shadow focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
            required
          />
          <p className="text-xs text-gray-500">
            The agents use this as topical framing across collection,
            analysis, and writing.
          </p>
        </section>

        <section className="space-y-3">
          <h2 className="text-sm font-medium text-gray-900">Industry type</h2>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {INDUSTRY_TYPE_OPTIONS.map((option) => (
              <label
                key={option.value}
                className={cn(
                  'flex cursor-pointer items-start gap-3 rounded-md border p-3 text-sm transition-colors',
                  industryType === option.value
                    ? 'border-blue-300 bg-blue-50'
                    : 'border-gray-200 bg-white hover:bg-gray-50'
                )}
              >
                <input
                  type="radio"
                  name="industry_type"
                  value={option.value}
                  checked={industryType === option.value}
                  onChange={() => setIndustryType(option.value)}
                  className="mt-0.5 h-4 w-4 border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                <div>
                  <div className="font-medium text-gray-900">{option.label}</div>
                  <div className="text-xs text-gray-500">{option.description}</div>
                </div>
              </label>
            ))}
          </div>
          <p className="text-xs text-gray-500">
            Selects industry-specific data collection paths for better coverage.
          </p>
        </section>

        <section className="space-y-3">
          <h2 className="text-sm font-medium text-gray-900">Analysis purpose</h2>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
            {ANALYSIS_PURPOSE_OPTIONS.map((option) => (
              <label
                key={option.value}
                className={cn(
                  'flex cursor-pointer items-start gap-3 rounded-md border p-3 text-sm transition-colors',
                  analysisPurpose === option.value
                    ? 'border-blue-300 bg-blue-50'
                    : 'border-gray-200 bg-white hover:bg-gray-50'
                )}
              >
                <input
                  type="radio"
                  name="analysis_purpose"
                  value={option.value}
                  checked={analysisPurpose === option.value}
                  onChange={() => setAnalysisPurpose(option.value)}
                  className="mt-0.5 h-4 w-4 border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                <div>
                  <div className="font-medium text-gray-900">{option.label}</div>
                  <div className="text-xs text-gray-500">{option.description}</div>
                </div>
              </label>
            ))}
          </div>
        </section>

        <section className="space-y-3">
          <h2 className="text-sm font-medium text-gray-900">Custom dimensions <span className="text-gray-400 font-normal">(optional)</span></h2>
          <div className="flex gap-2">
            <input
              id="custom-dimension-input"
              name="custom-dimension"
              aria-label="Add custom dimension"
              value={dimInput}
              onChange={(e) => setDimInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); handleAddDimension() } }}
              placeholder="e.g. API quality, data privacy"
              className="flex-1 rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
            />
            <button
              type="button"
              onClick={handleAddDimension}
              className="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
            >
              Add
            </button>
          </div>
          {customDimensions.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {customDimensions.map((dim) => (
                <span
                  key={dim}
                  className="inline-flex items-center gap-1 rounded-full bg-blue-50 px-2.5 py-0.5 text-xs font-medium text-blue-800"
                >
                  {dim}
                  <button
                    type="button"
                    onClick={() => handleRemoveDimension(dim)}
                    className="ml-0.5 text-blue-500 hover:text-blue-800"
                    aria-label={`Remove ${dim}`}
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
          )}
          <p className="text-xs text-gray-500">
            Extra analysis axes the agents will address explicitly.
          </p>
        </section>

        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-medium text-gray-900">Competitors</h2>
            <div className="flex items-center gap-3">
              <CompetitorDiscoveryPanel
                industry={industry}
                industryType={industryType}
                onAdd={handleAddFromDiscovery}
              />
              <button
                type="button"
                onClick={handleAddCompetitor}
                className="text-xs font-medium text-blue-700 hover:text-blue-800"
              >
                + Add competitor
              </button>
            </div>
          </div>
          <div className="space-y-2">
            {competitors.map((row, index) => (
              <div key={index} className="space-y-0">
                <div
                  className="flex flex-col gap-2 rounded-md border border-gray-200 bg-gray-50 p-3 sm:flex-row"
                >
                  <input
                    id={`competitor-name-${index}`}
                    name={`competitor-name-${index}`}
                    aria-label="Competitor name"
                    value={row.name}
                    onChange={(e) =>
                      handleCompetitorChange(index, 'name', e.target.value)
                    }
                    placeholder="Name"
                    className="w-full rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200 sm:max-w-[180px]"
                  />
                  <input
                    id={`competitor-url-${index}`}
                    name={`competitor-url-${index}`}
                    aria-label="Competitor website URL"
                    value={row.url}
                    onChange={(e) =>
                      handleCompetitorChange(index, 'url', e.target.value)
                    }
                    placeholder="https://example.com"
                    className="w-full rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
                  />
                  <select
                    id={`competitor-role-${index}`}
                    name={`competitor-role-${index}`}
                    aria-label="Competitor role"
                    value={row.role ?? 'direct_competitor'}
                    onChange={(e) => handleCompetitorChange(index, 'role', e.target.value)}
                    className="rounded-md border border-gray-300 bg-white px-2 py-1.5 text-xs text-gray-700 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
                  >
                    {COMPETITOR_ROLE_OPTIONS.map((r) => (
                      <option key={r.value} value={r.value}>{r.label}</option>
                    ))}
                  </select>
                  <button
                    type="button"
                    onClick={() => handleRemoveCompetitor(index)}
                    disabled={competitors.length === 1}
                    className="rounded-md px-2 py-1 text-xs text-gray-500 transition-colors hover:bg-gray-200 hover:text-gray-900 disabled:cursor-not-allowed disabled:opacity-50"
                    aria-label={`Remove ${row.name || 'competitor'}`}
                  >
                    Remove
                  </button>
                </div>
                <CandidateSourcePanel
                  competitorName={row.name}
                  website={row.url}
                  goals={goals}
                  industryType={industryType}
                  onSelectionChange={(urls) =>
                    setExtraUrlsByKey((prev) => ({ ...prev, [competitorKey(row)]: urls }))
                  }
                />
              </div>
            ))}
          </div>
        </section>

        <section className="space-y-3">
          <h2 className="text-sm font-medium text-gray-900">Analysis goals</h2>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {GOAL_OPTIONS.map((goal) => {
              const checked = goals.includes(goal.value)
              return (
                <label
                  key={goal.value}
                  className={cn(
                    'flex cursor-pointer items-start gap-3 rounded-md border p-3 text-sm transition-colors',
                    checked
                      ? 'border-blue-300 bg-blue-50'
                      : 'border-gray-200 bg-white hover:bg-gray-50'
                  )}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => handleToggleGoal(goal.value)}
                    className="mt-0.5 h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                  />
                  <div>
                    <div className="font-medium text-gray-900">{goal.label}</div>
                    <div className="text-xs text-gray-500">{goal.description}</div>
                  </div>
                </label>
              )
            })}
          </div>
        </section>

        <section className="space-y-3">
          <h2 className="text-sm font-medium text-gray-900">Data mode</h2>
          <div className="space-y-2">
            {([
              {
                value: 'demo' as const,
                label: 'Demo fixtures',
                description: 'Stable, offline — uses pre-canned data. Recommended for development.',
              },
              {
                value: 'live_with_fallback' as const,
                label: 'Live crawl with fallback',
                description: 'Crawls competitor websites. Slower, requires internet. Falls back to demo when coverage is insufficient.',
              },
            ] as const).map((option) => (
              <label
                key={option.value}
                className={cn(
                  'flex cursor-pointer items-start gap-3 rounded-md border p-3 text-sm transition-colors',
                  dataMode === option.value
                    ? 'border-blue-300 bg-blue-50'
                    : 'border-gray-200 bg-white hover:bg-gray-50'
                )}
              >
                <input
                  type="radio"
                  name="data_mode"
                  value={option.value}
                  checked={dataMode === option.value}
                  onChange={() => setDataMode(option.value)}
                  className="mt-0.5 h-4 w-4 border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                <div>
                  <div className="font-medium text-gray-900">{option.label}</div>
                  <div className="text-xs text-gray-500">{option.description}</div>
                </div>
              </label>
            ))}
          </div>
        </section>

        {createMutation.isError && (
          <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {createMutation.error instanceof Error
              ? createMutation.error.message
              : 'Failed to create project.'}
          </div>
        )}

        <div className="flex items-center justify-between border-t border-gray-100 pt-4">
          <Link
            href="/projects"
            className="text-sm text-gray-600 hover:text-gray-900"
          >
            View existing projects &rarr;
          </Link>
          <button
            type="submit"
            disabled={submitDisabled}
            className={cn(
              'inline-flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium text-white transition-colors',
              submitDisabled
                ? 'cursor-not-allowed bg-gray-300'
                : 'bg-blue-600 hover:bg-blue-700'
            )}
          >
            {createMutation.isPending && (
              <span
                className="h-3 w-3 animate-spin rounded-full border-2 border-white border-t-transparent"
                aria-hidden
              />
            )}
            {createMutation.isPending ? 'Creating...' : 'Create project'}
          </button>
        </div>
      </form>
    </div>
  )
}
