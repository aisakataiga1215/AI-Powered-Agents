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
import { useMutation, useQuery } from '@tanstack/react-query'

import { api } from '@/lib/api'
import { cn } from '@/lib/cn'
import type {
  AnalysisPurpose,
  CompetitorInput,
  CompetitorRole,
  IndustryType,
  ProjectCreate,
  ResearchInput,
  ResearchInputKind,
} from '@/lib/types'
import CandidateSourcePanel from '@/components/search/CandidateSourcePanel'
import CompetitorDiscoveryPanel from '@/components/competitor/CompetitorDiscoveryPanel'

type CreationMode = 'discover' | 'manual'

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
  { value: 'ai_search', label: 'AI Search / Q&A', description: 'Answer engines, chat assistants, research tools' },
  { value: 'design_tools', label: 'Design Tools', description: 'Visual design, whiteboards, creative suites' },
  { value: 'ecommerce', label: 'E-commerce', description: 'Online marketplaces, retail, shopping' },
  { value: 'local_services', label: 'Local Services', description: 'Delivery, gig economy, on-demand' },
  { value: 'open_source', label: 'Open Source / Nonprofit', description: 'Foundations, public-good products, communities' },
  { value: 'social', label: 'Social / Creator', description: 'Social platforms, creator tools, communities' },
  { value: 'general', label: 'General', description: 'Other industries' },
]

interface AnalysisPurposeOption {
  value: AnalysisPurpose
  label: string
  description: string
}

const ANALYSIS_PURPOSE_OPTIONS: AnalysisPurposeOption[] = [
  { value: 'build_similar_product', label: '我想做类似产品', description: '发现市场空白、差异化机会和 MVP 方向' },
  { value: 'choose_product_to_use', label: '我想选择产品使用', description: '按适配度、价格、风险和证据排序' },
  { value: 'market_research', label: '我想了解行业', description: '梳理市场格局、用户分层和增长驱动' },
  { value: 'competitor_success_analysis', label: '我想分析某个竞品', description: '拆解定位、增长路径、变现和护城河' },
]

const CUSTOM_DIMENSION_SUGGESTIONS = ['价格', '隐私', '本地部署', 'API', '企业版', '安全合规']
const MAX_CUSTOM_DIMENSIONS = 8

const COMPETITOR_ROLE_OPTIONS: { value: CompetitorRole; label: string }[] = [
  { value: 'direct_competitor', label: 'Direct Competitor' },
  { value: 'indirect_competitor', label: 'Indirect Competitor' },
  { value: 'inspiration_product', label: 'Inspiration Product' },
  { value: 'benchmark_leader', label: 'Benchmark Leader' },
]

const RESEARCH_KIND_OPTIONS: { value: ResearchInputKind; label: string }[] = [
  { value: 'survey', label: 'Survey results' },
  { value: 'interview', label: 'Interview notes' },
  { value: 'questionnaire', label: 'Questionnaire design' },
  { value: 'desk_research', label: 'Desk research' },
  { value: 'notes', label: 'Notes' },
]

const DEFAULT_COMPETITORS: CompetitorInput[] = [
  { name: 'Cursor', url: 'https://cursor.com', role: 'direct_competitor' },
  { name: 'Trae', url: 'https://www.trae.ai', role: 'direct_competitor' },
  { name: 'Windsurf', url: 'https://windsurf.ai', role: 'direct_competitor' },
]

export default function NewProjectPage() {
  const router = useRouter()
  const [industry, setIndustry] = useState('AI Coding Tools')
  const [creationMode, setCreationMode] = useState<CreationMode>('discover')
  const [naturalLanguageQuery, setNaturalLanguageQuery] = useState('帮我分析一下 AI coding 的竞品')
  const [industryType, setIndustryType] = useState<IndustryType>('ai_saas')
  const [analysisPurpose, setAnalysisPurpose] = useState<AnalysisPurpose>('build_similar_product')
  const [customDimensions, setCustomDimensions] = useState<string[]>([])
  const [dimInput, setDimInput] = useState('')
  const [competitors, setCompetitors] = useState<CompetitorInput[]>(
    DEFAULT_COMPETITORS
  )
  const [goals, setGoals] = useState<string[]>(
    GOAL_OPTIONS.map((g) => g.value)
  )
  const [researchInputs, setResearchInputs] = useState<ResearchInput[]>([])
  const [researchDraft, setResearchDraft] = useState<ResearchInput>({
    title: 'User research notes',
    content: '',
    source_kind: 'interview',
    competitor_name: '',
  })
  const [selectedDataMode, setSelectedDataMode] = useState<'demo' | 'live_with_fallback' | null>(null)
  const [extraUrlsByKey, setExtraUrlsByKey] = useState<Record<string, string[]>>({})
  const competitorKey = useCallback((c: CompetitorInput) => `${c.name}::${c.url}`, [])
  const searchStatusQuery = useQuery({
    queryKey: ['search-status'],
    queryFn: () => api.getSearchStatus(),
    retry: false,
  })
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
            const urls = next[oldKey]
            delete next[oldKey]
            if (urls) {
              next[newKey] = urls
            }
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

  const addDimension = (value: string) => {
    const normalized = value.trim()
    if (!normalized) return
    setCustomDimensions((prev) => {
      if (prev.length >= MAX_CUSTOM_DIMENSIONS) return prev
      if (prev.some((dim) => dim.toLowerCase() === normalized.toLowerCase())) return prev
      return [...prev, normalized]
    })
  }

  const handleAddDimension = () => {
    addDimension(dimInput)
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

  const handleAddResearchInput = () => {
    const content = researchDraft.content.trim()
    if (!content) return
    setResearchInputs((prev) => [
      ...prev,
      {
        title: researchDraft.title.trim() || 'User research notes',
        content,
        source_kind: researchDraft.source_kind,
        competitor_name: researchDraft.competitor_name?.trim() || '',
      },
    ])
    setResearchDraft((prev) => ({ ...prev, content: '', competitor_name: '' }))
  }

  const handleRemoveResearchInput = (index: number) => {
    setResearchInputs((prev) => prev.filter((_, i) => i !== index))
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
      research_inputs: researchInputs,
    }
    createMutation.mutate(payload)
  }

  const dataMode = selectedDataMode ?? (searchStatusQuery.data?.search_available ? 'live_with_fallback' : 'demo')
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
        <section className="space-y-3">
          <h2 className="text-sm font-medium text-gray-900">Project entry mode</h2>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {([
              {
                value: 'discover' as const,
                label: 'Mode A · Describe and discover',
                description: 'Start from a natural-language topic, review candidates, then add selected competitors.',
              },
              {
                value: 'manual' as const,
                label: 'Mode B · Manual competitor list',
                description: 'Enter known competitor names and URLs directly, then select official source pages.',
              },
            ]).map((option) => (
              <label
                key={option.value}
                className={cn(
                  'flex cursor-pointer items-start gap-3 rounded-md border p-3 text-sm transition-colors',
                  creationMode === option.value
                    ? 'border-blue-300 bg-blue-50'
                    : 'border-gray-200 bg-white hover:bg-gray-50'
                )}
              >
                <input
                  type="radio"
                  name="creation_mode"
                  value={option.value}
                  checked={creationMode === option.value}
                  onChange={() => setCreationMode(option.value)}
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

        {creationMode === 'discover' && (
          <section className="space-y-2 rounded-md border border-blue-100 bg-blue-50/60 p-3">
            <label htmlFor="natural-language-query" className="text-sm font-medium text-gray-900">
              Natural-language discovery prompt
            </label>
            <textarea
              id="natural-language-query"
              value={naturalLanguageQuery}
              onChange={(e) => {
                const value = e.target.value
                setNaturalLanguageQuery(value)
                setIndustry(value)
              }}
              placeholder="e.g. 帮我分析一下 AI coding 的竞品"
              rows={3}
              className="w-full rounded-md border border-blue-200 bg-white px-3 py-2 text-sm text-gray-900 placeholder-gray-400 transition-shadow focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
            />
            <CompetitorDiscoveryPanel
              industry={naturalLanguageQuery}
              industryType={industryType}
              onAdd={handleAddFromDiscovery}
              label="Find candidates"
              emptyLabel="No candidates found for this prompt. You can switch to manual mode."
            />
            <p className="text-xs text-gray-600">
              Discovery only proposes competitors. You still choose which candidates enter the project and can edit rows before running.
            </p>
          </section>
        )}

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
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
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
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-medium text-gray-900">Competitors</h2>
            <div className="flex items-center gap-3">
              {creationMode === 'manual' && (
                <CompetitorDiscoveryPanel
                  industry={industry}
                  industryType={industryType}
                  onAdd={handleAddFromDiscovery}
                />
              )}
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
                  key={competitorKey(row)}
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
          <h2 className="text-sm font-medium text-gray-900">Research inputs <span className="font-normal text-gray-400">(optional)</span></h2>
          <div className="rounded-md border border-gray-200 bg-gray-50 p-3">
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-[1fr_170px]">
              <input
                id="research-title"
                name="research-title"
                aria-label="Research input title"
                value={researchDraft.title}
                onChange={(e) => setResearchDraft((prev) => ({ ...prev, title: e.target.value }))}
                placeholder="e.g. PM workshop interview notes"
                className="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
              />
              <select
                id="research-kind"
                name="research-kind"
                aria-label="Research input type"
                value={researchDraft.source_kind}
                onChange={(e) => setResearchDraft((prev) => ({ ...prev, source_kind: e.target.value as ResearchInputKind }))}
                className="rounded-md border border-gray-300 bg-white px-2 py-1.5 text-xs text-gray-700 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
              >
                {RESEARCH_KIND_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </div>
            <select
              id="research-competitor"
              name="research-competitor"
              aria-label="Bind research input to competitor"
              value={researchDraft.competitor_name ?? ''}
              onChange={(e) => setResearchDraft((prev) => ({ ...prev, competitor_name: e.target.value }))}
              className="mt-2 w-full rounded-md border border-gray-300 bg-white px-2 py-1.5 text-xs text-gray-700 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
            >
              <option value="">Apply to all competitors</option>
              {competitors
                .filter((c) => c.name.trim())
                .map((c) => (
                  <option key={competitorKey(c)} value={c.name.trim()}>{c.name.trim()}</option>
                ))}
            </select>
            <textarea
              id="research-content"
              name="research-content"
              aria-label="Research input content"
              value={researchDraft.content}
              onChange={(e) => setResearchDraft((prev) => ({ ...prev, content: e.target.value }))}
              placeholder="Paste survey findings, questionnaire design, interview notes, or manual research observations."
              rows={4}
              className="mt-2 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
            />
            <div className="mt-2 flex justify-end">
              <button
                type="button"
                onClick={handleAddResearchInput}
                disabled={!researchDraft.content.trim()}
                className="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Add research input
              </button>
            </div>
          </div>
          {researchInputs.length > 0 && (
            <div className="space-y-2">
              {researchInputs.map((item, index) => (
                <div
                  key={`${item.title}-${index}`}
                  className="flex items-start justify-between gap-3 rounded-md border border-gray-200 bg-white p-3"
                >
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium text-gray-900">{item.title}</div>
                    <div className="mt-0.5 text-xs text-gray-500">
                      {item.source_kind.replace('_', ' ')}
                      {item.competitor_name ? ` · ${item.competitor_name}` : ' · all competitors'}
                    </div>
                    <div className="mt-1 line-clamp-2 text-xs text-gray-600">{item.content}</div>
                  </div>
                  <button
                    type="button"
                    onClick={() => handleRemoveResearchInput(index)}
                    className="shrink-0 rounded-md px-2 py-1 text-xs text-gray-500 hover:bg-gray-100 hover:text-gray-900"
                  >
                    Remove
                  </button>
                </div>
              ))}
            </div>
          )}
          <p className="text-xs text-gray-500">
            Added material is stored as manual evidence and appears in source traceability.
          </p>
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
          <h2 className="text-sm font-medium text-gray-900">Custom dimensions <span className="text-gray-400 font-normal">(optional)</span></h2>
          <div className="flex flex-wrap gap-1.5">
            {CUSTOM_DIMENSION_SUGGESTIONS.map((suggestion) => {
              const selected = customDimensions.some((dim) => dim.toLowerCase() === suggestion.toLowerCase())
              return (
                <button
                  key={suggestion}
                  type="button"
                  onClick={() => addDimension(suggestion)}
                  disabled={selected || customDimensions.length >= MAX_CUSTOM_DIMENSIONS}
                  className={cn(
                    'rounded-full border px-2.5 py-1 text-xs font-medium transition-colors',
                    selected
                      ? 'border-blue-200 bg-blue-50 text-blue-700'
                      : 'border-gray-200 bg-white text-gray-600 hover:border-blue-200 hover:bg-blue-50 hover:text-blue-700',
                    customDimensions.length >= MAX_CUSTOM_DIMENSIONS && !selected ? 'cursor-not-allowed opacity-50' : ''
                  )}
                >
                  {suggestion}
                </button>
              )
            })}
          </div>
          <div className="flex gap-2">
            <input
              id="custom-dimension-input"
              name="custom-dimension"
              aria-label="Add custom dimension"
              value={dimInput}
              onChange={(e) => setDimInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); handleAddDimension() } }}
              placeholder="e.g. API quality, data privacy"
              disabled={customDimensions.length >= MAX_CUSTOM_DIMENSIONS}
              className="flex-1 rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200 disabled:cursor-not-allowed disabled:bg-gray-50 disabled:text-gray-400"
            />
            <button
              type="button"
              onClick={handleAddDimension}
              disabled={customDimensions.length >= MAX_CUSTOM_DIMENSIONS}
              className="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
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
            Extra analysis axes the agents will address explicitly. Up to {MAX_CUSTOM_DIMENSIONS} dimensions.
          </p>
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
                  onChange={() => {
                    setSelectedDataMode(option.value)
                  }}
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
