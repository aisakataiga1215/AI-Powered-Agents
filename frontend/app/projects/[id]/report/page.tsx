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
import type { AgentRun, QAResult, SourceEvidence } from '@/lib/types'
import { useSourcePanel } from '@/lib/store'
import { formatDateTime } from '@/lib/formatDateTime'

import { ClaimList } from '@/components/report-viewer/ClaimList'
import { FeatureComparisonTable } from '@/components/report-viewer/FeatureComparisonTable'
import { PricingComparisonTable } from '@/components/report-viewer/PricingComparisonTable'
import { SWOTView } from '@/components/report-viewer/SWOTView'
import { TabsBar, type TabItem } from '@/components/report-viewer/TabsBar'
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

  const traces = useMemo(() => tracesQuery.data?.traces ?? [], [tracesQuery.data])

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

  const tabs: TabItem[] = useMemo(() => {
    const issuesCount = qaResult?.issues?.length ?? 0
    return [
      { value: 'summary', label: 'Summary' },
      { value: 'pricing', label: 'Pricing' },
      { value: 'features', label: 'Features' },
      { value: 'swot', label: 'SWOT' },
      { value: 'recommendations', label: 'Recommendations' },
      { value: 'markdown', label: 'Markdown' },
      {
        value: 'qa',
        label: 'QA Result',
        badge:
          qaResult && !qaResult.passed ? (
            <span className="rounded-full bg-red-100 px-1.5 py-0.5 text-[10px] font-semibold text-red-700">
              {issuesCount}
            </span>
          ) : qaResult?.passed ? (
            <span className="rounded-full bg-green-100 px-1.5 py-0.5 text-[10px] font-semibold text-green-700">
              ok
            </span>
          ) : null,
      },
    ]
  }, [qaResult])

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

      <header className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <p className="text-xs font-medium tracking-wider text-blue-700 uppercase print:hidden">
          Competitive analysis
        </p>
        <h1 className="mt-1 text-2xl font-semibold text-gray-900">{report.title}</h1>
        <p className="mt-2 text-xs text-gray-500">
          Generated {formatDateTime(report.created_at)} · Project {report.project_id}
        </p>
        <div className="mt-3 flex flex-wrap gap-3 text-xs text-gray-600">
          <span>{report.competitor_overview?.length ?? 0} competitors</span>
          <span>{report.source_list?.length ?? 0} sources cited</span>
          <span>{report.executive_summary?.length ?? 0} summary claims</span>
        </div>
      </header>

      {/* Tabbed interface — hidden when printing */}
      <div className="print:hidden">
        <TabsBar items={tabs} value={activeTab} onChange={(v) => setActiveTab(v as TabValue)} />

        <section role="tabpanel" className="pt-2">
          {activeTab === 'summary' && (
            <ClaimList
              claims={report.executive_summary}
              sourceList={report.source_list}
              emptyMessage="No executive summary available."
            />
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
            </>
          )}
        </section>
      </div>

      {/* Full report printed when Export PDF is clicked — hidden on screen */}
      <div className="hidden print:block space-y-8">
        <PrintView report={report} qaResult={qaResult} />
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
          onClick={() => exportMarkdown(report.markdown_content, report.title)}
          className="rounded-md border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
        >
          Export MD
        </button>
        <button
          type="button"
          onClick={() => window.print()}
          className="rounded-md border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
        >
          Export PDF
        </button>
      </div>

      {/* Mounted at the page root so it overlays everything. */}
      <SourcePanel />
    </div>
  )
}

import type { CompetitiveReport } from '@/lib/types'

function PrintView({ report, qaResult }: { report: CompetitiveReport; qaResult: QAResult | undefined }) {
  return (
    <div className="space-y-8 text-sm text-gray-800">
      {/* Executive Summary */}
      {report.executive_summary?.length > 0 && (
        <section>
          <h2 className="mb-3 border-b border-gray-200 pb-1 text-base font-semibold text-gray-900">
            Executive Summary
          </h2>
          <ol className="space-y-2">
            {report.executive_summary.map((claim, i) => (
              <li key={i} className="flex gap-2">
                <span className="shrink-0 font-mono text-xs text-gray-400">[{i + 1}]</span>
                <span>{claim.text}</span>
              </li>
            ))}
          </ol>
        </section>
      )}

      {/* Pricing Comparison */}
      {Object.keys(report.pricing_comparison ?? {}).length > 0 && (
        <section>
          <h2 className="mb-3 border-b border-gray-200 pb-1 text-base font-semibold text-gray-900">
            Pricing Comparison
          </h2>
          <table className="w-full border-collapse text-xs">
            <thead>
              <tr className="bg-gray-50">
                <th className="border border-gray-200 px-3 py-2 text-left">Competitor</th>
                <th className="border border-gray-200 px-3 py-2 text-left">Pricing</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(report.pricing_comparison).map(([comp, pricing]) => (
                <tr key={comp}>
                  <td className="border border-gray-200 px-3 py-2 font-medium">{comp}</td>
                  <td className="border border-gray-200 px-3 py-2">{pricing}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {/* Feature Comparison */}
      {Object.keys(report.feature_comparison ?? {}).length > 0 && (
        <section>
          <h2 className="mb-3 border-b border-gray-200 pb-1 text-base font-semibold text-gray-900">
            Feature Comparison
          </h2>
          <table className="w-full border-collapse text-xs">
            <thead>
              <tr className="bg-gray-50">
                <th className="border border-gray-200 px-3 py-2 text-left">Competitor</th>
                <th className="border border-gray-200 px-3 py-2 text-left">Features</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(report.feature_comparison).map(([comp, features]) => (
                <tr key={comp}>
                  <td className="border border-gray-200 px-3 py-2 font-medium">{comp}</td>
                  <td className="border border-gray-200 px-3 py-2">{features}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {/* SWOT */}
      {report.competitor_overview?.some((ck) => (ck as { swot?: unknown }).swot) && (
        <section>
          <h2 className="mb-3 border-b border-gray-200 pb-1 text-base font-semibold text-gray-900">
            SWOT Analysis
          </h2>
          <SWOTView
            swotComparison={report.swot_comparison ?? {}}
            competitorOverview={report.competitor_overview ?? []}
          />
        </section>
      )}

      {/* Strategic Recommendations */}
      {report.strategic_recommendations?.length > 0 && (
        <section>
          <h2 className="mb-3 border-b border-gray-200 pb-1 text-base font-semibold text-gray-900">
            Strategic Recommendations
          </h2>
          <ol className="space-y-2">
            {report.strategic_recommendations.map((claim, i) => (
              <li key={i} className="flex gap-2">
                <span className="shrink-0 font-mono text-xs text-gray-400">[{i + 1}]</span>
                <span>{claim.text}</span>
              </li>
            ))}
          </ol>
        </section>
      )}

      {/* Full Markdown narrative */}
      {report.markdown_content && (
        <section>
          <h2 className="mb-3 border-b border-gray-200 pb-1 text-base font-semibold text-gray-900">
            Full Report
          </h2>
          <div className="markdown-body leading-relaxed">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {report.markdown_content}
            </ReactMarkdown>
          </div>
        </section>
      )}

      {/* QA Result */}
      {qaResult && (
        <section>
          <h2 className="mb-3 border-b border-gray-200 pb-1 text-base font-semibold text-gray-900">
            QA Result
          </h2>
          <QAResultBanner result={qaResult} />
        </section>
      )}

      {/* Sources */}
      {report.source_list?.length > 0 && (
        <section>
          <h2 className="mb-3 border-b border-gray-200 pb-1 text-base font-semibold text-gray-900">
            Sources
          </h2>
          <ol className="space-y-1 text-xs">
            {report.source_list.map((s, i) => (
              <li key={s.source_id} className="flex gap-2">
                <span className="shrink-0 text-gray-400">[{i + 1}]</span>
                <span>
                  <span className="font-medium">{s.title || s.url}</span>
                  {' — '}
                  <span className="text-gray-500">{s.url}</span>
                </span>
              </li>
            ))}
          </ol>
        </section>
      )}
    </div>
  )
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

function exportMarkdown(content: string, title: string) {
  const filename = title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '') || 'report'
  const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' })
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
  const out = qaRun.output as Partial<QAResult>
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
