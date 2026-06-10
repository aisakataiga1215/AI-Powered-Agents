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
import { use, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

import { api } from '@/lib/api'
import type { AgentRun, CompetitorInProject, CompetitiveReport, QAResult, QATraceOutput, SourceEvidence } from '@/lib/types'
import { useSourcePanel } from '@/lib/store'
import { formatDateTime } from '@/lib/formatDateTime'

import { ClaimList } from '@/components/report-viewer/ClaimList'
import { DroppedCompetitorsList } from '@/components/report-viewer/DroppedCompetitorsList'
import type { DroppedCompetitor } from '@/components/report-viewer/DroppedCompetitorsList'
import { FeatureComparisonTable } from '@/components/report-viewer/FeatureComparisonTable'
import { InsufficientDataView } from '@/components/report-viewer/InsufficientDataView'
import { PricingComparisonTable } from '@/components/report-viewer/PricingComparisonTable'
import { SWOTView } from '@/components/report-viewer/SWOTView'
import { TabsBar, type TabItem } from '@/components/report-viewer/TabsBar'
import { QaStatusBanner } from '@/components/qa/QaStatusBanner'
import { QAResultBanner } from '@/components/qa/QAResultBanner'
import { SourcePanel } from '@/components/source-viewer/SourcePanel'

interface PageProps {
  params: Promise<{ id: string }>
}

type TabValue = 'summary' | 'pricing' | 'features' | 'swot' | 'recommendations' | 'markdown' | 'qa'

export default function ReportPage({ params }: PageProps) {
  const { id } = use(params)
  const [activeTab, setActiveTab] = useState<TabValue>('summary')

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

  const analysedCount = useMemo(() => {
    const collectorTrace = traces.find((t) => t.agent_name.includes('Collector'))
    const out = (collectorTrace?.output ?? {}) as Record<string, unknown>
    const collected = out.sufficiently_collected_competitors as string[] | undefined
    return collected?.length ?? reportQuery.data?.competitor_overview?.length ?? 0
  }, [traces, reportQuery.data])

  const tabs: TabItem[] = useMemo(() => {
    const allIssues = qaResult?.issues ?? []
    const highCount   = allIssues.filter((i) => i.severity === 'high').length
    const mediumCount = allIssues.filter((i) => i.severity === 'medium').length
    const lowCount    = allIssues.filter((i) => i.severity === 'low').length
    const baseTabs: TabItem[] = [
      { value: 'summary', label: '摘要' },
      { value: 'pricing', label: '定价' },
      { value: 'features', label: '功能' },
      { value: 'swot', label: 'SWOT' },
      { value: 'recommendations', label: '建议' },
      { value: 'markdown', label: 'Markdown' },
      {
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
      },
    ]
    return baseTabs
  }, [qaResult])

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
    citedSources === 0 || summaryLen === 0 || qaScore < 30 || analysedCount < 2
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
            <TabsBar items={tabs} value={activeTab} onChange={(v) => setActiveTab(v as TabValue)} />

        <section role="tabpanel" className="pt-2">
          {activeTab === 'summary' && (
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
          {activeTab === 'pricing' && (
            <PricingComparisonTable
              data={normalizeStringMap(report.pricing_comparison)}
              emptyMessage="暂无定价数据。"
            />
          )}
          {activeTab === 'features' && (
            <FeatureComparisonTable
              data={normalizeStringMap(report.feature_comparison)}
              emptyMessage="暂无功能数据。"
            />
          )}
          {activeTab === 'swot' && (
            <SWOTView
              swotComparison={report.swot_comparison ?? {}}
              competitorOverview={report.competitor_overview ?? []}
              sourceList={report.source_list ?? []}
            />
          )}
          {activeTab === 'recommendations' && (
            <ClaimList
              claims={report.strategic_recommendations}
              sourceList={report.source_list}
              emptyMessage="暂无战略建议。"
            />
          )}
          {activeTab === 'markdown' && (
            <MarkdownTab markdown={report.markdown_content} sourceList={report.source_list} />
          )}
          {activeTab === 'qa' && (
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
