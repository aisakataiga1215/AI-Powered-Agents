'use client'

import Link from 'next/link'
import { use, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'

import { api } from '@/lib/api'
import { formatDateTime } from '@/lib/formatDateTime'
import type {
  AgentRun,
  Claim,
  CompetitorInProject,
  CompetitiveReport,
  CompetitorCollectionStats,
  CompetitorKnowledge,
  QAResult,
  QATraceOutput,
  SourceEvidence,
  SWOTAnalysis,
} from '@/lib/types'
import { FeatureComparisonTable } from '@/components/report-viewer/FeatureComparisonTable'
import { PricingComparisonTable } from '@/components/report-viewer/PricingComparisonTable'
import { DroppedCompetitorsList } from '@/components/report-viewer/DroppedCompetitorsList'
import type { DroppedCompetitor } from '@/components/report-viewer/DroppedCompetitorsList'
import ScoringMatrix from '@/components/report-viewer/ScoringMatrix'
import PurposeSections from '@/components/report-viewer/PurposeSections'
import MarketBackground from '@/components/report-viewer/MarketBackground'
import FeatureInsights from '@/components/report-viewer/FeatureInsights'
import OperationMonetization from '@/components/report-viewer/OperationMonetization'

interface PageProps {
  params: Promise<{ id: string }>
}

function purposeSectionTitle(purpose?: string): string | null {
  if (!purpose) return null
  const labels: Record<string, string> = {
    build_similar_product: 'Build Insights',
    choose_product_to_use: 'Decision Guide',
    market_research: 'Market Research',
    competitor_success_analysis: 'Success Analysis',
  }
  return labels[purpose] ?? null
}

export default function PrintPage({ params }: PageProps) {
  const { id } = use(params)

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

  const report = reportQuery.data
  const traces = useMemo(() => tracesQuery.data?.traces ?? [], [tracesQuery.data])
  const projectStatus = projectQuery.data?.status
  const requestedCompetitors = useMemo(() => projectQuery.data?.competitors ?? [], [projectQuery.data])

  const qaResult = useMemo(() => extractLatestQA(traces), [traces])

  const droppedCompetitors = useMemo<DroppedCompetitor[]>(
    () => computeDroppedCompetitors(requestedCompetitors, report, traces),
    [requestedCompetitors, report, traces]
  )

  const citationData = useMemo(
    () =>
      report
        ? buildCitationIndex(report)
        : { index: new Map<string, number>(), usedIds: [], unusedIds: [] },
    [report]
  )

  const analysedCount = useMemo(() => {
    const collectorTrace = traces.find((t) => t.agent_name.includes('Collector'))
    const out = (collectorTrace?.output ?? {}) as Record<string, unknown>
    const collected = out.sufficiently_collected_competitors as string[] | undefined
    return collected?.length ?? report?.competitor_overview?.length ?? 0
  }, [traces, report])

  const qaScore = qaResult?.score ?? 0
  const citedSourcesCount = report?.source_list?.length ?? 0
  const summaryLen = report?.executive_summary?.length ?? 0
  const isInsufficientData =
    citedSourcesCount === 0 || summaryLen === 0 || qaScore < 30 || analysedCount < 2

  if (reportQuery.isLoading) {
    return <PrintSkeleton />
  }

  if (reportQuery.isError || !report) {
    return (
      <div className="p-8 text-sm text-red-700">
        Failed to load report:{' '}
        {reportQuery.error instanceof Error ? reportQuery.error.message : 'Unknown error.'}
      </div>
    )
  }

  const { index: citationIndex, usedIds, unusedIds } = citationData

  const purposeTitle = purposeSectionTitle(report.analysis_purpose)

  const usedSources = usedIds
    .map((sid) => report.source_list.find((s) => s.source_id === sid))
    .filter((s): s is SourceEvidence => s !== undefined)

  const unusedSources = unusedIds
    .map((sid) => report.source_list.find((s) => s.source_id === sid))
    .filter((s): s is SourceEvidence => s !== undefined)

  const hasSwot =
    Object.keys(report.swot_comparison ?? {}).length > 0 ||
    (report.competitor_overview ?? []).some((c) => c.swot)

  return (
    <div className="bg-white">
      <div className="mx-auto max-w-4xl px-6 py-10 print:max-w-none print:px-0 print:py-4">
        {/* Print toolbar — hidden when printing */}
        <div className="print:hidden mb-6 flex items-center justify-end gap-2">
          <Link
            href={`/projects/${id}/report`}
            className="rounded-md border border-gray-200 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 shadow-sm transition-colors hover:bg-gray-50"
          >
            ← Back to Report
          </Link>
          <button
            type="button"
            onClick={() => window.print()}
            className="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-blue-700"
          >
            Print / Save as PDF
          </button>
        </div>

        {/* QA/failure warning banner */}
        {(projectStatus === 'qa_failed' || projectStatus === 'failed') && (
          <div className="mb-6 rounded border border-orange-300 bg-orange-50 p-4 text-sm text-orange-900">
            <strong>
              {projectStatus === 'qa_failed' ? '⚠ Partial Report — QA Failed' : '✗ Workflow Failed'}
            </strong>
            <p className="mt-1 text-xs">
              {projectStatus === 'qa_failed'
                ? `This report did not pass quality checks. Some sources are missing or weak.${
                    droppedCompetitors.length
                      ? ` ${droppedCompetitors.length} competitor${droppedCompetitors.length > 1 ? 's' : ''} could not be fully analysed.`
                      : ''
                  } Treat results with caution and verify claims against cited sources.`
                : 'The analysis workflow encountered an error. This report may be incomplete.'}
            </p>
          </div>
        )}

        {/* Report header */}
        <header className="mb-8 border-b border-gray-200 pb-6">
          <p className="text-xs font-medium uppercase tracking-wider text-blue-700">
            Competitive Analysis
          </p>
          <h1 className="mt-1 text-3xl font-bold text-gray-900">{report.title}</h1>
          <p className="mt-2 text-sm text-gray-500">
            Generated {formatDateTime(report.created_at)} · Project {report.project_id}
          </p>
          <div className="mt-3 flex flex-wrap gap-4 text-sm text-gray-600">
            <span>{report.competitor_overview?.length ?? 0} competitors</span>
            <span>{usedSources.length} cited sources</span>
            <span>{report.executive_summary?.length ?? 0} summary claims</span>
          </div>
        </header>

        {isInsufficientData ? (
          <PrintInsufficientDataSection
            report={report}
            qaResult={qaResult}
            traces={traces}
            requestedCompetitors={requestedCompetitors}
            qaScore={qaScore}
            citedSources={citedSourcesCount}
            droppedCompetitors={droppedCompetitors}
          />
        ) : (
          <>
        {/* Executive Summary */}
        {(report.executive_summary?.length ?? 0) > 0 && (
          <PrintSection title="Executive Summary">
            <PrintClaimList claims={report.executive_summary} citationIndex={citationIndex} />
          </PrintSection>
        )}

        {/* Competitor Overview */}
        {(report.competitor_overview?.length ?? 0) > 0 && (
          <PrintSection title="Competitor Overview">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {report.competitor_overview.map((comp) => (
                <CompetitorCard
                  key={comp.competitor_id ?? comp.competitor_name}
                  competitor={comp}
                />
              ))}
            </div>
          </PrintSection>
        )}

        {/* Feature Comparison */}
        {Object.keys(report.feature_comparison ?? {}).length > 0 && (
          <PrintSection title="Feature Comparison" breakBefore>
            <FeatureComparisonTable
              data={normalizeStringMap(report.feature_comparison)}
              emptyMessage="No feature data."
            />
          </PrintSection>
        )}

        {/* Pricing Comparison */}
        {Object.keys(report.pricing_comparison ?? {}).length > 0 && (
          <PrintSection title="Pricing Comparison" breakBefore>
            <PricingComparisonTable
              data={normalizeStringMap(report.pricing_comparison)}
              emptyMessage="No pricing data."
            />
          </PrintSection>
        )}

        {/* User Persona Comparison */}
        {(report.competitor_overview ?? []).some((c) => (c.user_personas?.length ?? 0) > 0) && (
          <PrintSection title="User Persona Comparison" breakBefore>
            <PrintPersonaSection competitors={report.competitor_overview} />
          </PrintSection>
        )}

        {/* SWOT Analysis */}
        {hasSwot && (
          <PrintSection title="SWOT Analysis" breakBefore>
            <PrintSWOTSection
              swotComparison={report.swot_comparison ?? {}}
              competitorOverview={report.competitor_overview ?? []}
              citationIndex={citationIndex}
            />
          </PrintSection>
        )}

        {/* Strategic Recommendations */}
        {(report.strategic_recommendations?.length ?? 0) > 0 && (
          <PrintSection title="Strategic Recommendations">
            <PrintClaimList
              claims={report.strategic_recommendations}
              citationIndex={citationIndex}
            />
          </PrintSection>
        )}

        {/* Purpose-specific scoring and sections */}
        {purposeTitle && (
          <>
            <PrintSection title={purposeTitle}>
              <ScoringMatrix
                analysisPurpose={report.analysis_purpose}
                competitorScores={report.competitor_scores}
                opportunityScore={report.opportunity_score}
              />
            </PrintSection>
            {report.purpose_sections && Object.keys(report.purpose_sections).length > 0 && (
              <PrintSection title="Purpose Analysis">
                <PurposeSections
                  analysisPurpose={report.analysis_purpose}
                  purposeSections={report.purpose_sections}
                  sourceList={report.source_list ?? []}
                />
              </PrintSection>
            )}
            {report.custom_dimension_analysis &&
              Object.keys(report.custom_dimension_analysis).length > 0 && (
                <PrintSection title="Custom Dimension Analysis">
                  <PrintCustomDimensionTable analysis={report.custom_dimension_analysis} />
                </PrintSection>
              )}
          </>
        )}

        {/* QA Result */}
        {qaResult && (
          <PrintSection title="QA Result">
            <PrintQAResult result={qaResult} />
          </PrintSection>
        )}

        {/* PM-framework sections (M13B) */}
        {report.market_background && (
          <PrintSection title="Market & Background">
            <MarketBackground data={report.market_background} />
          </PrintSection>
        )}
        {report.feature_insights && (
          <PrintSection title="Feature Insights">
            <FeatureInsights data={report.feature_insights} />
          </PrintSection>
        )}
        {report.operation_monetization && (
          <PrintSection title="Operations & Monetization">
            <OperationMonetization data={report.operation_monetization} />
          </PrintSection>
        )}

        {/* Dropped Competitors */}
        {droppedCompetitors.length > 0 && (
          <PrintSection title="Dropped / Insufficient Competitors">
            <DroppedCompetitorsList dropped={droppedCompetitors} />
          </PrintSection>
        )}

        {/* References */}
        {(usedSources.length > 0 || unusedSources.length > 0) && (
          <PrintSection title="References" breakBefore>
            {usedSources.length > 0 && (
              <ol className="space-y-3 text-sm">
                {usedSources.map((s, i) => (
                  <li key={s.source_id} className="flex gap-3">
                    <span className="shrink-0 font-mono text-xs text-gray-500">[{i + 1}]</span>
                    <div>
                      <div className="font-medium text-gray-900">{s.title || s.url}</div>
                      <div className="break-all text-gray-600">{s.url}</div>
                      <div className="mt-0.5 text-xs text-gray-400">
                        Source ID: {s.source_id} · {s.competitor_name} · {s.source_type} ·
                        retrieved {formatDateTime(s.retrieved_at)}
                      </div>
                    </div>
                  </li>
                ))}
              </ol>
            )}
            {unusedSources.length > 0 && (
              <div className="mt-6">
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-400">
                  Additional Sources
                </h3>
                <ul className="space-y-2 text-sm">
                  {unusedSources.map((s) => (
                    <li key={s.source_id} className="flex gap-2 text-gray-600">
                      <span className="shrink-0">–</span>
                      <div>
                        <div className="font-medium text-gray-800">{s.title || s.url}</div>
                        <div className="break-all">{s.url}</div>
                        <div className="text-xs text-gray-400">Source ID: {s.source_id}</div>
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </PrintSection>
        )}
          </>
        )}
      </div>
    </div>
  )
}

// ─── Section wrapper ──────────────────────────────────────────────────────────

// ─── Insufficient data section (print-safe) ───────────────────────────────────

function PrintInsufficientDataSection({
  report,
  qaResult,
  traces,
  requestedCompetitors,
  qaScore,
  citedSources,
  droppedCompetitors,
}: {
  report: CompetitiveReport
  qaResult: QAResult | undefined
  traces: AgentRun[]
  requestedCompetitors: CompetitorInProject[]
  qaScore: number
  citedSources: number
  droppedCompetitors: DroppedCompetitor[]
}) {
  const collectorTrace = traces.find((t) => t.agent_name.includes('Collector'))
  const collectorOutput = (collectorTrace?.output ?? {}) as Record<string, unknown>
  const failedUrls = (collectorOutput.failed_urls as string[] | undefined) ?? []
  const statsMap =
    (collectorOutput.collection_stats_by_competitor as
      | Record<string, CompetitorCollectionStats>
      | undefined) ?? {}
  const attemptedUrlsMap =
    (collectorOutput.attempted_urls_by_competitor as
      | Record<string, string[]>
      | undefined) ?? {}
  const dataMode = (collectorOutput.data_mode as string | undefined) ?? ''

  const allIssues = qaResult?.issues ?? []
  const summaryLen = report.executive_summary?.length ?? 0
  const allAttemptedUrls = Object.entries(attemptedUrlsMap).flatMap(([comp, urls]) =>
    urls.map((u) => ({ competitor: comp, url: u }))
  )

  return (
    <div className="mb-8 rounded border border-amber-300 bg-amber-50 p-6">
      <h2 className="mb-2 text-lg font-semibold text-amber-900">
        Insufficient Data — Report Cannot Be Generated
      </h2>
      <div className="mb-4 flex flex-wrap gap-4 text-sm text-amber-800">
        <span>Cited sources: {citedSources}</span>
        <span>Summary claims: {summaryLen}</span>
        <span>QA score: {qaScore}/100</span>
      </div>

      {requestedCompetitors.length > 0 && (
        <div className="mb-4">
          <h3 className="mb-2 text-sm font-semibold text-amber-900">
            Per-competitor collection
          </h3>
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-amber-200 text-left text-amber-700">
                <th className="pb-1.5 pr-3 font-semibold">Competitor</th>
                <th className="pb-1.5 pr-3 font-semibold">Sources</th>
                <th className="pb-1.5 pr-3 font-semibold">Live / Demo</th>
                <th className="pb-1.5 font-semibold">Status</th>
              </tr>
            </thead>
            <tbody>
              {requestedCompetitors.map((comp) => {
                const stats = statsMap[comp.name]
                return (
                  <tr key={comp.name} className="border-b border-amber-100 last:border-0">
                    <td className="py-1.5 pr-3 font-medium text-gray-900">{comp.name}</td>
                    <td className="py-1.5 pr-3 text-gray-700">{stats?.source_count ?? 0}</td>
                    <td className="py-1.5 pr-3 text-gray-600">
                      {stats ? formatSourceBreakdown(stats, dataMode) : '—'}
                    </td>
                    <td className="py-1.5 text-gray-600">
                      {stats ? formatFallbackStatus(stats, dataMode) : '—'}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {droppedCompetitors.length > 0 && (
        <div className="mb-4">
          <h3 className="mb-2 text-sm font-semibold text-amber-900">Dropped competitors</h3>
          <DroppedCompetitorsList dropped={droppedCompetitors} />
        </div>
      )}

      {allIssues.length > 0 && (
        <div className="mb-4">
          <h3 className="mb-2 text-sm font-semibold text-amber-900">
            QA issues ({allIssues.length})
          </h3>
          <ul className="space-y-1.5">
            {allIssues.map((issue, i) => (
              <li
                key={issue.issue_id ?? i}
                className="rounded border border-amber-200 bg-white px-3 py-2 text-xs text-gray-700"
              >
                <span className="mr-1.5 font-semibold uppercase text-gray-700">
                  {issue.severity}
                </span>
                <span className="text-gray-500">
                  {issue.target_agent} · {issue.issue_type}
                </span>
                <p className="mt-0.5 text-gray-800">{issue.message}</p>
                {issue.suggested_action && (
                  <p className="mt-0.5 text-gray-500">Action: {issue.suggested_action}</p>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {failedUrls.length > 0 && (
        <div className="mb-4">
          <h3 className="mb-1.5 text-sm font-semibold text-amber-900">
            Failed URLs ({failedUrls.length})
          </h3>
          <ul className="space-y-0.5 pl-3 text-xs text-gray-600">
            {failedUrls.map((u) => (
              <li key={u} className="break-all">{u}</li>
            ))}
          </ul>
        </div>
      )}

      {allAttemptedUrls.length > 0 && (
        <div className="mb-4">
          <h3 className="mb-1.5 text-sm font-semibold text-amber-900">
            Attempted discovery URLs ({allAttemptedUrls.length})
          </h3>
          <ul className="space-y-0.5 pl-3 text-xs text-gray-600">
            {allAttemptedUrls.map(({ competitor, url }) => (
              <li key={`${competitor}:${url}`} className="break-all">
                <span className="font-medium text-gray-700">{competitor}:</span> {url}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div>
        <h3 className="mb-1.5 text-sm font-semibold text-amber-900">Suggested next steps</h3>
        <ul className="list-disc space-y-0.5 pl-5 text-xs text-amber-800">
          {dataMode === 'demo' && (
            <li>Switch to &ldquo;Live crawl with fallback&rdquo; for non-SaaS competitors.</li>
          )}
          {dataMode === 'live_with_fallback' && (
            <li>Check that competitor websites are publicly accessible.</li>
          )}
          <li>Select the correct Industry Type when creating the project.</li>
          <li>Verify that the competitor URLs are correct and reachable.</li>
        </ul>
      </div>
    </div>
  )
}

function formatSourceBreakdown(stats: CompetitorCollectionStats, dataMode: string): string {
  if (dataMode === 'demo') {
    return stats.demo_source_count !== undefined ? `${stats.demo_source_count} demo` : '—'
  }
  const live = stats.live_source_count ?? 0
  const demo = stats.fallback_source_count ?? 0
  if (live === 0 && demo === 0) return '0 live'
  if (demo === 0) return `${live} live`
  return `${live} live · ${demo} demo`
}

function formatFallbackStatus(stats: CompetitorCollectionStats, dataMode: string): string {
  if (dataMode === 'demo') return 'demo'
  if (!stats.fallback_attempted) return 'live ok'
  if (stats.fallback_attempted && !stats.fallback_available) return 'No demo fallback available'
  if (stats.fallback_used) return 'fallback used'
  return 'fallback attempted'
}

function PrintSection({
  title,
  children,
  breakBefore = false,
}: {
  title: string
  children: React.ReactNode
  breakBefore?: boolean
}) {
  return (
    <section className={`mb-8 print-section${breakBefore ? ' print-break' : ''}`}>
      <h2 className="mb-4 border-b border-gray-200 pb-2 text-lg font-semibold text-gray-900">
        {title}
      </h2>
      {children}
    </section>
  )
}

// ─── Claim list with inline [N] citations ─────────────────────────────────────

function PrintClaimList({
  claims,
  citationIndex,
}: {
  claims: Claim[]
  citationIndex: Map<string, number>
}) {
  if (!claims?.length) {
    return <p className="text-sm text-gray-500">No items.</p>
  }
  return (
    <ol className="space-y-3">
      {claims.map((claim, i) => (
        <li key={claim.claim_id ?? i} className="flex gap-3 text-sm">
          <span className="mt-0.5 shrink-0 font-mono text-xs text-gray-400">{i + 1}.</span>
          <span className="leading-relaxed text-gray-800">
            {claim.text}
            <InlineCitations evidence={claim.evidence} citationIndex={citationIndex} />
            {claim.is_hypothesis && (
              <span className="ml-1 text-xs text-yellow-600">(hypothesis)</span>
            )}
          </span>
        </li>
      ))}
    </ol>
  )
}

function InlineCitations({
  evidence,
  citationIndex,
}: {
  evidence: string[] | undefined
  citationIndex: Map<string, number>
}) {
  const nums = (evidence ?? [])
    .map((id) => citationIndex.get(id))
    .filter((n): n is number => n !== undefined)
  if (nums.length === 0) return null
  return (
    <sup className="ml-0.5 font-mono text-[10px] text-gray-500">
      {nums.map((n) => `[${n}]`).join('')}
    </sup>
  )
}

// ─── Competitor overview card ─────────────────────────────────────────────────

function CompetitorCard({ competitor }: { competitor: CompetitorKnowledge }) {
  const profile = competitor.product_profile
  const plans = competitor.pricing_model?.plans ?? []
  const featureCategoryCount = competitor.feature_tree?.length ?? 0

  return (
    <div className="print-card rounded-lg border border-gray-200 p-4">
      <h3 className="font-semibold text-gray-900">{competitor.competitor_name}</h3>
      {profile?.positioning?.text && (
        <p className="mt-1 text-sm leading-relaxed text-gray-600">
          {profile.positioning.text}
        </p>
      )}
      <dl className="mt-3 space-y-1 text-xs">
        {featureCategoryCount > 0 && (
          <div className="flex gap-1.5">
            <dt className="font-medium text-gray-700">Features:</dt>
            <dd className="text-gray-500">{featureCategoryCount} categories</dd>
          </div>
        )}
        {plans.length > 0 && (
          <div className="flex gap-1.5">
            <dt className="font-medium text-gray-700">Plans:</dt>
            <dd className="text-gray-500">{plans.map((p) => p.name).join(', ')}</dd>
          </div>
        )}
        {(competitor.user_personas?.length ?? 0) > 0 && (
          <div className="flex gap-1.5">
            <dt className="font-medium text-gray-700">Personas:</dt>
            <dd className="text-gray-500">
              {competitor.user_personas.map((p) => p.name).join(', ')}
            </dd>
          </div>
        )}
      </dl>
    </div>
  )
}

// ─── User persona section ─────────────────────────────────────────────────────

function PrintPersonaSection({ competitors }: { competitors: CompetitorKnowledge[] }) {
  const withPersonas = competitors.filter((c) => (c.user_personas?.length ?? 0) > 0)
  if (withPersonas.length === 0) {
    return <p className="text-sm text-gray-500">No user persona data available.</p>
  }
  return (
    <div className="space-y-6">
      {withPersonas.map((comp) => (
        <div key={comp.competitor_id ?? comp.competitor_name}>
          <h3 className="mb-2 font-semibold text-gray-900">{comp.competitor_name}</h3>
          <div className="space-y-2">
            {comp.user_personas.map((persona, i) => (
              <div key={i} className="print-card rounded border border-gray-200 p-3">
                <div className="text-sm font-medium text-gray-900">{persona.name}</div>
                {persona.description && (
                  <p className="mt-1 text-sm leading-relaxed text-gray-600">
                    {persona.description}
                  </p>
                )}
                {(persona.needs?.length ?? 0) > 0 && (
                  <p className="mt-1.5 text-xs text-gray-500">
                    <span className="font-medium text-gray-600">Needs: </span>
                    {persona.needs.join(', ')}
                  </p>
                )}
                {(persona.pain_points?.length ?? 0) > 0 && (
                  <p className="mt-0.5 text-xs text-gray-500">
                    <span className="font-medium text-gray-600">Pain points: </span>
                    {persona.pain_points.join(', ')}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

// ─── SWOT section (print-safe, no interactive source panel) ───────────────────

type SwotQuadrant = 'strengths' | 'weaknesses' | 'opportunities' | 'threats'

const SWOT_QUADRANTS: { key: SwotQuadrant; label: string; borderClass: string; headingClass: string }[] =
  [
    { key: 'strengths', label: 'Strengths', borderClass: 'border-green-200', headingClass: 'text-green-800' },
    { key: 'weaknesses', label: 'Weaknesses', borderClass: 'border-red-200', headingClass: 'text-red-800' },
    { key: 'opportunities', label: 'Opportunities', borderClass: 'border-blue-200', headingClass: 'text-blue-800' },
    { key: 'threats', label: 'Threats', borderClass: 'border-orange-200', headingClass: 'text-orange-800' },
  ]

function PrintSWOTSection({
  swotComparison,
  competitorOverview,
  citationIndex,
}: {
  swotComparison: Record<string, unknown>
  competitorOverview: CompetitorKnowledge[]
  citationIndex: Map<string, number>
}) {
  const swots = collectSwots(swotComparison, competitorOverview)
  if (swots.length === 0) {
    return <p className="text-sm text-gray-500">No SWOT data available.</p>
  }
  return (
    <div className="space-y-8">
      {swots.map(({ name, swot }) => (
        <div key={name} className="print-card">
          <h3 className="mb-3 font-semibold text-gray-900">{name}</h3>
          <div className="grid grid-cols-2 gap-3">
            {SWOT_QUADRANTS.map((q) => {
              const items: Claim[] = swot[q.key] ?? []
              return (
                <div key={q.key} className={`rounded border p-3 ${q.borderClass}`}>
                  <h4
                    className={`mb-2 text-xs font-semibold uppercase tracking-wider ${q.headingClass}`}
                  >
                    {q.label}
                  </h4>
                  {items.length === 0 ? (
                    <p className="text-xs text-gray-400">No items.</p>
                  ) : (
                    <ul className="space-y-1.5">
                      {items.map((claim, i) => (
                        <li
                          key={claim.claim_id ?? i}
                          className="text-sm leading-relaxed text-gray-800"
                        >
                          {claim.text}
                          <InlineCitations
                            evidence={claim.evidence}
                            citationIndex={citationIndex}
                          />
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      ))}
    </div>
  )
}

// ─── QA result (simplified, no progress bar) ─────────────────────────────────

const SEVERITY_LABEL: Record<string, string> = {
  high:   'Blocking Issue',
  medium: 'Warning',
  low:    'Advisory',
}

function PrintQAResult({ result }: { result: QAResult }) {
  const issues = result.issues ?? []
  const blockingIssues = issues.filter((i) => i.severity === 'high')
  const warnings       = issues.filter((i) => i.severity === 'medium')
  const advisories     = issues.filter((i) => i.severity === 'low')

  return (
    <div className="text-sm">
      <div className="mb-4 flex flex-wrap items-center gap-4">
        <span
          className={
            result.passed ? 'font-semibold text-green-700' : 'font-semibold text-red-700'
          }
        >
          {result.passed ? '✓ Passed' : '✗ Failed'}
        </span>
        <span className="text-gray-600">Score: {result.score}/100</span>
        {blockingIssues.length > 0 && (
          <span className="text-gray-500">
            {blockingIssues.length} blocking issue{blockingIssues.length !== 1 ? 's' : ''}
          </span>
        )}
        {warnings.length > 0 && (
          <span className="text-gray-500">
            {warnings.length} warning{warnings.length !== 1 ? 's' : ''}
          </span>
        )}
        {advisories.length > 0 && (
          <span className="text-gray-500">
            {advisories.length} advisor{advisories.length !== 1 ? 'ies' : 'y'}
          </span>
        )}
        {blockingIssues.length === 0 && warnings.length === 0 && advisories.length === 0 && (
          <span className="text-gray-500">No issues</span>
        )}
      </div>

      {blockingIssues.length > 0 && (
        <>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-600">
            Blocking Issues
          </h3>
          <ul className="mb-4 space-y-2">
            {blockingIssues.map((issue, i) => (
              <li key={issue.issue_id ?? i} className="print-card rounded border border-gray-200 p-3">
                <div className="mb-1 flex items-center gap-2">
                  <span className="text-xs font-semibold uppercase text-gray-700">
                    {SEVERITY_LABEL[issue.severity] ?? issue.severity}
                  </span>
                  <span className="text-xs text-gray-400">
                    {issue.target_agent} · {issue.issue_type}
                  </span>
                </div>
                <p className="text-sm text-gray-900">{issue.message}</p>
                {issue.suggested_action && (
                  <p className="mt-1 text-xs text-gray-500">Action: {issue.suggested_action}</p>
                )}
              </li>
            ))}
          </ul>
        </>
      )}

      {warnings.length > 0 && (
        <>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-600">
            Warnings
          </h3>
          <ul className="mb-4 space-y-2">
            {warnings.map((issue, i) => (
              <li key={issue.issue_id ?? i} className="print-card rounded border border-gray-200 p-3">
                <div className="mb-1 flex items-center gap-2">
                  <span className="text-xs font-semibold uppercase text-yellow-700">
                    {SEVERITY_LABEL[issue.severity] ?? issue.severity}
                  </span>
                  <span className="text-xs text-gray-400">
                    {issue.target_agent} · {issue.issue_type}
                  </span>
                </div>
                <p className="text-sm text-gray-900">{issue.message}</p>
                {issue.suggested_action && (
                  <p className="mt-1 text-xs text-gray-500">Action: {issue.suggested_action}</p>
                )}
              </li>
            ))}
          </ul>
        </>
      )}

      {advisories.length > 0 && (
        <>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-500">
            Advisories
          </h3>
          <ul className="space-y-2">
            {advisories.map((issue, i) => (
              <li key={issue.issue_id ?? i} className="print-card rounded border border-gray-100 p-3">
                <div className="mb-1 flex items-center gap-2">
                  <span className="text-xs font-semibold uppercase text-gray-500">
                    Advisory
                  </span>
                  <span className="text-xs text-gray-400">
                    {issue.target_agent} · {issue.issue_type}
                  </span>
                </div>
                <p className="text-sm text-gray-700">{issue.message}</p>
                {issue.suggested_action && (
                  <p className="mt-1 text-xs text-gray-400">Action: {issue.suggested_action}</p>
                )}
              </li>
            ))}
          </ul>
        </>
      )}

      <p className="mt-3 text-xs text-gray-400">
        A QA score of 100 does not guarantee factual accuracy — always verify claims with cited
        sources.
      </p>
    </div>
  )
}

interface PrintCustomDimensionCell {
  score?: number | string
  rationale?: string
  evidence?: unknown
  source_confidence?: string
  confidence?: string
}

function PrintCustomDimensionTable({
  analysis,
}: {
  analysis: Record<string, Record<string, unknown>>
}) {
  return (
    <div className="space-y-4">
      {Object.entries(analysis).map(([dimension, competitorData]) => {
        const entries = isRecord(competitorData) ? Object.entries(competitorData) : []
        return (
          <div key={dimension} className="overflow-x-auto rounded-lg border border-gray-200 print:overflow-visible">
            <div className="border-b border-gray-200 bg-gray-50 px-4 py-2 text-sm font-medium text-gray-700">
              {dimension.replace(/_/g, ' ')}
            </div>
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-gray-100 text-left text-gray-500">
                  <th className="px-3 py-2 font-medium">Competitor</th>
                  <th className="px-3 py-2 text-center font-medium">Score</th>
                  <th className="px-3 py-2 font-medium">Rationale</th>
                  <th className="px-3 py-2 font-medium">Evidence</th>
                  <th className="px-3 py-2 font-medium">Confidence</th>
                </tr>
              </thead>
              <tbody>
                {entries.map(([competitorName, value]) => {
                  const cell = isRecord(value) ? (value as PrintCustomDimensionCell) : undefined
                  return (
                    <tr key={competitorName} className="border-b border-gray-100 last:border-0">
                      <td className="px-3 py-2 font-medium text-gray-700">{competitorName}</td>
                      <td className="px-3 py-2 text-center text-gray-600">{cell?.score ?? '—'}</td>
                      <td className="px-3 py-2 text-gray-600">{cell?.rationale ?? '—'}</td>
                      <td className="px-3 py-2 font-mono text-[11px] text-gray-500">
                        {formatEvidenceList(cell?.evidence)}
                      </td>
                      <td className="px-3 py-2 text-gray-500">
                        {cell?.source_confidence ?? cell?.confidence ?? '—'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )
      })}
    </div>
  )
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function formatEvidenceList(evidence: unknown): string {
  return Array.isArray(evidence) && evidence.length > 0 ? evidence.join(', ') : '—'
}

// ─── Skeleton ─────────────────────────────────────────────────────────────────

function PrintSkeleton() {
  return (
    <div className="mx-auto max-w-4xl space-y-6 px-6 py-10">
      <div className="h-32 animate-pulse rounded-xl bg-gray-100" />
      <div className="h-48 animate-pulse rounded-xl bg-gray-100" />
      <div className="h-48 animate-pulse rounded-xl bg-gray-100" />
    </div>
  )
}

// ─── Citation index ───────────────────────────────────────────────────────────

interface CitationData {
  index: Map<string, number>
  usedIds: string[]
  unusedIds: string[]
}

function buildCitationIndex(report: CompetitiveReport): CitationData {
  const usedIds: string[] = []

  function see(id: string) {
    if (!usedIds.includes(id)) usedIds.push(id)
  }

  report.executive_summary?.forEach((c) => c.evidence?.forEach(see))
  report.competitor_overview?.forEach((comp) => {
    comp.product_profile?.positioning?.evidence?.forEach(see)
    comp.product_profile?.target_users?.forEach((c) => c.evidence?.forEach(see))
    comp.user_personas?.forEach((p) => p.evidence?.forEach(see))
    comp.swot?.strengths?.forEach((c) => c.evidence?.forEach(see))
    comp.swot?.weaknesses?.forEach((c) => c.evidence?.forEach(see))
    comp.swot?.opportunities?.forEach((c) => c.evidence?.forEach(see))
    comp.swot?.threats?.forEach((c) => c.evidence?.forEach(see))
  })
  report.strategic_recommendations?.forEach((c) => c.evidence?.forEach(see))

  const usedSet = new Set(usedIds)
  const unusedIds = (report.source_list ?? [])
    .map((s) => s.source_id)
    .filter((id) => !usedSet.has(id))

  return {
    index: new Map(usedIds.map((id, i) => [id, i + 1])),
    usedIds,
    unusedIds,
  }
}

// ─── QA extraction (same logic as report/page.tsx) ────────────────────────────

function extractLatestQA(traces: AgentRun[]): QAResult | undefined {
  const qaRun = [...traces].reverse().find((t) => t.agent_name.includes('QA'))
  if (!qaRun) return undefined
  const out = qaRun.output as Partial<QATraceOutput>
  if (typeof out?.passed !== 'boolean' || typeof out?.score !== 'number') return undefined
  return { passed: out.passed, score: out.score, issues: out.issues ?? [] }
}

// ─── String map coercion ──────────────────────────────────────────────────────

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

// ─── SWOT helpers (ported from SWOTView.tsx) ──────────────────────────────────

interface NamedSwot {
  name: string
  swot: SWOTAnalysis
}

function isClaim(v: unknown): v is Claim {
  return typeof v === 'object' && v !== null && typeof (v as Claim).text === 'string'
}

function toClaimArray(value: unknown): Claim[] {
  if (!Array.isArray(value)) return []
  const out: Claim[] = []
  for (const item of value) {
    if (typeof item === 'string') {
      out.push({ text: item, evidence: [] })
    } else if (isClaim(item)) {
      out.push({ ...item, evidence: Array.isArray(item.evidence) ? item.evidence : [] })
    } else if (typeof item === 'object' && item !== null) {
      const obj = item as Record<string, unknown>
      const text =
        typeof obj.text === 'string'
          ? obj.text
          : typeof obj.claim === 'string'
            ? (obj.claim as string)
            : ''
      const evidence = Array.isArray(obj.evidence) ? (obj.evidence as string[]) : []
      if (text) out.push({ text, evidence })
    }
  }
  return out
}

function pickSwot(raw: unknown): SWOTAnalysis | null {
  if (typeof raw !== 'object' || raw === null) return null
  const obj = raw as Record<string, unknown>
  if (
    !('strengths' in obj) &&
    !('weaknesses' in obj) &&
    !('opportunities' in obj) &&
    !('threats' in obj)
  ) {
    return null
  }
  return {
    strengths: toClaimArray(obj.strengths),
    weaknesses: toClaimArray(obj.weaknesses),
    opportunities: toClaimArray(obj.opportunities),
    threats: toClaimArray(obj.threats),
  }
}

function collectSwots(
  swotComparison: Record<string, unknown>,
  competitorOverview: CompetitorKnowledge[]
): NamedSwot[] {
  const out: NamedSwot[] = []
  if (swotComparison && typeof swotComparison === 'object') {
    for (const [name, value] of Object.entries(swotComparison)) {
      const swot = pickSwot(value)
      if (swot) out.push({ name, swot })
    }
  }
  if (out.length > 0) return out
  for (const c of competitorOverview ?? []) {
    if (c.swot) {
      out.push({
        name: c.competitor_name || c.competitor_id || 'Competitor',
        swot: {
          strengths: toClaimArray(c.swot.strengths),
          weaknesses: toClaimArray(c.swot.weaknesses),
          opportunities: toClaimArray(c.swot.opportunities),
          threats: toClaimArray(c.swot.threats),
        },
      })
    }
  }
  return out
}

// ─── Dropped competitor helpers ───────────────────────────────────────────────

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
