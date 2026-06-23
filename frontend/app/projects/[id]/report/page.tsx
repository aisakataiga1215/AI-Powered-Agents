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

import { api, apiAssetUrl } from '@/lib/api'
import type { AgentRun, Claim, CompetitorInProject, CompetitiveReport, CompetitorKnowledge, CompetitorScore, DimensionScore, OpportunityScore, QAResult, QATraceOutput, SourceEvidence } from '@/lib/types'
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
      report?.custom_dimension_analysis,
      report?.analysis_purpose,
      report?.competitor_scores,
      report
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

  const report = sanitizeReportForDisplay(reportQuery.data!)

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
            <CustomDimensionTab
              dimension={currentTab.slice('custom_dimension:'.length)}
              analysis={report.custom_dimension_analysis?.[currentTab.slice('custom_dimension:'.length)]}
              detail={report.custom_dimension_sections?.[currentTab.slice('custom_dimension:'.length)]}
              sourceList={report.source_list ?? []}
            />
          )}
          {currentTab === 'scoring' && (
            <ScoringMatrix
              competitorScores={report.competitor_scores}
              purposeSections={report.purpose_sections}
            />
          )}
          {currentTab === 'opportunity' && (
            <OpportunityTab
              opportunityScore={report.opportunity_score}
              purposeSections={report.purpose_sections}
            />
          )}
          {currentTab === 'pm_sections' && (
            <PMSectionsTab
              marketBackground={report.market_background}
              featureInsights={report.feature_insights}
              operationMonetization={report.operation_monetization}
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
  const [features, setFeatures] = useState(recordToEditableLines(report.feature_comparison ?? {}))
  const [pricing, setPricing] = useState(recordToEditableLines(report.pricing_comparison ?? {}))
  const [personas, setPersonas] = useState(readableObjectText(report.user_persona_comparison ?? {}))
  const [swot, setSwot] = useState(readableObjectText(report.swot_comparison ?? {}))
  const [frameworks, setFrameworks] = useState(readableObjectText(report.framework_sections ?? {}))
  const [customDimensions, setCustomDimensions] = useState(readableObjectText(report.custom_dimension_sections ?? {}))
  const [purposeSections, setPurposeSections] = useState(readableObjectText(report.purpose_sections ?? {}))
  const [rationale, setRationale] = useState(recordToEditableLines(report.competitor_selection_rationale ?? {}))
  const [advancedFields, setAdvancedFields] = useState(toPrettyJson({
    competitor_overview: report.competitor_overview ?? [],
    custom_dimension_analysis: report.custom_dimension_analysis ?? {},
    competitor_scores: report.competitor_scores ?? {},
    opportunity_score: report.opportunity_score ?? null,
    market_background: report.market_background ?? null,
    feature_insights: report.feature_insights ?? null,
    operation_monetization: report.operation_monetization ?? null,
  }))
  const [parseError, setParseError] = useState<string | null>(null)
  const markdownPreview = useMemo(
    () =>
      buildCorrectionMarkdownPreview({
        title,
        objective,
        summary,
        recommendations,
        features,
        pricing,
        personas,
        swot,
        frameworks,
        customDimensions,
        purposeSections,
        rationale,
      }),
    [
      title,
      objective,
      summary,
      recommendations,
      features,
      pricing,
      personas,
      swot,
      frameworks,
      customDimensions,
      purposeSections,
      rationale,
    ]
  )

  const save = () => {
    try {
      setParseError(null)
      const advanced = parseJsonField<Record<string, unknown>>(advancedFields, '高级结构化字段')
      onSave({
        title,
        analysis_objective: objective,
        executive_summary: mergeClaimLines(report.executive_summary, summary),
        strategic_recommendations: mergeClaimLines(report.strategic_recommendations, recommendations),
        feature_comparison: editableLinesToRecord(features),
        pricing_comparison: editableLinesToRecord(pricing),
        user_persona_comparison: editableTextToObject(personas, report.user_persona_comparison ?? {}),
        swot_comparison: editableTextToObject(swot, report.swot_comparison ?? {}),
        framework_sections: editableTextToObject(frameworks, report.framework_sections ?? {}),
        custom_dimension_sections: editableTextToObject(customDimensions, report.custom_dimension_sections ?? {}),
        purpose_sections: editableTextToObject(purposeSections, report.purpose_sections ?? {}),
        competitor_selection_rationale: editableLinesToRecord(rationale),
        competitor_overview: (advanced.competitor_overview ?? report.competitor_overview) as CompetitorKnowledge[],
        custom_dimension_analysis: (advanced.custom_dimension_analysis ?? report.custom_dimension_analysis ?? {}) as Record<string, DimensionScore>,
        competitor_scores: (advanced.competitor_scores ?? report.competitor_scores ?? {}) as Record<string, CompetitorScore>,
        opportunity_score: (advanced.opportunity_score ?? report.opportunity_score ?? null) as OpportunityScore | null,
        market_background: (advanced.market_background ?? report.market_background ?? null) as Record<string, unknown> | null,
        feature_insights: (advanced.feature_insights ?? report.feature_insights ?? null) as Record<string, unknown> | null,
        operation_monetization: (advanced.operation_monetization ?? report.operation_monetization ?? null) as Record<string, unknown> | null,
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
        <EditableKeyValueBlock label="功能对比" value={features} onChange={setFeatures} />
        <EditableKeyValueBlock label="定价模式" value={pricing} onChange={setPricing} />
        <EditableTextBlock label="用户画像" value={personas} onChange={setPersonas} rows={6} />
        <EditableTextBlock label="SWOT" value={swot} onChange={setSwot} rows={6} />
        <EditableTextBlock label="分析框架" value={frameworks} onChange={setFrameworks} rows={6} />
        <EditableTextBlock label="自定义维度" value={customDimensions} onChange={setCustomDimensions} rows={6} />
        <EditableTextBlock label="目的相关建议" value={purposeSections} onChange={setPurposeSections} rows={6} />
        <EditableKeyValueBlock label="竞品选择说明" value={rationale} onChange={setRationale} />
        <details className="rounded-md border border-gray-200 bg-gray-50 p-3">
          <summary className="cursor-pointer text-sm font-medium text-gray-700">高级结构化字段</summary>
          <p className="mt-2 text-xs text-gray-500">
            这里保留给需要精细修改评分、机会分和原始竞品画像的高级用户；普通修正不用展开。
          </p>
          <EditableJsonBlock label="高级字段" value={advancedFields} onChange={setAdvancedFields} rows={12} />
        </details>
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
  rows = 4,
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
        className="rounded-md border border-gray-300 px-3 py-2 text-sm leading-relaxed outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
      />
      <span className="text-xs text-gray-500">每行一条，保存时会保留原有引用和置信度。</span>
    </label>
  )
}

function EditableKeyValueBlock({
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
        rows={5}
        className="rounded-md border border-gray-300 px-3 py-2 text-sm leading-relaxed outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
      />
      <span className="text-xs text-gray-500">格式：每行一个条目，例如 Cursor：适合重度 AI 编码用户。</span>
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
  return (claims ?? []).map((claim) => cleanDisplayText(claim.text)).join('\n')
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
  return JSON.stringify(value === undefined ? {} : value, null, 2)
}

function recordToEditableLines(value: Record<string, unknown>): string {
  return Object.entries(value ?? {})
    .map(([key, item]) => `${key}: ${typeof item === 'string' ? item : readableObjectText(item)}`)
    .join('\n')
}

function editableLinesToRecord(value: string): Record<string, string> {
  const result: Record<string, string> = {}
  value
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .forEach((line, index) => {
      const colonIndex = line.search(/[:：]/)
      if (colonIndex > 0) {
        const key = line.slice(0, colonIndex).trim()
        const text = line.slice(colonIndex + 1).trim()
        if (key && text) result[key] = text
      } else {
        result[`修正 ${index + 1}`] = line
      }
    })
  return result
}

function readableObjectText(value: unknown): string {
  if (value == null) return ''
  if (typeof value === 'string') return cleanDisplayText(value)
  if (Array.isArray(value)) {
    return value
      .map((item) => {
        if (typeof item === 'string') return cleanDisplayText(item)
        if (item && typeof item === 'object' && 'text' in item) {
          return cleanDisplayText(String((item as Record<string, unknown>).text ?? ''))
        }
        return readableObjectText(item)
      })
      .filter(Boolean)
      .join('\n')
  }
  if (typeof value === 'object') {
    return Object.entries(value as Record<string, unknown>)
      .map(([key, item]) => {
        const text = readableObjectText(item)
        return text ? `${key}: ${text}` : key
      })
      .join('\n')
  }
  return String(value)
}

function editableTextToObject(value: string, existing: Record<string, unknown>): Record<string, unknown> {
  const text = value.trim()
  if (!text) return {}
  if (text === readableObjectText(existing).trim()) return existing
  return editableLinesToRecord(text)
}

function parseJsonField<T>(value: string, label: string): T {
  try {
    return JSON.parse(value) as T
  } catch {
    throw new Error(`${label} 的 JSON 格式不正确。`)
  }
}

function cleanDisplayText(value: string | undefined | null): string {
  let text = String(value ?? '').trim()
  if (!text) return ''
  const markers = [text.indexOf('<parameter'), text.indexOf('</parameter')].filter((idx) => idx >= 0)
  if (markers.length > 0) {
    text = text.slice(0, Math.min(...markers))
  }
  return text.replace(/<\/?parameter[^>]*>/gi, '').trim()
}

function redactDisplayPii(value: string): string {
  return value
    .replace(/mailto:[^\s>]+/gi, '[REDACTED:mailto]')
    .replace(/(?<![\w.+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g, '[REDACTED:email]')
    .replace(/(?<!\d)(?:\d{17}[\dXx])(?!\d)/g, '[REDACTED:id]')
    .replace(/(?:\+?86[-\s]?|0086[-\s]?)?1[3-9](?:[-\s]?\d){9}/g, '[REDACTED:phone]')
    .replace(/(?<![\w.])\+\d{1,3}[\s.-]?\(?\d{1,4}\)?[\s.-]?\d{2,4}[\s.-]?\d{2,4}(?:[\s.-]?\d{2,4})?(?![\w.])/g, '[REDACTED:phone]')
    .replace(/[\u4e00-\u9fa5]{2,3}(?=(?:先生|女士|小姐|总监|经理|主管|总经理|总裁|老师|博士))/g, '[REDACTED:name]')
}

function extractEmbeddedRationale(value: string | undefined | null): Record<string, string> {
  const text = String(value ?? '')
  const match = text.match(/<parameter\s+name=["']competitor_selection_rationale["'][^>]*>(\{[\s\S]*?\})(?:\s*<\/parameter>)?/i)
  if (!match) return {}
  try {
    const parsed = JSON.parse(match[1]) as Record<string, unknown>
    return Object.fromEntries(
      Object.entries(parsed)
        .filter(([key, item]) => key.trim() && String(item ?? '').trim())
        .map(([key, item]) => [key, String(item)])
    )
  } catch {
    return {}
  }
}

function sanitizeReportForDisplay(report: CompetitiveReport): CompetitiveReport {
  const embeddedRationale = extractEmbeddedRationale(report.analysis_objective)
  const currentRationale = report.competitor_selection_rationale ?? {}
  return {
    ...report,
    title: cleanDisplayText(report.title) || 'Competitive Analysis Report',
    analysis_objective: cleanDisplayText(report.analysis_objective),
    competitor_selection_rationale:
      Object.keys(currentRationale).length > 0 ? currentRationale : embeddedRationale,
    executive_summary: (report.executive_summary ?? []).map((claim) => ({
      ...claim,
      text: cleanDisplayText(claim.text),
    })).filter((claim) => claim.text),
    strategic_recommendations: (report.strategic_recommendations ?? []).map((claim) => ({
      ...claim,
      text: cleanDisplayText(claim.text),
    })).filter((claim) => claim.text),
    markdown_content: rebuildMarkdownFromDisplayReport(report, Object.keys(currentRationale).length > 0 ? currentRationale : embeddedRationale),
  }
}

function rebuildMarkdownFromDisplayReport(report: CompetitiveReport, rationale?: Record<string, string>): string {
  const title = cleanDisplayText(report.title) || 'Competitive Analysis Report'
  const lines = [`# ${title}`, '']
  appendTextSection(lines, 'Analysis Objective', cleanDisplayText(report.analysis_objective))
  appendLineListSection(lines, 'Executive Summary', claimsToLines(report.executive_summary))
  appendPreviewSection(lines, 'Feature Comparison', recordToEditableLines(report.feature_comparison ?? {}))
  appendPreviewSection(lines, 'Pricing Comparison', recordToEditableLines(report.pricing_comparison ?? {}))
  appendPreviewSection(lines, 'User Personas', readableObjectText(report.user_persona_comparison ?? {}))
  appendPreviewSection(lines, 'SWOT', readableObjectText(report.swot_comparison ?? {}))
  appendPreviewSection(lines, 'Analysis Frameworks', readableObjectText(report.framework_sections ?? {}))
  appendPreviewSection(lines, 'Purpose Guidance', readableObjectText(report.purpose_sections ?? {}))
  appendPreviewSection(lines, 'Competitor Selection Rationale', recordToEditableLines(rationale ?? report.competitor_selection_rationale ?? {}))
  appendLineListSection(lines, 'Strategic Recommendations', claimsToLines(report.strategic_recommendations))
  return lines.join('\n').trim()
}

function buildCorrectionMarkdownPreview({
  title,
  objective,
  summary,
  recommendations,
  features,
  pricing,
  personas,
  swot,
  frameworks,
  customDimensions,
  purposeSections,
  rationale,
}: {
  title: string
  objective: string
  summary: string
  recommendations: string
  features: string
  pricing: string
  personas: string
  swot: string
  frameworks: string
  customDimensions: string
  purposeSections: string
  rationale: string
}): string {
  const lines = [`# ${title || 'Competitive Analysis Report'}`, '']
  appendTextSection(lines, 'Analysis Objective', objective)
  appendLineListSection(lines, 'Executive Summary', summary)
  appendPreviewSection(lines, 'Feature Comparison', features)
  appendPreviewSection(lines, 'Pricing Comparison', pricing)
  appendPreviewSection(lines, 'User Personas', personas)
  appendPreviewSection(lines, 'SWOT', swot)
  appendPreviewSection(lines, 'Analysis Frameworks', frameworks)
  appendPreviewSection(lines, 'Custom Dimension Details', customDimensions)
  appendPreviewSection(lines, 'Purpose Guidance', purposeSections)
  appendPreviewSection(lines, 'Competitor Selection Rationale', rationale)
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

function appendPreviewSection(lines: string[], title: string, value: string) {
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
  customDimensionAnalysis?: Record<string, unknown>,
  analysisPurpose?: string,
  competitorScores?: Record<string, unknown>,
  report?: CompetitiveReport
): string[] {
  let next = [...tabs]
  const customDimensionNames = new Set([
    ...Object.keys(customDimensionSections ?? {}),
    ...Object.keys(customDimensionAnalysis ?? {}),
  ])
  for (const dim of customDimensionNames) {
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
  const hasOpportunityData =
    analysisPurpose === 'build_product' ||
    Boolean(report?.opportunity_score)
  if (!next.includes('opportunity') && hasOpportunityData) {
    const recommendationsIndex = next.indexOf('recommendations')
    const insertAt = recommendationsIndex !== -1 ? recommendationsIndex : next.length
    next = [...next.slice(0, insertAt), 'opportunity', ...next.slice(insertAt)]
  }
  const hasPmData =
    analysisPurpose === 'understand_industry' ||
    analysisPurpose === 'analyze_growth_ops' ||
    Boolean(report?.market_background || report?.feature_insights || report?.operation_monetization)
  if (!next.includes('pm_sections') && hasPmData) {
    const recommendationsIndex = next.indexOf('recommendations')
    const insertAt = recommendationsIndex !== -1 ? recommendationsIndex : next.length
    next = [...next.slice(0, insertAt), 'pm_sections', ...next.slice(insertAt)]
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
  if (value === 'opportunity') return '机会'
  if (value === 'pm_sections') return 'PM 报告'
  if (value === 'recommendations') return '建议'
  if (value === 'sources') return 'Sources'
  if (value.startsWith('custom_dimension:')) return value.slice('custom_dimension:'.length)
  return value
}

function OpportunityTab({
  opportunityScore,
  purposeSections,
}: {
  opportunityScore?: OpportunityScore | null
  purposeSections?: Record<string, unknown>
}) {
  if (!opportunityScore) {
    return <p className="rounded-md border border-dashed border-gray-300 bg-white px-4 py-6 text-center text-sm text-gray-500">暂无机会评分。</p>
  }
  return (
    <div className="space-y-4">
      <section className="rounded-lg border border-gray-200 bg-white p-4">
        <div className="flex flex-wrap items-end justify-between gap-2">
          <div>
            <h2 className="text-base font-semibold text-gray-900">OpportunityScore</h2>
            <p className="mt-1 text-xs text-gray-500">{opportunityScore.scoring_note}</p>
          </div>
          <span className="rounded bg-blue-50 px-2 py-1 text-sm font-bold text-blue-700">
            {opportunityScore.overall_score.toFixed(1)}
          </span>
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          {opportunityScore.dimensions.map((dimension) => (
            <DimensionScoreCard key={dimension.dimension_name} dimension={dimension} />
          ))}
        </div>
      </section>
      <StructuredSection data={purposeSections} emptyMessage="暂无机会建议。" />
    </div>
  )
}

function PMSectionsTab({
  marketBackground,
  featureInsights,
  operationMonetization,
}: {
  marketBackground?: Record<string, unknown> | null
  featureInsights?: Record<string, unknown> | null
  operationMonetization?: Record<string, unknown> | null
}) {
  if (!marketBackground && !featureInsights && !operationMonetization) {
    return <p className="rounded-md border border-dashed border-gray-300 bg-white px-4 py-6 text-center text-sm text-gray-500">暂无 PM 报告内容。</p>
  }
  return (
    <div className="space-y-4">
      <StructuredCard title="市场背景" data={marketBackground} />
      <StructuredCard title="功能洞察" data={featureInsights} />
      <StructuredCard title="运营与商业化" data={operationMonetization} />
    </div>
  )
}

function CustomDimensionTab({
  dimension,
  analysis,
  detail,
  sourceList,
}: {
  dimension: string
  analysis?: DimensionScore
  detail?: unknown
  sourceList: SourceEvidence[]
}) {
  if (!analysis && !detail) {
    return <p className="rounded-md border border-dashed border-gray-300 bg-white px-4 py-6 text-center text-sm text-gray-500">暂无足够证据。</p>
  }
  return (
    <div className="space-y-4">
      {analysis && (
        <section className="rounded-lg border border-gray-200 bg-white p-4">
          <h2 className="text-base font-semibold text-gray-900">{dimension}</h2>
          <div className="mt-3">
            <DimensionScoreCard dimension={analysis} sourceList={sourceList} />
          </div>
        </section>
      )}
      <CustomDimensionDetail data={detail} sourceList={sourceList} />
    </div>
  )
}

function DimensionScoreCard({ dimension, sourceList = [] }: { dimension: DimensionScore; sourceList?: SourceEvidence[] }) {
  const openSource = useSourcePanel((s) => s.openSource)
  const sourceIndex = new Map(sourceList.map((s, i) => [s.source_id, i + 1]))
  return (
    <div className="rounded-md border border-gray-200 bg-gray-50 p-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-gray-900">{dimension.dimension_name}</h3>
        <span className="rounded bg-white px-2 py-1 text-xs font-bold text-gray-700">
          {dimension.score}/5
        </span>
      </div>
      <p className="mt-2 text-sm text-gray-600">{dimension.rationale}</p>
      <div className="mt-2 flex flex-wrap gap-2 text-xs text-gray-500">
        {dimension.weight != null && <span>权重 {Math.round(dimension.weight * 100)}%</span>}
        <span>置信度 {confidenceLabel(dimension.source_confidence)}</span>
        {dimension.evidence?.length > 0 && (
          <SourceBadgeList evidence={dimension.evidence} sourceIndex={sourceIndex} onOpen={openSource} />
        )}
      </div>
    </div>
  )
}

function CustomDimensionDetail({ data, sourceList }: { data: unknown; sourceList: SourceEvidence[] }) {
  const openSource = useSourcePanel((s) => s.openSource)
  const sourceIndex = new Map(sourceList.map((s, i) => [s.source_id, i + 1]))
  if (!Array.isArray(data) || data.length === 0) {
    return <StructuredSection data={data} emptyMessage="暂无维度明细。" />
  }
  return (
    <div className="space-y-3">
      {data.map((item, index) => {
        const record = isRecord(item) ? item : {}
        const competitor = String(record.competitor_name ?? record.competitor ?? `条目 ${index + 1}`)
        const summary = String(record.summary ?? record.rationale ?? record.text ?? '')
        const confidence = typeof record.confidence === 'string' ? record.confidence : undefined
        const evidence = Array.isArray(record.evidence)
          ? record.evidence.map((value) => String(value)).filter(Boolean)
          : []
        return (
          <article key={`${competitor}-${index}`} className="rounded-lg border border-gray-200 bg-white p-4">
            <h3 className="text-sm font-semibold text-gray-900">{competitor}</h3>
            <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-gray-700">
              {summary || '暂无维度摘要。'}
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-gray-500">
              {confidence && <span>置信度 {confidenceLabel(confidence)}</span>}
              <SourceBadgeList evidence={evidence} sourceIndex={sourceIndex} onOpen={openSource} />
            </div>
          </article>
        )
      })}
    </div>
  )
}

function SourceBadgeList({
  evidence,
  sourceIndex,
  onOpen,
}: {
  evidence?: string[]
  sourceIndex: Map<string, number>
  onOpen: (sourceId: string) => void
}) {
  const ids = evidence ?? []
  if (ids.length === 0) return null
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      <span>证据</span>
      {ids.map((srcId) => {
        const num = sourceIndex.get(srcId)
        return (
          <button
            key={srcId}
            type="button"
            onClick={() => onOpen(srcId)}
            title={srcId}
            className="rounded border border-blue-200 bg-blue-50 px-1.5 py-0.5 font-mono text-[11px] font-semibold text-blue-700 transition-colors hover:bg-blue-100"
          >
            {num !== undefined ? `[${num}]` : srcId}
          </button>
        )
      })}
    </span>
  )
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function StructuredCard({ title, data }: { title: string; data?: unknown }) {
  if (!data) return null
  return (
    <section className="rounded-lg border border-gray-200 bg-white p-4">
      <h2 className="mb-3 text-base font-semibold text-gray-900">{title}</h2>
      <StructuredSection data={data} emptyMessage="暂无内容。" />
    </section>
  )
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
  const reviews = collectManualReviewSources(sourceList)
  if (reviews.length === 0) {
    return <p className="rounded-md border border-dashed border-gray-300 bg-white px-4 py-6 text-center text-sm text-gray-500">暂无研究输入。</p>
  }
  return (
    <div className="space-y-3">
      {reviews.map((review) => (
        <article key={review.key} className="rounded-lg border border-gray-200 bg-white p-4">
          <div className="flex flex-wrap items-center gap-2">
            <div className="text-sm font-semibold text-gray-900">{review.title || '研究输入'}</div>
            {review.desensitized && (
              <span className="rounded bg-green-50 px-2 py-0.5 text-[11px] font-medium text-green-700">
                已脱敏
              </span>
            )}
          </div>
          <div className="mt-1 text-xs text-gray-500">
            适用竞品：{review.competitorNames.length > 0 ? review.competitorNames.join('、') : '所有竞品'}
          </div>
          <p className="mt-2 whitespace-pre-wrap text-sm text-gray-700">{review.content}</p>
        </article>
      ))}
    </div>
  )
}

type ManualReviewSource = {
  key: string
  title: string
  content: string
  competitorNames: string[]
  desensitized: boolean
}

function collectManualReviewSources(sourceList: SourceEvidence[]): ManualReviewSource[] {
  const grouped = new Map<string, ManualReviewSource>()
  for (const source of sourceList) {
    if (!(source.data_source === 'manual' || String(source.source_type).includes('manual'))) {
      continue
    }
    const content = redactDisplayPii(stripResearchTypePrefix(source.content || source.snippet || ''))
    if (!content.trim()) continue
    const key = source.url?.startsWith('manual://')
      ? source.url
      : `${source.title || '研究输入'}::${content.replace(/\s+/g, ' ').trim().slice(0, 160)}`
    const existing = grouped.get(key)
    if (existing) {
      if (source.competitor_name && !existing.competitorNames.includes(source.competitor_name)) {
        existing.competitorNames.push(source.competitor_name)
      }
      existing.desensitized = existing.desensitized || Boolean(source.desensitized || source.contains_pii)
      continue
    }
    grouped.set(key, {
      key,
      title: source.title || '研究输入',
      content,
      competitorNames: source.competitor_name ? [source.competitor_name] : [],
      desensitized: Boolean(source.desensitized || source.contains_pii),
    })
  }
  return Array.from(grouped.values()).map((item) => ({
    ...item,
    competitorNames: item.competitorNames.sort((a, b) => a.localeCompare(b)),
  }))
}

function stripResearchTypePrefix(content: string): string {
  return content.replace(/^Research type:\s*[^\n]+\n\n/i, '').trim()
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
            <div className="flex flex-wrap items-start gap-3">
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
              {source.screenshot_url && (
                <a
                  href={apiAssetUrl(source.screenshot_url)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block w-28 shrink-0 overflow-hidden rounded-md border border-gray-200 bg-gray-50"
                  title="打开截图证据"
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={apiAssetUrl(source.screenshot_url)}
                    alt={`${source.title || source.url} 页面截图`}
                    className="h-16 w-full object-cover object-top"
                  />
                </a>
              )}
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
            <h3 className="text-sm font-semibold text-gray-900">{structuredLabel(key)}</h3>
            <div className="mt-2 text-sm text-gray-700">{renderStructuredValue(child)}</div>
          </section>
        ))}
      </div>
    )
  }
  return <span>{String(value)}</span>
}

function structuredLabel(key: string): string {
  const labels: Record<string, string> = {
    opportunity_summary: '机会概览',
    overall_score: '综合分',
    summary: '摘要',
    market_gaps: '市场缺口',
    features_to_learn_from: '可借鉴功能',
    competitor_name: '竞品',
    features: '功能',
    pitfalls_to_avoid: '需要规避的问题',
    mvp_direction: 'MVP 方向',
    best_for: '适合谁',
    who_should_avoid: '哪些人不建议选',
    recommendation_ranking: '推荐排序',
    decision_matrix: '决策矩阵',
    pm_report: 'PM 报告',
    market_overview: '市场概览',
    segment_map: '用户 / 场景分层',
    table_stakes: '基础能力',
    differentiators: '差异化能力',
    gtm_profiles: '渠道与定位',
    monetization_patterns: '商业化模式',
    growth_loops: '增长路径',
  }
  return labels[key] ?? key
}

function confidenceLabel(value: string | undefined): string {
  if (value === 'high') return '高'
  if (value === 'medium') return '中'
  if (value === 'low') return '低'
  return '未知'
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
