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
import PurposeSections from '@/components/report-viewer/PurposeSections'
import ScoringMatrix from '@/components/report-viewer/ScoringMatrix'
import MarketBackground from '@/components/report-viewer/MarketBackground'
import FeatureInsights from '@/components/report-viewer/FeatureInsights'
import OperationMonetization from '@/components/report-viewer/OperationMonetization'
import { SWOTView } from '@/components/report-viewer/SWOTView'
import { TabsBar, type TabItem } from '@/components/report-viewer/TabsBar'
import { QaStatusBanner } from '@/components/qa/QaStatusBanner'
import { QAResultBanner } from '@/components/qa/QAResultBanner'
import { SourcePanel } from '@/components/source-viewer/SourcePanel'

interface PageProps {
  params: Promise<{ id: string }>
}

type TabValue = 'summary' | 'pricing' | 'features' | 'market' | 'swot' | 'recommendations' | 'markdown' | 'qa' | 'purpose'

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
  const requestedCompetitors = projectQuery.data?.competitors ?? []

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
    const blockingCount = allIssues.filter((i) => i.severity !== 'low').length
    const advisoryCount = allIssues.filter((i) => i.severity === 'low').length
    const purpose = reportQuery.data?.analysis_purpose
    const purposeTab: TabItem | null =
      purpose && purpose !== 'general'
        ? { value: 'purpose', label: purpose === 'build_product' ? 'Build Insights' : 'Decision Guide' }
        : null
    const baseTabs: TabItem[] = [
      { value: 'summary', label: 'Summary' },
      { value: 'pricing', label: 'Pricing' },
      { value: 'features', label: 'Features' },
      { value: 'market', label: 'Market & Ops' },
      { value: 'swot', label: 'SWOT' },
      { value: 'recommendations', label: 'Recommendations' },
      { value: 'markdown', label: 'Markdown' },
      {
        value: 'qa',
        label: 'QA Result',
        badge:
          qaResult && !qaResult.passed ? (
            <span className="rounded-full bg-red-100 px-1.5 py-0.5 text-[10px] font-semibold text-red-700">
              {blockingCount}
            </span>
          ) : qaResult?.passed && advisoryCount > 0 ? (
            <span className="rounded-full bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold text-amber-700">
              {advisoryCount} adv
            </span>
          ) : qaResult?.passed ? (
            <span className="rounded-full bg-green-100 px-1.5 py-0.5 text-[10px] font-semibold text-green-700">
              ok
            </span>
          ) : null,
      },
    ]
    if (purposeTab) baseTabs.splice(6, 0, purposeTab)
    return baseTabs
  }, [qaResult, reportQuery.data?.analysis_purpose])

  if (reportQuery.isLoading) {
    return <ReportSkeleton id={id} />
  }

  if (reportQuery.isError) {
    return (
      <div className="space-y-4">
        <Breadcrumb id={id} />
        <div className="rounded-md border border-red-200 bg-red-50 p-6 text-sm text-red-700">
          Failed to load report.{' '}
          {reportQuery.error instanceof Error ? reportQuery.error.message : 'Unknown error.'} The
          workflow may not have produced one yet.
        </div>
        <Link
          href={`/projects/${id}`}
          className="rounded-md border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
        >
          &larr; Back to project
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
          <span className="font-semibold">⚠ Fallback mode: </span>
          Report generated without a successful LLM call. Executive summary and strategic
          recommendations may be incomplete or generic.
        </div>
      )}

      {projectStatus && projectStatus !== 'completed' && projectStatus !== 'running' && projectStatus !== 'created' && (
        <QaStatusBanner status={projectStatus} droppedCount={droppedCompetitors.length} />
      )}

      <header className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <p className="text-xs font-medium tracking-wider text-blue-700 uppercase print:hidden">
          Competitive analysis
        </p>
        <h1 className="mt-1 text-2xl font-semibold text-gray-900">{report.title}</h1>
        <p className="mt-2 text-xs text-gray-500">
          Generated {formatDateTime(report.created_at)} · Project {report.project_id}
        </p>
        <div className="mt-3 flex flex-wrap gap-3 text-xs text-gray-600">
          {droppedCompetitors.length > 0 ? (
            <span className="text-orange-600">
              {report.competitor_overview?.length ?? 0} of {requestedCompetitors.length} analysed
              ({droppedCompetitors.length} dropped)
            </span>
          ) : (
            <span>{report.competitor_overview?.length ?? 0} competitors</span>
          )}
          <SourceCountChip sourceList={report.source_list ?? []} />
          <span>{report.executive_summary?.length ?? 0} summary claims</span>
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
                emptyMessage="No executive summary available."
              />
            </>
          )}
          {activeTab === 'pricing' && (
            <PricingComparisonTable
              data={normalizeStringMap(report.pricing_comparison)}
              emptyMessage="No pricing data."
            />
          )}
          {activeTab === 'features' && (
            <FeatureComparisonTable
              data={normalizeStringMap(report.feature_comparison)}
              emptyMessage="No feature data."
            />
          )}
          {activeTab === 'market' && (
            <div className="space-y-8">
              {report.market_background && (
                <MarketBackground data={report.market_background} />
              )}
              {report.feature_insights && (
                <FeatureInsights data={report.feature_insights} />
              )}
              {report.operation_monetization && (
                <OperationMonetization data={report.operation_monetization} />
              )}
              {!report.market_background && !report.feature_insights && !report.operation_monetization && (
                <p className="text-sm text-gray-400 italic">PM-framework sections not available for this report.</p>
              )}
            </div>
          )}
          {activeTab === 'swot' && (
            <SWOTView
              swotComparison={report.swot_comparison ?? {}}
              competitorOverview={report.competitor_overview ?? []}
            />
          )}
          {activeTab === 'recommendations' && (
            <ClaimList
              claims={report.strategic_recommendations}
              sourceList={report.source_list}
              emptyMessage="No strategic recommendations available."
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
                  QA result not available yet.
                </p>
              )}
              {droppedCompetitors.length > 0 && (
                <DroppedCompetitorsList dropped={droppedCompetitors} className="mt-4" />
              )}
            </>
          )}
          {activeTab === 'purpose' && report.analysis_purpose && report.analysis_purpose !== 'general' && (
            <div className="space-y-8">
              <ScoringMatrix
                analysisPurpose={report.analysis_purpose}
                competitorScores={report.competitor_scores}
                opportunityScore={report.opportunity_score}
              />
              <PurposeSections
                analysisPurpose={report.analysis_purpose}
                purposeSections={report.purpose_sections ?? {}}
              />
              {report.custom_dimension_analysis && Object.keys(report.custom_dimension_analysis).length > 0 && (
                <CustomDimensionTable analysis={report.custom_dimension_analysis} />
              )}
            </div>
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
          &larr; Back to project
        </Link>
        <Link
          href={`/projects/${id}/traces`}
          className="rounded-md border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
        >
          View Agent traces
        </Link>
        <button
          type="button"
          onClick={() => exportMarkdown(report.markdown_content, report.title, report.source_list ?? [])}
          className="rounded-md border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
        >
          Export MD
        </button>
        <Link
          href={`/projects/${id}/print`}
          target="_blank"
          rel="noopener noreferrer"
          className="rounded-md border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
        >
          {projectStatus === 'qa_failed' ? 'Export Partial PDF' : 'Export PDF'}
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

  if (!hasDataSource) return <span>{total} sources cited</span>
  if (liveCount === 0 && searchCount === 0) return <span>{total} sources cited (demo)</span>

  const parts: string[] = []
  if (liveCount > 0) parts.push(`${liveCount} live`)
  if (searchCount > 0) parts.push(`${searchCount} search`)
  if (demoCount > 0) parts.push(`${demoCount} demo`)
  return <span>{total} sources cited · {parts.join(' · ')}</span>
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
          <p className="text-sm text-gray-500">No markdown content.</p>
        )}
      </div>
      <hr className="my-6 border-gray-200" />
      <h2 className="mb-3 text-base font-semibold text-gray-900">Sources</h2>
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
                  {s.competitor_name} · {s.source_type} · retrieved {formatDateTime(s.retrieved_at)}
                </div>
              </div>
            </li>
          ))}
        </ol>
      ) : (
        <p className="text-sm text-gray-500">No sources listed.</p>
      )}
    </article>
  )
}

function Breadcrumb({ id, title }: { id: string; title?: string }) {
  return (
    <nav className="text-sm text-gray-500">
      <Link href="/projects" className="hover:text-gray-900">
        Projects
      </Link>
      <span className="mx-1">/</span>
      <Link href={`/projects/${id}`} className="hover:text-gray-900">
        {id}
      </Link>
      <span className="mx-1">/</span>
      <span className="text-gray-900">{title ?? 'Report'}</span>
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

function CustomDimensionTable({ analysis }: { analysis: Record<string, Record<string, unknown>> }) {
  return (
    <div className="space-y-4">
      <h3 className="text-base font-semibold text-gray-900">Custom Dimension Analysis</h3>
      {Object.entries(analysis).map(([dim, compData]) => (
        <div key={dim} className="overflow-x-auto rounded-lg border border-gray-200">
          <div className="border-b border-gray-200 bg-gray-50 px-4 py-2 text-sm font-medium text-gray-700 capitalize">
            {dim.replace(/_/g, ' ')}
          </div>
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-gray-100">
                <th className="px-3 py-2 text-left font-medium text-gray-500">Competitor</th>
                <th className="px-3 py-2 text-center font-medium text-gray-500">Score</th>
                <th className="px-3 py-2 text-left font-medium text-gray-500">Rationale</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(compData).map(([name, val]) => {
                const cell = val as { score?: number | string; rationale?: string } | undefined
                return (
                  <tr key={name} className="border-b border-gray-100 last:border-0">
                    <td className="px-3 py-2 font-medium text-gray-700">{name}</td>
                    <td className="px-3 py-2 text-center text-gray-600">{cell?.score ?? '—'}</td>
                    <td className="px-3 py-2 text-gray-600">{cell?.rationale ?? ''}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      ))}
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
    if (failedUrls.some((u) => u.includes(hostname))) return 'Homepage failed or unreachable'
  } catch {
    // ignore invalid URL
  }

  const cov = coverageMap[name]
  if (cov !== undefined) {
    if (cov.score === 0) return 'No usable sources collected'
    if (cov.score < 40) return `Weak coverage (score ${cov.score}/100)`
  }

  if (dataMode === 'demo') return 'No demo fixture found'
  return 'Insufficient sources for analysis'
}
