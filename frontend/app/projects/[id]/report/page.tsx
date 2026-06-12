'use client'

/**
 * Report viewer page.
 *
 * Pulls report + traces in parallel. Surfaces:
 *  - the QA fallback warning if WriterAgent ran in fallback mode
 *  - a tabbed view of summary, pricing, features, SWOT, recommendations,
 *    full markdown, and QA result
 *
 * The SourcePanel is mounted at the root of the page so any citation
 * badge in any tab can open it (overlay).
 */

import Link from 'next/link'
import { use, useMemo, useState, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

import { api } from '@/lib/api'
import type { AgentRun, Claim, CompetitorInProject, CompetitiveReport, CompetitorKnowledge, CompetitorScore, QAResult, QATraceOutput, SourceEvidence } from '@/lib/types'
import { useSourcePanel } from '@/lib/store'
import { formatDateTime } from '@/lib/formatDateTime'

import { ClaimList } from '@/components/report-viewer/ClaimList'
import { DroppedCompetitorsList } from '@/components/report-viewer/DroppedCompetitorsList'
import type { DroppedCompetitor } from '@/components/report-viewer/DroppedCompetitorsList'
import { FeatureComparisonTable } from '@/components/report-viewer/FeatureComparisonTable'
import { InsufficientDataView } from '@/components/report-viewer/InsufficientDataView'
import { PricingComparisonTable } from '@/components/report-viewer/PricingComparisonTable'
import { ScoringMatrix } from '@/components/report-viewer/ScoringMatrix'
import { SWOTView } from '@/components/report-viewer/SWOTView'
import { TabsBar, type TabItem } from '@/components/report-viewer/TabsBar'
import { QaStatusBanner } from '@/components/qa/QaStatusBanner'
import { QAResultBanner } from '@/components/qa/QAResultBanner'
import { SourcePanel } from '@/components/source-viewer/SourcePanel'

interface PageProps {
  params: Promise<{ id: string }>
}

type TabValue = string

export default function ReportPage({ params }: PageProps) {
  const { id } = use(params)
  const [activeTab, setActiveTab] = useState<TabValue>('summary')
  const [correctionOpen, setCorrectionOpen] = useState(false)
  const queryClient = useQueryClient()

  const reportQuery = useQuery({
    queryKey: ['report', id],
    queryFn: () => api.getReport(id),
  })

  const tracesQuery = useQuery({
    queryKey: ['traces', id],
    queryFn: () => api.getTraces(id),
  })

  const projectQuery = useQuery({
    queryKey: ['project', id],
    queryFn: () => api.getProject(id),
  })

  const correctionMutation = useMutation({
    mutationFn: (payload: Partial<CompetitiveReport>) =>
      api.patchReport(id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['report', id] })
      queryClient.invalidateQueries({ queryKey: ['traces', id] })
      setCorrectionOpen(false)
    },
  })

  const traces = useMemo(() => tracesQuery.data?.traces ?? [], [tracesQuery.data])
  const projectStatus = projectQuery.data?.status
  const requestedCompetitors = useMemo(() => projectQuery.data?.competitors ?? [], [projectQuery.data])

  const isFallback = useMemo(
    () =>
      traces.some(
        (t) =>
          t.agent_name.includes('Writer') &&
          (t.output as Record<string, unknown>)?.is_fallback === true
      ),
    [traces]
  )

  const qaResult = useMemo<QAResult | undefined>(() => extractLatestQA(traces), [traces])

  const droppedCompetitors = useMemo<DroppedCompetitor[]>(
    () => computeDroppedCompetitors(requestedCompetitors, reportQuery.data, traces),
    [requestedCompetitors, reportQuery.data, traces]
  )

  const tabs: TabItem[] = useMemo(() => {
    const allIssues = qaResult?.issues ?? []
    const highCount   = allIssues.filter((i) => i.severity === 'high').length
    const mediumCount = allIssues.filter((i) => i.severity === 'medium').length
    const lowCount    = allIssues.filter((i) => i.severity === 'low').length
    const qaTab: TabItem = {
        value: 'qa',
        label: 'QA 结果',
        badge:
          qaResult && !qaResult.passed ? (
            <span className="rounded-full bg-red-100 px-1.5 py-0.5 text-[10px] font-semibold text-red-700">
              {highCount} 阻塞
            </span>
          ) : qaResult?.passed && mediumCount > 0 ? (
            <span className="rounded-full bg-orange-100 px-1.5 py-0.5 text-[10px] font-semibold text-orange-700">
              {mediumCount} 警告
            </span>
          ) : qaResult?.passed && lowCount > 0 ? (
            <span className="rounded-full bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold text-amber-700">
              {lowCount} 提示
            </span>
          ) : qaResult?.passed ? (
            <span className="rounded-full bg-green-100 px-1.5 py-0.5 text-[10px] font-semibold text-green-700">
              通过
            </span>
          ) : null,
      }
    const report = reportQuery.data
    const selected = report?.selected_report_tabs?.length
      ? report.selected_report_tabs
      : buildSelectedReportTabs(
        projectQuery.data?.goals ?? [],
        projectQuery.data?.analysis_frameworks ?? report?.analysis_frameworks ?? ['swot'],
        projectQuery.data?.custom_dimensions ?? []
      )
    return ensureStandardTabs(
      selected,
      report?.custom_dimension_sections,
      report?.analysis_purpose,
      report?.competitor_scores
    ).map((value) => {
      if (value === 'qa') return qaTab
      return { value, label: tabLabel(value) }
    })
  }, [projectQuery.data, qaResult, reportQuery.data])

  const currentTab = tabs.some((tab) => tab.value === activeTab)
    ? activeTab
    : tabs[0]?.value ?? activeTab

  if (reportQuery.isLoading) {
    return <ReportSkeleton id={id} />
  }

  if (reportQuery.isError) {
    return (
      <div className="space-y-4">
        <Breadcrumb id={id} />
        <div className="rounded-md border border-red-200 bg-red-50 p-6 text-sm text-red-700">
          报告加载失败。{' '}
          {reportQuery.error instanceof Error ? reportQuery.error.message : '未知错误。'} 工作流可能还没有生成报告。
        </div>
        <Link
          href={`/projects/${id}`}
          className="rounded-md border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
        >
          &larr; 返回项目
        </Link>
      </div>
    )
  }

  const report = reportQuery.data!

  const qaScore = qaResult?.score ?? 0
  const citedSources = report.source_list?.length ?? 0
  const summaryLen = report.executive_summary?.length ?? 0
  const isInsufficientData =
    citedSources === 0 || summaryLen === 0
  return (
    <div className="space-y-5">
      {/* Breadcrumb hidden in print */}
      <div className="print:hidden">
        <Breadcrumb id={id} title={report.title} />
      </div>

      {isFallback && (
        <div className="rounded-md border border-yellow-200 bg-yellow-50 p-4 text-sm text-yellow-900">
          <span className="font-semibold">⚠ 兜底模式： </span>
          报告是在 LLM 调用未成功的情况下生成的，摘要和战略建议可能不完整或偏通用。
        </div>
      )}

      {projectStatus && projectStatus !== 'completed' && projectStatus !== 'running' && projectStatus !== 'created' && (
        <QaStatusBanner status={projectStatus} droppedCount={droppedCompetitors.length} />
      )}

      <header className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <p className="text-xs font-medium tracking-wider text-blue-700 uppercase print:hidden">
          竞品分析
        </p>
        <h1 className="mt-1 text-2xl font-semibold text-gray-900">{report.title}</h1>
        <p className="mt-2 text-xs text-gray-500">
          生成时间：{formatDateTime(report.created_at)} · 项目：{report.project_id}
        </p>
        <div className="mt-3 flex flex-wrap gap-3 text-xs text-gray-600">
          {droppedCompetitors.length > 0 ? (
            <span className="text-orange-600">
              已分析 {report.competitor_overview?.length ?? 0} / {requestedCompetitors.length} 个竞品
              （{droppedCompetitors.length} 个被剔除）
            </span>
          ) : (
            <span>{report.competitor_overview?.length ?? 0} 个竞品</span>
          )}
          <SourceCountChip sourceList={report.source_list ?? []} />
          <span>{report.executive_summary?.length ?? 0} 条摘要结论</span>
        </div>
      </header>

      <div className="print:hidden">
        <button
          type="button"
          onClick={() => setCorrectionOpen((v) => !v)}
          className="rounded-md border border-blue-200 bg-blue-50 px-4 py-2 text-sm font-medium text-blue-700 transition-colors hover:bg-blue-100"
        >
          {correctionOpen ? '收起人工修正' : '人工修正报告'}
        </button>
        {correctionOpen && (
          <HumanCorrectionPanel
            report={report}
            isPending={correctionMutation.isPending}
            error={correctionMutation.error}
            onCancel={() => setCorrectionOpen(false)}
            onSave={(payload) => correctionMutation.mutate(payload)}
          />
        )}
      </div>

      {/* Tabbed interface — hidden when printing */}
      <div className="print:hidden">
        {isInsufficientData ? (
          <InsufficientDataView
            report={report}
            qaResult={qaResult}
            traces={traces}
            requestedCompetitors={requestedCompetitors}
            qaScore={qaScore}
            citedSources={citedSources}
          />
        ) : (
          <>
            <TabsBar items={tabs} value={currentTab} onChange={(v) => setActiveTab(v as TabValue)} />

        <section role="tabpanel" className="pt-2">
          {currentTab === 'summary' && (
            <>
              {(report.analysis_objective || (report.competitor_selection_rationale && Object.keys(report.competitor_selection_rationale).length > 0)) && (
                <div className="mb-4 rounded-lg border border-blue-200 bg-blue-50 p-4 text-sm">
                  {report.analysis_objective && (
                    <p className="text-blue-900 font-medium">{report.analysis_objective}</p>
                  )}
                  {report.competitor_selection_rationale && Object.keys(report.competitor_selection_rationale).length > 0 && (
                    <ul className="mt-2 space-y-0.5 text-blue-800 text-xs">
                      {Object.entries(report.competitor_selection_rationale).map(([name, rationale]) => (
                        <li key={name}><span className="font-medium">{name}:</span> {rationale}</li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
              <ClaimList
                claims={report.executive_summary}
                sourceList={report.source_list}
                emptyMessage="暂无执行摘要。"
              />
            </>
          )}
          {currentTab === 'pricing' && (
            <PricingComparisonTable
              data={normalizeStringMap(report.pricing_comparison)}
              emptyMessage="暂无定价数据。"
            />
          )}
          {currentTab === 'pricing_analysis' && (
            <PricingComparisonTable
              data={normalizeStringMap(report.pricing_comparison)}
              emptyMessage="暂无定价数据。"
            />
          )}
          {currentTab === 'features' && (
            <FeatureComparisonTable
              data={normalizeStringMap(report.feature_comparison)}
              emptyMessage="暂无功能数据。"
            />
          )}
          {currentTab === 'feature_comparison' && (
            <FeatureComparisonTable
              data={normalizeStringMap(report.feature_comparison)}
              emptyMessage="暂无功能数据。"
            />
          )}
          {currentTab === 'user_personas' && (
            <PersonaTab competitors={report.competitor_overview ?? []} />
          )}
          {currentTab === 'user_reviews' && (
            <UserReviewsTab sourceList={report.source_list ?? []} />
          )}
          {currentTab === 'sources' && (
            <SourcesTab sourceList={report.source_list ?? []} />
          )}
          {currentTab === 'swot' && (
            <SWOTView
              swotComparison={report.swot_comparison ?? {}}
              competitorOverview={report.competitor_overview ?? []}
              sourceList={report.source_list ?? []}
            />
          )}
          {currentTab === 'three_c' && (
            <StructuredSection data={report.framework_sections?.three_c} emptyMessage="暂无 3C 分析。" />
          )}
          {currentTab === 'aarrr' && (
            <StructuredSection data={report.framework_sections?.aarrr} emptyMessage="暂无 AARRR 分析。" />
          )}
          {currentTab.startsWith('custom_dimension:') && (
            <StructuredSection
              data={report.custom_dimension_sections?.[currentTab.slice('custom_dimension:'.length)]}
              emptyMessage="暂无足够证据。"
            />
          )}
          {currentTab === 'scoring' && (
            <ScoringMatrix
              competitorScores={report.competitor_scores}
              purposeSections={report.purpose_sections}
            />
          )}
          {currentTab === 'recommendations' && (
            <ClaimList
              claims={report.strategic_recommendations}
              sourceList={report.source_list}
              emptyMessage="暂无战略建议。"
            />
          )}
          {currentTab === 'markdown' && (
            <MarkdownTab markdown={report.markdown_content} sourceList={report.source_list} />
          )}
          {currentTab === 'qa' && (
            <>
              {qaResult ? (
                <QAResultBanner result={qaResult} />
              ) : (
                <p className="rounded-md border border-dashed border-gray-300 bg-white px-4 py-6 text-center text-sm text-gray-500">
                  暂无 QA 结果。
                </p>
              )}
              {droppedCompetitors.length > 0 && (
                <DroppedCompetitorsList dropped={droppedCompetitors} className="mt-4" />
              )}
            </>
          )}
        </section>
          </>
        )}
      </div>

      {/* Action buttons — hidden when printing */}
      <div className="flex flex-wrap gap-3 pt-3 print:hidden">
        <Link
          href={`/projects/${id}`}
          className="rounded-md border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
        >
          &larr; 返回项目
        </Link>
        <Link
          href={`/projects/${id}/traces`}
          className="rounded-md border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
        >
          查看 Agent Trace
        </Link>
        <button
          type="button"
          onClick={() => exportMarkdown(report.markdown_content, report.title, report.source_list ?? [])}
          className="rounded-md border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
        >
          导出 MD
        </button>
        <Link
          href={`/projects/${id}/print`}
          target="_blank"
          rel="noopener noreferrer"
          className="rounded-md border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
        >
          {projectStatus === 'qa_failed' ? '导出部分 PDF' : '导出 PDF'}
        </Link>
      </div>

      {/* Mounted at the page root so it overlays everything. */}
      <SourcePanel />
    </div>
  )
}

function HumanCorrectionPanel({
  report,
  isPending,
  error,
  onCancel,
  onSave,
}: {
  report: CompetitiveReport
  isPending: boolean
  error: unknown
  onCancel: () => void
  onSave: (payload: Partial<CompetitiveReport>) => void
}) {
  const [title, setTitle] = useState(report.title)
  const [objective, setObjective] = useState(report.analysis_objective ?? '')
  const [summary, setSummary] = useState(claimsToLines(report.executive_summary))
  const [recommendations, setRecommendations] = useState(claimsToLines(report.strategic_recommendations))
  const [competitorOverview, setCompetitorOverview] = useState(toPrettyJson(report.competitor_overview ?? []))
  const [features, setFeatures] = useState(toPrettyJson(report.feature_comparison ?? {}))
  const [pricing, setPricing] = useState(toPrettyJson(report.pricing_comparison ?? {}))
  const [personas, setPersonas] = useState(toPrettyJson(report.user_persona_comparison ?? {}))
  const [swot, setSwot] = useState(toPrettyJson(report.swot_comparison ?? {}))
  const [frameworks, setFrameworks] = useState(toPrettyJson(report.framework_sections ?? {}))
  const [customDimensions, setCustomDimensions] = useState(toPrettyJson(report.custom_dimension_sections ?? {}))
  const [competitorScores, setCompetitorScores] = useState(toPrettyJson(report.competitor_scores ?? {}))
  const [purposeSections, setPurposeSections] = useState(toPrettyJson(report.purpose_sections ?? {}))
  const [rationale, setRationale] = useState(toPrettyJson(report.competitor_selection_rationale ?? {}))
  const [parseError, setParseError] = useState<string | null>(null)
  const markdownPreview = useMemo(
    () =>
      buildCorrectionMarkdownPreview({
        title,
        objective,
        summary,
        recommendations,
        competitorOverview,
        features,
        pricing,
        personas,
        swot,
        frameworks,
        customDimensions,
        competitorScores,
        purposeSections,
        rationale,
      }),
    [
      title,
      objective,
      summary,
      recommendations,
      competitorOverview,
      features,
      pricing,
      personas,
      swot,
      frameworks,
      customDimensions,
      competitorScores,
      purposeSections,
      rationale,
    ]
  )

  const save = () => {
    try {
      setParseError(null)
      onSave({
        title,
        analysis_objective: objective,
        executive_summary: mergeClaimLines(report.executive_summary, summary),
        strategic_recommendations: mergeClaimLines(report.strategic_recommendations, recommendations),
        competitor_overview: parseJsonField<CompetitorKnowledge[]>(competitorOverview, '竞品画像'),
        feature_comparison: parseJsonField<Record<string, string>>(features, '功能对比'),
        pricing_comparison: parseJsonField<Record<string, string>>(pricing, '定价模式'),
        user_persona_comparison: parseJsonField<Record<string, unknown>>(personas, '用户画像对比'),
        swot_comparison: parseJsonField<Record<string, unknown>>(swot, 'SWOT'),
        framework_sections: parseJsonField<Record<string, unknown>>(frameworks, '分析框架'),
        custom_dimension_sections: parseJsonField<Record<string, unknown>>(customDimensions, '自定义维度'),
        competitor_scores: parseJsonField<Record<string, CompetitorScore>>(competitorScores, '产品选择评分'),
        purpose_sections: parseJsonField<Record<string, unknown>>(purposeSections, '选择建议'),
        competitor_selection_rationale: parseJsonField<Record<string, string>>(rationale, '竞品选择说明'),
      })
    } catch (err) {
      setParseError(err instanceof Error ? err.message : 'JSON 格式不正确。')
    }
  }

  return (
    <section className="mt-3 rounded-lg border border-blue-200 bg-white p-4 shadow-sm">
      <div className="grid gap-3">
        <label className="grid gap-1 text-sm">
          <span className="font-medium text-gray-800">报告标题</span>
          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            className="rounded-md border border-gray-300 px-3 py-2 text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
          />
        </label>
        <label className="grid gap-1 text-sm">
          <span className="font-medium text-gray-800">分析目标说明</span>
          <textarea
            value={objective}
            onChange={(event) => setObjective(event.target.value)}
            rows={2}
            className="rounded-md border border-gray-300 px-3 py-2 text-sm leading-relaxed outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
          />
        </label>
        <EditableTextBlock label="摘要" value={summary} onChange={setSummary} />
        <EditableTextBlock label="建议" value={recommendations} onChange={setRecommendations} />
        <EditableJsonBlock label="竞品画像 / 用户画像" value={competitorOverview} onChange={setCompetitorOverview} rows={12} />
        <EditableJsonBlock label="功能对比" value={features} onChange={setFeatures} />
        <EditableJsonBlock label="定价模式" value={pricing} onChange={setPricing} />
        <EditableJsonBlock label="用户画像对比" value={personas} onChange={setPersonas} />
        <EditableJsonBlock label="SWOT" value={swot} onChange={setSwot} rows={8} />
        <EditableJsonBlock label="分析框架" value={frameworks} onChange={setFrameworks} rows={8} />
        <EditableJsonBlock label="自定义维度" value={customDimensions} onChange={setCustomDimensions} rows={8} />
        <EditableJsonBlock label="产品选择评分" value={competitorScores} onChange={setCompetitorScores} rows={8} />
        <EditableJsonBlock label="选择建议 / 不建议人群" value={purposeSections} onChange={setPurposeSections} rows={8} />
        <EditableJsonBlock label="竞品选择说明" value={rationale} onChange={setRationale} />
        <label className="grid gap-1 text-sm">
          <span className="font-medium text-gray-800">Markdown 正文</span>
          <textarea
            value={markdownPreview}
            readOnly
            rows={10}
            className="min-h-40 rounded-md border border-gray-200 bg-gray-50 px-3 py-2 font-mono text-xs leading-relaxed text-gray-500"
          />
          <span className="text-xs text-gray-500">Markdown 会根据上面的结构化内容自动重新生成。</span>
        </label>
      </div>
      {Boolean(parseError || error) && (
        <p className="mt-3 rounded border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
          {parseError || (error instanceof Error ? error.message : '保存失败。')}
        </p>
      )}
      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={save}
          disabled={isPending || !title.trim()}
          className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-gray-300"
        >
          {isPending ? '保存中...' : '保存修正版本'}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded-md border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
        >
          取消
        </button>
      </div>
    </section>
  )
}

function EditableTextBlock({
  label,
  value,
  onChange,
}: {
  label: string
  value: string
  onChange: (value: string) => void
}) {
  return (
    <label className="grid gap-1 text-sm">
      <span className="font-medium text-gray-800">{label}</span>
      <textarea
        value={value}
        onChange={(event) => onChange(event.target.value)}
        rows={4}
        className="rounded-md border border-gray-300 px-3 py-2 text-sm leading-relaxed outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
      />
      <span className="text-xs text-gray-500">每行一条，保存时会保留原有引用和置信度。</span>
    </label>
  )
}

function EditableJsonBlock({
  label,
  value,
  onChange,
  rows = 6,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  rows?: number
}) {
  return (
    <label className="grid gap-1 text-sm">
      <span className="font-medium text-gray-800">{label}</span>
      <textarea
        value={value}
        onChange={(event) => onChange(event.target.value)}
        rows={rows}
        className="rounded-md border border-gray-300 px-3 py-2 font-mono text-xs leading-relaxed outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
      />
    </label>
  )
}

function claimsToLines(claims: Claim[] | undefined): string {
  return (claims ?? []).map((claim) => claim.text).join('\n')
}

function mergeClaimLines(existing: Claim[] | undefined, lines: string): Claim[] {
  return lines
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((text, index) => ({
      ...(existing?.[index] ?? { evidence: [], confidence: 'medium', is_hypothesis: true }),
      text,
    }))
}

function toPrettyJson(value: unknown): string {
  return JSON.stringify(value ?? {}, null, 2)
}

function parseJsonField<T>(value: string, label: string): T {
  try {
    return JSON.parse(value) as T
  } catch {
    throw new Error(`${label} 的 JSON 格式不正确。`)
  }
}

function buildCorrectionMarkdownPreview({
  title,
  objective,
  summary,
  recommendations,
  competitorOverview,
  features,
  pricing,
  personas,
  swot,
  frameworks,
  customDimensions,
  competitorScores,
  purposeSections,
  rationale,
}: {
  title: string
  objective: string
  summary: string
  recommendations: string
  competitorOverview: string
  features: string
  pricing: string
  personas: string
  swot: string
  frameworks: string
  customDimensions: string
  competitorScores: string
  purposeSections: string
  rationale: string
}): string {
  const lines = [`# ${title || 'Competitive Analysis Report'}`, '']
  appendTextSection(lines, 'Analysis Objective', objective)
  appendLineListSection(lines, 'Executive Summary', summary)
  appendJsonPreviewSection(lines, 'Competitor Overview', competitorOverview)
  appendJsonPreviewSection(lines, 'Feature Comparison', features)
  appendJsonPreviewSection(lines, 'Pricing Comparison', pricing)
  appendJsonPreviewSection(lines, 'User Personas', personas)
  appendJsonPreviewSection(lines, 'SWOT', swot)
  appendJsonPreviewSection(lines, 'Analysis Frameworks', frameworks)
  appendJsonPreviewSection(lines, 'Custom Dimensions', customDimensions)
  appendJsonPreviewSection(lines, 'Product Selection Scores', competitorScores)
  appendJsonPreviewSection(lines, 'Product Selection Guidance', purposeSections)
  appendJsonPreviewSection(lines, 'Competitor Selection Rationale', rationale)
  appendLineListSection(lines, 'Strategic Recommendations', recommendations)
  return lines.join('\n').trim()
}

function appendTextSection(lines: string[], title: string, value: string) {
  const text = value.trim()
  if (!text) return
  lines.push(`## ${title}`, '', text, '')
}

function appendLineListSection(lines: string[], title: string, value: string) {
  const items = value.split('\n').map((line) => line.trim()).filter(Boolean)
  if (items.length === 0) return
  lines.push(`## ${title}`, '', ...items.map((item) => `- ${item}`), '')
}

function appendJsonPreviewSection(lines: string[], title: string, value: string) {
  const text = value.trim()
  if (!text || text === '{}' || text === '[]') return
  lines.push(`## ${title}`, '', text, '')
}

function SourceCountChip({ sourceList }: { sourceList: SourceEvidence[] }) {
  const total = sourceList.length
  const liveCount = sourceList.filter((s) => s.data_source === 'live').length
  const searchCount = sourceList.filter((s) => s.data_source === 'search').length
  const demoCount = sourceList.filter((s) => s.data_source === 'demo').length
  const hasDataSource = liveCount > 0 || demoCount > 0 || searchCount > 0

  if (!hasDataSource) return <span>{total} 个引用来源</span>
  if (liveCount === 0 && searchCount === 0) return <span>{total} 个引用来源（Demo）</span>

  const parts: string[] = []
  if (liveCount > 0) parts.push(`${liveCount} 个真实来源`)
  if (searchCount > 0) parts.push(`${searchCount} 个搜索来源`)
  if (demoCount > 0) parts.push(`${demoCount} 个 Demo`)
  return <span>{total} 个引用来源 · {parts.join(' · ')}</span>
}

function MarkdownTab({ markdown, sourceList }: { markdown: string; sourceList: SourceEvidence[] }) {
  const { openSource } = useSourcePanel()

  // Build source_id → 1-based index map for citation numbering
  const sourceIndex = useMemo(
    () => new Map(sourceList.map((s, i) => [s.source_id, i + 1])),
    [sourceList]
  )

  // Replace [src_xxxxxxxx] patterns with a markdown link: [[N]](cite:src_xxxxxxxx)
  const processedMarkdown = useMemo(() => {
    if (!markdown) return ''
    return markdown.replace(/\[src_[0-9a-f]+\]/g, (match) => {
      const id = match.slice(1, -1)
      const num = sourceIndex.get(id)
      return `[[${num ?? '?'}]](#cite-${id})`
    })
  }, [markdown, sourceIndex])

  return (
    <article className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
      <div className="markdown-body text-sm leading-relaxed text-gray-800">
        {processedMarkdown ? (
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              a({ href, children }) {
                if (href?.startsWith('#cite-')) {
                  const sourceId = href.slice(6)
                  return (
                    <button
                      type="button"
                      onClick={(e) => { e.preventDefault(); openSource(sourceId) }}
                      className="mx-0.5 inline-flex cursor-pointer items-center rounded border border-blue-200 bg-blue-50 px-1 py-0.5 font-mono text-[11px] font-semibold text-blue-700 hover:bg-blue-100"
                    >
                      {children}
                    </button>
                  )
                }
                return (
                  <a href={href} target="_blank" rel="noopener noreferrer">
                    {children}
                  </a>
                )
              },
            }}
          >
            {processedMarkdown}
          </ReactMarkdown>
        ) : (
          <p className="text-sm text-gray-500">暂无 Markdown 内容。</p>
        )}
      </div>
      <hr className="my-6 border-gray-200" />
      <h2 className="mb-3 text-base font-semibold text-gray-900">来源</h2>
      {sourceList && sourceList.length > 0 ? (
        <ol className="space-y-2 text-sm">
          {sourceList.map((s, i) => (
            <li
              key={s.source_id}
              className="flex items-baseline gap-2 rounded border border-gray-100 px-2 py-1"
            >
              <span className="text-xs text-gray-400">[{i + 1}]</span>
              <div>
                <a
                  href={s.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-medium text-blue-700 underline hover:text-blue-800"
                >
                  {s.title || s.url}
                </a>
                <div className="text-xs text-gray-500">
                  {s.competitor_name} · {s.source_type} · 获取时间 {formatDateTime(s.retrieved_at)}
                </div>
              </div>
            </li>
          ))}
        </ol>
      ) : (
        <p className="text-sm text-gray-500">暂无来源列表。</p>
      )}
    </article>
  )
}

function Breadcrumb({ id, title }: { id: string; title?: string }) {
  return (
    <nav className="text-sm text-gray-500">
      <Link href="/projects" className="hover:text-gray-900">
        项目
      </Link>
      <span className="mx-1">/</span>
      <Link href={`/projects/${id}`} className="hover:text-gray-900">
        {id}
      </Link>
      <span className="mx-1">/</span>
      <span className="text-gray-900">{title ?? '报告'}</span>
    </nav>
  )
}

function ReportSkeleton({ id }: { id: string }) {
  return (
    <div className="space-y-4">
      <Breadcrumb id={id} />
      <div className="h-28 animate-pulse rounded-xl border border-gray-200 bg-white" />
      <div className="h-12 animate-pulse rounded-md bg-white" />
      <div className="h-60 animate-pulse rounded-xl border border-gray-200 bg-white" />
    </div>
  )
}

function exportMarkdown(content: string, title: string, sourceList: SourceEvidence[]) {
  const filename = title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '') || 'report'

  const sourceIndex = new Map(sourceList.map((s, i) => [s.source_id, i + 1]))
  const cleaned = content.replace(/\[src_[0-9a-f]+\]/g, (match) => {
    const id = match.slice(1, -1)
    const num = sourceIndex.get(id)
    return `[${num ?? '?'}]`
  })

  const sourceSection =
    sourceList.length > 0
      ? '\n\n## Sources\n\n' +
        sourceList
          .map((s, i) => `${i + 1}. ${s.title || s.url} — ${s.url}`)
          .join('\n')
      : ''

  const blob = new Blob([cleaned + sourceSection], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${filename}.md`
  a.click()
  URL.revokeObjectURL(url)
}

function extractLatestQA(traces: AgentRun[]): QAResult | undefined {
  const qaRun = [...traces].reverse().find((t) => t.agent_name.includes('QA'))
  if (!qaRun) return undefined
  const out = qaRun.output as Partial<QATraceOutput>
  if (typeof out?.passed !== 'boolean' || typeof out?.score !== 'number') {
    return undefined
  }
  return {
    passed: out.passed,
    score: out.score,
    issues: out.issues ?? [],
  }
}

function normalizeStringMap(input: unknown): Record<string, string> {
  if (!input || typeof input !== 'object') return {}
  const out: Record<string, string> = {}
  for (const [k, v] of Object.entries(input as Record<string, unknown>)) {
    if (typeof v === 'string') {
      out[k] = v
    } else if (v != null) {
      try {
        out[k] = JSON.stringify(v)
      } catch {
        out[k] = String(v)
      }
    }
  }
  return out
}

function buildSelectedReportTabs(goals: string[], frameworks: string[], customDimensions: string[]): string[] {
  const tabs = ['summary']
  for (const value of goals) {
    if (!tabs.includes(value)) tabs.push(value)
  }
  for (const value of frameworks.length > 0 ? frameworks : ['swot']) {
    if (!tabs.includes(value)) tabs.push(value)
  }
  for (const dim of customDimensions) {
    const key = `custom_dimension:${dim}`
    if (!tabs.includes(key)) tabs.push(key)
  }
  tabs.push('recommendations')
  tabs.push('sources')
  tabs.push('qa')
  return tabs
}

function ensureStandardTabs(
  tabs: string[],
  customDimensionSections?: Record<string, unknown>,
  analysisPurpose?: string,
  competitorScores?: Record<string, unknown>
): string[] {
  let next = [...tabs]
  for (const dim of Object.keys(customDimensionSections ?? {})) {
    const key = `custom_dimension:${dim}`
    if (!next.includes(key)) {
      const qaIndex = next.indexOf('qa')
      const sourcesIndex = next.indexOf('sources')
      const insertAt =
        sourcesIndex !== -1 ? sourcesIndex : qaIndex !== -1 ? qaIndex : next.length
      next = [...next.slice(0, insertAt), key, ...next.slice(insertAt)]
    }
  }
  if (!next.includes('recommendations')) {
    const qaIndex = next.indexOf('qa')
    const sourcesIndex = next.indexOf('sources')
    const insertAt =
      sourcesIndex !== -1 ? sourcesIndex : qaIndex !== -1 ? qaIndex : next.length
    next = [...next.slice(0, insertAt), 'recommendations', ...next.slice(insertAt)]
  }
  const hasScoringData =
    analysisPurpose === 'choose_product' ||
    Object.keys(competitorScores ?? {}).length > 0
  if (!next.includes('scoring') && hasScoringData) {
    const recommendationsIndex = next.indexOf('recommendations')
    const insertAt = recommendationsIndex !== -1 ? recommendationsIndex : next.length
    next = [...next.slice(0, insertAt), 'scoring', ...next.slice(insertAt)]
  }
  if (!next.includes('sources')) {
    const qaIndex = next.indexOf('qa')
    if (qaIndex === -1) return [...next, 'sources']
    next = [...next.slice(0, qaIndex), 'sources', ...next.slice(qaIndex)]
  }
  return next
}

function tabLabel(value: string): string {
  if (value === 'summary') return '摘要'
  if (value === 'feature_comparison' || value === 'features') return '功能对比'
  if (value === 'pricing_analysis' || value === 'pricing') return '定价模式'
  if (value === 'user_personas') return '用户画像'
  if (value === 'user_reviews') return '用户评价'
  if (value === 'swot') return 'SWOT'
  if (value === 'three_c') return '3C'
  if (value === 'aarrr') return 'AARRR'
  if (value === 'scoring') return '评分'
  if (value === 'recommendations') return '建议'
  if (value === 'sources') return 'Sources'
  if (value.startsWith('custom_dimension:')) return value.slice('custom_dimension:'.length)
  return value
}

function PersonaTab({ competitors }: { competitors: CompetitorKnowledge[] }) {
  const withPersonas = competitors.filter((c) => (c.user_personas?.length ?? 0) > 0)
  if (withPersonas.length === 0) {
    return <p className="rounded-md border border-dashed border-gray-300 bg-white px-4 py-6 text-center text-sm text-gray-500">暂无用户画像数据。</p>
  }
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {withPersonas.map((comp) => (
        <div key={comp.competitor_id ?? comp.competitor_name} className="rounded-lg border border-gray-200 bg-white p-4">
          <h3 className="text-sm font-semibold text-gray-900">{comp.competitor_name}</h3>
          <div className="mt-3 space-y-3">
            {comp.user_personas.map((persona, index) => (
              <div key={`${persona.name}-${index}`} className="text-sm">
                <div className="font-medium text-gray-900">{persona.name}</div>
                <p className="mt-1 text-gray-600">{persona.description}</p>
                {(persona.needs?.length ?? 0) > 0 && (
                  <p className="mt-1 text-xs text-gray-500">需求：{persona.needs.join('、')}</p>
                )}
                {(persona.pain_points?.length ?? 0) > 0 && (
                  <p className="mt-1 text-xs text-gray-500">痛点：{persona.pain_points.join('、')}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

function UserReviewsTab({ sourceList }: { sourceList: SourceEvidence[] }) {
  const manualSources = sourceList.filter((source) =>
    source.data_source === 'manual' || String(source.source_type).includes('manual')
  )
  if (manualSources.length === 0) {
    return <p className="rounded-md border border-dashed border-gray-300 bg-white px-4 py-6 text-center text-sm text-gray-500">暂无研究输入。</p>
  }
  return (
    <div className="space-y-3">
      {manualSources.map((source) => (
        <article key={source.source_id} className="rounded-lg border border-gray-200 bg-white p-4">
          <div className="text-sm font-semibold text-gray-900">{source.title || '研究输入'}</div>
          <div className="mt-1 text-xs text-gray-500">{source.competitor_name || '所有竞品'}</div>
          <p className="mt-2 whitespace-pre-wrap text-sm text-gray-700">{source.content || source.snippet}</p>
        </article>
      ))}
    </div>
  )
}

function SourcesTab({ sourceList }: { sourceList: SourceEvidence[] }) {
  if (sourceList.length === 0) {
    return <p className="rounded-md border border-dashed border-gray-300 bg-white px-4 py-6 text-center text-sm text-gray-500">暂无来源链接。</p>
  }
  return (
    <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-gray-900">Sources</h2>
          <p className="mt-1 text-xs text-gray-500">报告引用和采集到的全部来源链接。</p>
        </div>
        <span className="text-xs text-gray-500">{sourceList.length} 个来源</span>
      </div>
      <ol className="space-y-3">
        {sourceList.map((source, index) => (
          <li key={source.source_id} className="rounded-lg border border-gray-200 p-3">
            <div className="flex flex-wrap items-start gap-2">
              <span className="mt-0.5 rounded bg-gray-100 px-1.5 py-0.5 font-mono text-[11px] text-gray-500">
                {index + 1}
              </span>
              <div className="min-w-0 flex-1">
                <a
                  href={source.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="break-words text-sm font-semibold text-blue-700 underline hover:text-blue-800"
                >
                  {source.title || source.url}
                </a>
                <p className="mt-1 break-all font-mono text-[11px] text-gray-500">{source.url}</p>
                <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-gray-500">
                  <span>{source.competitor_name || '未标注竞品'}</span>
                  <span>{source.source_type}</span>
                  <span>{source.data_source ?? 'unknown'}</span>
                  <span>可靠性 {source.reliability}</span>
                  <span>{formatDateTime(source.retrieved_at)}</span>
                </div>
                {(source.snippet || source.content) && (
                  <p className="mt-2 line-clamp-3 text-xs leading-relaxed text-gray-600">
                    {source.snippet || source.content}
                  </p>
                )}
              </div>
            </div>
          </li>
        ))}
      </ol>
    </section>
  )
}

function StructuredSection({ data, emptyMessage }: { data: unknown; emptyMessage: string }) {
  if (!data || (typeof data === 'object' && Object.keys(data as Record<string, unknown>).length === 0)) {
    return <p className="rounded-md border border-dashed border-gray-300 bg-white px-4 py-6 text-center text-sm text-gray-500">{emptyMessage}</p>
  }
  return <div className="space-y-3">{renderStructuredValue(data)}</div>
}

function renderStructuredValue(value: unknown): ReactNode {
  if (Array.isArray(value)) {
    return value.length > 0 ? (
      <ul className="space-y-2">
        {value.map((item, index) => (
          <li key={index} className="rounded-md border border-gray-200 bg-white p-3 text-sm text-gray-700">
            {renderStructuredValue(item)}
          </li>
        ))}
      </ul>
    ) : null
  }
  if (value && typeof value === 'object') {
    return (
      <div className="space-y-3">
        {Object.entries(value as Record<string, unknown>).map(([key, child]) => (
          <section key={key} className="rounded-lg border border-gray-200 bg-white p-4">
            <h3 className="text-sm font-semibold text-gray-900">{key}</h3>
            <div className="mt-2 text-sm text-gray-700">{renderStructuredValue(child)}</div>
          </section>
        ))}
      </div>
    )
  }
  return <span>{String(value)}</span>
}

function computeDroppedCompetitors(
  requested: CompetitorInProject[],
  report: CompetitiveReport | undefined,
  traces: AgentRun[],
): DroppedCompetitor[] {
  if (!report || requested.length === 0) return []
  const analysedNames = new Set(
    (report.competitor_overview ?? []).map((c) => c.competitor_name.toLowerCase())
  )
  const dropped = requested.filter((c) => !analysedNames.has(c.name.toLowerCase()))
  if (dropped.length === 0) return []

  const collectorTrace = traces.find((t) => t.agent_name.includes('Collector'))
  const collectorOutput = (collectorTrace?.output ?? {}) as Record<string, unknown>
  const failedUrls = (collectorOutput.failed_urls as string[] | undefined) ?? []
  const coverageMap = (collectorOutput.source_coverage_by_competitor as
    Record<string, { score: number }> | undefined) ?? {}
  const dataMode = (collectorOutput.data_mode as string | undefined) ?? 'demo'

  return dropped.map((comp) => ({
    name: comp.name,
    url: comp.url,
    reason: inferDropReason(comp.name, comp.url, failedUrls, coverageMap, dataMode),
  }))
}

function inferDropReason(
  name: string,
  url: string,
  failedUrls: string[],
  coverageMap: Record<string, { score: number }>,
  dataMode: string,
): string {
  try {
    const hostname = new URL(url).hostname
    if (failedUrls.some((u) => u.includes(hostname))) return '官网失败或不可访问'
  } catch {
    // ignore invalid URL
  }

  const cov = coverageMap[name]
  if (cov !== undefined) {
    if (cov.score === 0) return '未采集到可用来源'
    if (cov.score < 40) return `来源覆盖较弱（${cov.score}/100）`
  }

  if (dataMode === 'demo') return '未找到 Demo fixture'
  return '可用于分析的来源不足'
}
