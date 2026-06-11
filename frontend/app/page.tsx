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
    description: '对比各竞品的功能覆盖。',
  },
  {
    value: 'pricing_analysis',
    label: '定价分析',
    description: '对比套餐结构和价格点。',
  },
  {
    value: 'user_personas',
    label: '用户画像',
    description: '识别各产品的主要用户群。',
  },
  {
    value: 'swot',
    label: 'SWOT 分析',
    description: '分析优势、劣势、机会和威胁。',
  },
]

interface IndustryTypeOption {
  value: IndustryType
  label: string
  description: string
}

const INDUSTRY_TYPE_OPTIONS: IndustryTypeOption[] = [
  { value: 'ai_saas', label: 'AI / SaaS', description: '软件工具、API、开发者平台' },
  { value: 'ai_search', label: 'AI 搜索 / 问答', description: '答案引擎、聊天助手、研究工具' },
  { value: 'design_tools', label: '设计工具', description: '视觉设计、白板、创意套件' },
  { value: 'ecommerce', label: '电商', description: '电商平台、零售、交易市场' },
  { value: 'local_services', label: '本地生活', description: '外卖、到家服务、即时履约' },
  { value: 'open_source', label: '开源 / 非营利', description: '基金会、公共产品、社区项目' },
  { value: 'social', label: '社交 / 创作者', description: '社交平台、创作者工具、社区' },
  { value: 'general', label: '通用', description: '其他行业' },
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

const CUSTOM_DIMENSION_SUGGESTIONS_BY_INDUSTRY: Record<IndustryType, string[]> = {
  ai_saas: ['价格', '隐私', '本地部署', 'API', '企业版', '安全合规'],
  ai_search: ['答案质量', '来源引用', '实时性', '多模态', '隐私', '付费限制'],
  design_tools: ['协作体验', '模板生态', '品牌资产', '导出格式', '团队权限', '学习成本'],
  ecommerce: ['商品供给', '价格竞争力', '履约配送', '商家生态', '交易保障', '会员体系'],
  local_services: ['配送速度', '供给密度', '服务覆盖', '骑手/商家管理', '会员补贴', '售后体验'],
  open_source: ['社区活跃度', '治理结构', '文档质量', '商业支持', '捐赠/会员', '生态项目'],
  social: ['内容供给', '创作者激励', '社区氛围', '推荐机制', '互动玩法', '商业化干扰'],
  general: ['用户体验', '核心功能', '价格', '渠道', '品牌信任', '风险'],
}
const MAX_CUSTOM_DIMENSIONS = 8
const DEFAULT_GOALS = ['feature_comparison', 'user_personas']

function defaultGoalsForIndustryType(): string[] {
  return [...DEFAULT_GOALS]
}

const COMPETITOR_ROLE_OPTIONS: { value: CompetitorRole; label: string }[] = [
  { value: 'direct_competitor', label: '直接竞品' },
  { value: 'indirect_competitor', label: '间接竞品' },
  { value: 'inspiration_product', label: '参考产品' },
  { value: 'benchmark_leader', label: '标杆产品' },
]

const RESEARCH_KIND_OPTIONS: { value: ResearchInputKind; label: string }[] = [
  { value: 'survey', label: '问卷结果' },
  { value: 'interview', label: '访谈记录' },
  { value: 'questionnaire', label: '问卷设计' },
  { value: 'desk_research', label: '桌面研究' },
  { value: 'notes', label: '备注' },
]

const DEFAULT_COMPETITORS: CompetitorInput[] = [
  { name: 'Cursor', url: 'https://cursor.com', role: 'direct_competitor' },
  { name: 'Trae', url: 'https://www.trae.ai', role: 'direct_competitor' },
  { name: 'Windsurf', url: 'https://windsurf.ai', role: 'direct_competitor' },
]

function isDefaultCompetitorSet(rows: CompetitorInput[]): boolean {
  if (rows.length !== DEFAULT_COMPETITORS.length) return false
  return rows.every((row, index) => {
    const defaultRow = DEFAULT_COMPETITORS[index]
    return (
      row.name === defaultRow.name &&
      row.url === defaultRow.url &&
      (row.role ?? 'direct_competitor') === defaultRow.role
    )
  })
}

function extractIndustryTopic(input: string): string {
  const normalized = input.replace(/\s+/g, ' ').trim()
  if (!normalized) return ''

  const patterns = [
    /^(?:请|麻烦)?帮我分析一下\s*(.+?)\s*的竞品[。.!！?？]*$/i,
    /^(?:请|麻烦)?帮我分析\s*(.+?)\s*的竞品[。.!！?？]*$/i,
    /^(?:请|麻烦)?帮我看看\s*(.+?)\s*的竞品[。.!！?？]*$/i,
    /^分析一下\s*(.+?)\s*的竞品[。.!！?？]*$/i,
    /^分析\s*(.+?)\s*的竞品[。.!！?？]*$/i,
    /^(.+?)\s*的竞品[。.!！?？]*$/i,
  ]
  for (const pattern of patterns) {
    const match = normalized.match(pattern)
    if (match?.[1]?.trim()) return match[1].trim()
  }

  return normalized
    .replace(/^(?:请|麻烦)?帮我(?:分析|看看|了解)?(?:一下)?\s*/i, '')
    .replace(/\s*(?:的)?(?:竞品|竞争对手|对标产品|类似产品)[。.!！?？]*$/i, '')
    .trim() || normalized
}

function inferIndustryTypeFromTopic(topic: string): IndustryType | null {
  const lower = topic.toLowerCase()
  if (/^(qq|微信|wechat|telegram|discord|whatsapp|line|signal|snapchat)\b/.test(lower)) return 'social'
  if (/电商|电子商务|网购|网店|marketplace|e-?commerce|online store/.test(lower)) return 'ecommerce'
  if (/外卖|本地生活|配送|到家|跑腿|送餐|food delivery|local service|on-demand/.test(lower)) return 'local_services'
  if (/ai\s*搜索|ai搜索|答案引擎|问答|perplexity|answer engine/.test(lower)) return 'ai_search'
  if (/设计|figma|canva|adobe express|design tool|prototyp/.test(lower)) return 'design_tools'
  if (/开源|非营利|基金会|open source|foundation|nonprofit/.test(lower)) return 'open_source'
  if (/社交|社区|约会|交友|social|dating|community/.test(lower)) return 'social'
  if (/ai\s*coding|ai\s*编程|代码助手|编程助手|ide|coding assistant|code assistant/.test(lower)) return 'ai_saas'
  return null
}

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
    DEFAULT_GOALS
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

  const applyIndustryType = useCallback((value: IndustryType) => {
    setIndustryType(value)
    setGoals(defaultGoalsForIndustryType())
    setCompetitors((prev) => {
      if (value !== 'ai_saas' && isDefaultCompetitorSet(prev)) return []
      if (value === 'ai_saas' && prev.length === 0) return DEFAULT_COMPETITORS
      return prev
    })
  }, [])

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
      output_language: 'zh',
      report_depth: 'standard',
      data_mode: dataMode,
      research_inputs: researchInputs,
    }
    createMutation.mutate(payload)
  }

  const dataMode = selectedDataMode ?? (searchStatusQuery.data?.search_available ? 'live_with_fallback' : 'demo')
  const customDimensionSuggestions =
    CUSTOM_DIMENSION_SUGGESTIONS_BY_INDUSTRY[industryType] ??
    CUSTOM_DIMENSION_SUGGESTIONS_BY_INDUSTRY.general
  const submitDisabled =
    createMutation.isPending ||
    industry.trim().length === 0 ||
    competitors.every((c) => !c.name.trim() || !c.url.trim())

  return (
    <div className="mx-auto max-w-3xl">
      <header className="mb-8">
        <p className="text-xs font-medium uppercase tracking-wider text-blue-700">
          新建分析
        </p>
        <h1 className="mt-2 text-3xl font-semibold text-gray-900">
          创建竞品分析项目
        </h1>
        <p className="mt-2 max-w-xl text-sm text-gray-600">
          先明确分析主题、竞品和目标。启动后，采集、分析、撰写和 QA Agent 会按工作流依次执行。
        </p>
      </header>

      <form
        onSubmit={handleSubmit}
        className="space-y-6 rounded-xl border border-gray-200 bg-white p-6 shadow-sm"
      >
        <section className="space-y-3">
          <h2 className="text-sm font-medium text-gray-900">创建方式</h2>
          <div className="inline-flex rounded-md border border-gray-200 bg-gray-50 p-1">
            {([
              {
                value: 'discover' as const,
                label: '描述后发现',
              },
              {
                value: 'manual' as const,
                label: '手动填写',
              },
            ]).map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => setCreationMode(option.value)}
                className={cn(
                  'rounded px-3 py-1.5 text-xs font-medium transition-colors',
                  creationMode === option.value
                    ? 'bg-white text-blue-700 shadow-sm'
                    : 'text-gray-600 hover:text-gray-900'
                )}
              >
                {option.label}
              </button>
            ))}
          </div>
        </section>

        {creationMode === 'discover' && (
          <section className="space-y-2 rounded-md border border-blue-100 bg-blue-50/60 p-3">
            <label htmlFor="natural-language-query" className="text-sm font-medium text-gray-900">
              自然语言发现提示
            </label>
            <textarea
              id="natural-language-query"
              value={naturalLanguageQuery}
              onChange={(e) => {
                const value = e.target.value
                const topic = extractIndustryTopic(value)
                const inferredType = inferIndustryTypeFromTopic(topic)
                setNaturalLanguageQuery(value)
                setIndustry(topic)
                if (inferredType) applyIndustryType(inferredType)
              }}
              placeholder="例如：帮我分析一下 AI coding 的竞品"
              rows={3}
              className="w-full rounded-md border border-blue-200 bg-white px-3 py-2 text-sm text-gray-900 placeholder-gray-400 transition-shadow focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
            />
            <CompetitorDiscoveryPanel
              industry={extractIndustryTopic(naturalLanguageQuery)}
              industryType={industryType}
              onAdd={handleAddFromDiscovery}
              label="查找候选竞品"
              emptyLabel="没有找到候选竞品，可以切换到手动填写。"
            />
            <p className="text-xs text-gray-600">
              发现功能只负责推荐候选项，最终进入项目的竞品仍由你确认。
            </p>
          </section>
        )}

        {creationMode === 'manual' && (
        <section className="space-y-2">
          <label
            htmlFor="industry"
            className="text-sm font-medium text-gray-900"
          >
            行业 / 主题
          </label>
          <input
            id="industry"
            value={industry}
            onChange={(e) => setIndustry(e.target.value)}
            placeholder="例如：AI Coding Tools"
            className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 placeholder-gray-400 transition-shadow focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
            required
          />
          <p className="text-xs text-gray-500">
            Agent 会把它作为采集、分析和撰写时的上下文。
          </p>
        </section>
        )}

        <section className="space-y-3">
          <label htmlFor="industry-type" className="text-sm font-medium text-gray-900">
            行业类型
          </label>
          <select
            id="industry-type"
            value={industryType}
            onChange={(e) => applyIndustryType(e.target.value as IndustryType)}
            className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
          >
            {INDUSTRY_TYPE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label} — {option.description}
              </option>
            ))}
          </select>
          <p className="text-xs text-gray-500">
            用于选择更适合该行业的数据采集路径。
          </p>
        </section>

        <section className="space-y-3">
          <label htmlFor="analysis-purpose" className="text-sm font-medium text-gray-900">
            分析目的
          </label>
          <select
            id="analysis-purpose"
            value={analysisPurpose}
            onChange={(e) => setAnalysisPurpose(e.target.value as AnalysisPurpose)}
            className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
          >
            {ANALYSIS_PURPOSE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label} — {option.description}
              </option>
            ))}
          </select>
        </section>

        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-medium text-gray-900">竞品</h2>
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={handleAddCompetitor}
                className="text-xs font-medium text-blue-700 hover:text-blue-800"
              >
                + 添加竞品
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
                    aria-label="竞品名称"
                    value={row.name}
                    onChange={(e) =>
                      handleCompetitorChange(index, 'name', e.target.value)
                    }
                    placeholder="名称"
                    className="w-full rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200 sm:max-w-[180px]"
                  />
                  <input
                    id={`competitor-url-${index}`}
                    name={`competitor-url-${index}`}
                    aria-label="竞品官网 URL"
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
                    aria-label="竞品角色"
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
                    aria-label={`移除 ${row.name || '竞品'}`}
                  >
                    移除
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
          <h2 className="text-sm font-medium text-gray-900">研究输入 <span className="font-normal text-gray-400">（可选）</span></h2>
          <div className="rounded-md border border-gray-200 bg-gray-50 p-3">
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-[1fr_170px]">
              <input
                id="research-title"
                name="research-title"
                aria-label="研究输入标题"
                value={researchDraft.title}
                onChange={(e) => setResearchDraft((prev) => ({ ...prev, title: e.target.value }))}
                placeholder="例如：产品访谈记录"
                className="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
              />
              <select
                id="research-kind"
                name="research-kind"
                aria-label="研究输入类型"
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
              aria-label="绑定到竞品"
              value={researchDraft.competitor_name ?? ''}
              onChange={(e) => setResearchDraft((prev) => ({ ...prev, competitor_name: e.target.value }))}
              className="mt-2 w-full rounded-md border border-gray-300 bg-white px-2 py-1.5 text-xs text-gray-700 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
            >
              <option value="">应用到所有竞品</option>
              {competitors
                .filter((c) => c.name.trim())
                .map((c) => (
                  <option key={competitorKey(c)} value={c.name.trim()}>{c.name.trim()}</option>
                ))}
            </select>
            <textarea
              id="research-content"
              name="research-content"
              aria-label="研究输入内容"
              value={researchDraft.content}
              onChange={(e) => setResearchDraft((prev) => ({ ...prev, content: e.target.value }))}
              placeholder="粘贴问卷结果、问卷设计、访谈记录或人工研究观察。"
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
                添加研究输入
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
                      {item.competitor_name ? ` · ${item.competitor_name}` : ' · 所有竞品'}
                    </div>
                    <div className="mt-1 line-clamp-2 text-xs text-gray-600">{item.content}</div>
                  </div>
                  <button
                    type="button"
                    onClick={() => handleRemoveResearchInput(index)}
                    className="shrink-0 rounded-md px-2 py-1 text-xs text-gray-500 hover:bg-gray-100 hover:text-gray-900"
                  >
                    移除
                  </button>
                </div>
              ))}
            </div>
          )}
          <p className="text-xs text-gray-500">
            添加的材料会作为人工证据进入来源追溯。
          </p>
        </section>

        <section className="space-y-3">
          <h2 className="text-sm font-medium text-gray-900">分析目标</h2>
          <div className="flex flex-wrap gap-2">
            {GOAL_OPTIONS.map((goal) => {
              const checked = goals.includes(goal.value)
              return (
                <label
                  key={goal.value}
                  className={cn(
                    'inline-flex cursor-pointer items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors',
                    checked
                      ? 'border-blue-300 bg-blue-50'
                      : 'border-gray-200 bg-white hover:bg-gray-50'
                  )}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => handleToggleGoal(goal.value)}
                    className="h-3.5 w-3.5 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                  />
                  <span className="text-gray-900">{goal.label}</span>
                </label>
              )
            })}
          </div>
        </section>

        <section className="space-y-3">
          <h2 className="text-sm font-medium text-gray-900">自定义维度 <span className="text-gray-400 font-normal">（可选）</span></h2>
          <div className="flex flex-wrap gap-1.5">
            {customDimensionSuggestions.map((suggestion) => {
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
              aria-label="添加自定义维度"
              value={dimInput}
              onChange={(e) => setDimInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); handleAddDimension() } }}
              placeholder="例如：履约效率、社区活跃度"
              disabled={customDimensions.length >= MAX_CUSTOM_DIMENSIONS}
              className="flex-1 rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200 disabled:cursor-not-allowed disabled:bg-gray-50 disabled:text-gray-400"
            />
            <button
              type="button"
              onClick={handleAddDimension}
              disabled={customDimensions.length >= MAX_CUSTOM_DIMENSIONS}
              className="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
            >
              添加
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
                    aria-label={`移除 ${dim}`}
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
          )}
          <p className="text-xs text-gray-500">
            推荐项会随行业类型变化，也可以自行添加。最多 {MAX_CUSTOM_DIMENSIONS} 个维度。
          </p>
        </section>

        <section className="space-y-3">
          <label htmlFor="data-mode" className="text-sm font-medium text-gray-900">
            数据模式
          </label>
          <select
            id="data-mode"
            value={dataMode}
            onChange={(e) => setSelectedDataMode(e.target.value as 'demo' | 'live_with_fallback')}
            className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
          >
            <option value="live_with_fallback">
              真实采集
            </option>
            <option value="demo">
              Demo
            </option>
          </select>
          <p className="text-xs text-gray-500">
            默认跟随后端搜索状态：Tavily 可用时使用真实采集，否则使用 Demo。
          </p>
        </section>

        {createMutation.isError && (
          <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {createMutation.error instanceof Error
              ? createMutation.error.message
              : '项目创建失败。'}
          </div>
        )}

        <div className="flex items-center justify-between border-t border-gray-100 pt-4">
          <Link
            href="/projects"
            className="text-sm text-gray-600 hover:text-gray-900"
          >
            查看已有项目 &rarr;
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
            {createMutation.isPending ? '创建中...' : '创建项目'}
          </button>
        </div>
      </form>
    </div>
  )
}
