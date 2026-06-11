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

interface PageProps {
  params: Promise<{ id: string }>
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

  const qaScore = qaResult?.score ?? 0
  const citedSourcesCount = report?.source_list?.length ?? 0
  const summaryLen = report?.executive_summary?.length ?? 0
  const isInsufficientData =
    citedSourcesCount === 0 || summaryLen === 0

  if (reportQuery.isLoading) {
    return <PrintSkeleton />
  }

  if (reportQuery.isError || !report) {
    return (
      <div className="p-8 text-sm text-red-700">
        报告加载失败：{' '}
        {reportQuery.error instanceof Error ? reportQuery.error.message : '未知错误。'}
      </div>
    )
  }

  const { index: citationIndex, usedIds, unusedIds } = citationData

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
            ← 返回报告
          </Link>
          <button
            type="button"
            onClick={() => window.print()}
            className="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-blue-700"
          >
            打印 / 保存为 PDF
          </button>
        </div>

        {/* QA/failure warning banner */}
        {(projectStatus === 'qa_failed' || projectStatus === 'failed') && (
          <div className="mb-6 rounded border border-orange-300 bg-orange-50 p-4 text-sm text-orange-900">
            <strong>
              {projectStatus === 'qa_failed' ? '⚠ 部分报告 - QA 未通过' : '✗ 工作流失败'}
            </strong>
            <p className="mt-1 text-xs">
              {projectStatus === 'qa_failed'
                ? `这份报告没有通过质量检查，部分来源缺失或较弱。${
                    droppedCompetitors.length
                      ? ` ${droppedCompetitors.length} 个竞品未能完整分析。`
                      : ''
                  } 请谨慎使用结果，并对照引用来源核验结论。`
                : '分析工作流遇到错误，报告可能不完整。'}
            </p>
          </div>
        )}

        {/* Report header */}
        <header className="mb-8 border-b border-gray-200 pb-6">
          <p className="text-xs font-medium uppercase tracking-wider text-blue-700">
            竞品分析
          </p>
          <h1 className="mt-1 text-3xl font-bold text-gray-900">{report.title}</h1>
          <p className="mt-2 text-sm text-gray-500">
            生成时间：{formatDateTime(report.created_at)} · 项目：{report.project_id}
          </p>
          <div className="mt-3 flex flex-wrap gap-4 text-sm text-gray-600">
            <span>{report.competitor_overview?.length ?? 0} 个竞品</span>
            <span>{usedSources.length} 个引用来源</span>
            <span>{report.executive_summary?.length ?? 0} 条摘要结论</span>
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
          <PrintSection title="执行摘要">
            <PrintClaimList claims={report.executive_summary} citationIndex={citationIndex} />
          </PrintSection>
        )}

        {/* Competitor Overview */}
        {(report.competitor_overview?.length ?? 0) > 0 && (
          <PrintSection title="竞品概览">
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
          <PrintSection title="功能对比" breakBefore>
            <FeatureComparisonTable
              data={normalizeStringMap(report.feature_comparison)}
              emptyMessage="暂无功能数据。"
            />
          </PrintSection>
        )}

        {/* Pricing Comparison */}
        {Object.keys(report.pricing_comparison ?? {}).length > 0 && (
          <PrintSection title="定价对比" breakBefore>
            <PricingComparisonTable
              data={normalizeStringMap(report.pricing_comparison)}
              emptyMessage="暂无定价数据。"
            />
          </PrintSection>
        )}

        {/* User Persona Comparison */}
        {(report.competitor_overview ?? []).some((c) => (c.user_personas?.length ?? 0) > 0) && (
          <PrintSection title="用户画像对比" breakBefore>
            <PrintPersonaSection competitors={report.competitor_overview} />
          </PrintSection>
        )}

        {/* SWOT Analysis */}
        {hasSwot && (
          <PrintSection title="SWOT 分析" breakBefore>
            <PrintSWOTSection
              swotComparison={report.swot_comparison ?? {}}
              competitorOverview={report.competitor_overview ?? []}
              citationIndex={citationIndex}
            />
          </PrintSection>
        )}

        {/* Strategic Recommendations */}
        {(report.strategic_recommendations?.length ?? 0) > 0 && (
          <PrintSection title="战略建议">
            <PrintClaimList
              claims={report.strategic_recommendations}
              citationIndex={citationIndex}
            />
          </PrintSection>
        )}

        {/* QA Result */}
        {qaResult && (
          <PrintSection title="QA 结果">
            <PrintQAResult result={qaResult} />
          </PrintSection>
        )}

        {/* Dropped Competitors */}
        {droppedCompetitors.length > 0 && (
          <PrintSection title="已剔除 / 数据不足的竞品">
            <DroppedCompetitorsList dropped={droppedCompetitors} />
          </PrintSection>
        )}

        {/* References */}
        {(usedSources.length > 0 || unusedSources.length > 0) && (
          <PrintSection title="参考来源" breakBefore>
            {usedSources.length > 0 && (
              <ol className="space-y-3 text-sm">
                {usedSources.map((s, i) => (
                  <li key={s.source_id} className="flex gap-3">
                    <span className="shrink-0 font-mono text-xs text-gray-500">[{i + 1}]</span>
                    <div>
                      <div className="font-medium text-gray-900">{s.title || s.url}</div>
                      <div className="break-all text-gray-600">{s.url}</div>
                      <div className="mt-0.5 text-xs text-gray-400">
                        来源 ID：{s.source_id} · {s.competitor_name} · {s.source_type} ·
                        获取时间 {formatDateTime(s.retrieved_at)}
                      </div>
                    </div>
                  </li>
                ))}
              </ol>
            )}
            {unusedSources.length > 0 && (
              <div className="mt-6">
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-400">
                  补充来源
                </h3>
                <ul className="space-y-2 text-sm">
                  {unusedSources.map((s) => (
                    <li key={s.source_id} className="flex gap-2 text-gray-600">
                      <span className="shrink-0">–</span>
                      <div>
                        <div className="font-medium text-gray-800">{s.title || s.url}</div>
                        <div className="break-all">{s.url}</div>
                        <div className="text-xs text-gray-400">来源 ID：{s.source_id}</div>
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
        数据不足，无法生成可靠报告
      </h2>
      <div className="mb-4 flex flex-wrap gap-4 text-sm text-amber-800">
        <span>引用来源：{citedSources}</span>
        <span>摘要结论：{summaryLen}</span>
        <span>QA 评分：{qaScore}/100</span>
      </div>

      {requestedCompetitors.length > 0 && (
        <div className="mb-4">
          <h3 className="mb-2 text-sm font-semibold text-amber-900">
            按竞品采集情况
          </h3>
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-amber-200 text-left text-amber-700">
                <th className="pb-1.5 pr-3 font-semibold">竞品</th>
                <th className="pb-1.5 pr-3 font-semibold">来源数</th>
                <th className="pb-1.5 pr-3 font-semibold">Live / Demo</th>
                <th className="pb-1.5 font-semibold">状态</th>
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
          <h3 className="mb-2 text-sm font-semibold text-amber-900">已剔除竞品</h3>
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
                  <p className="mt-0.5 text-gray-500">建议：{issue.suggested_action}</p>
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
        <h3 className="mb-1.5 text-sm font-semibold text-amber-900">建议下一步</h3>
        <ul className="list-disc space-y-0.5 pl-5 text-xs text-amber-800">
          {dataMode === 'demo' && (
            <li>非 SaaS 竞品建议切换到“真实采集 + Demo 兜底”。</li>
          )}
          {dataMode === 'live_with_fallback' && (
            <li>检查竞品网站是否可公开访问。</li>
          )}
          <li>创建项目时选择正确的行业类型。</li>
          <li>确认竞品 URL 正确且可访问。</li>
        </ul>
      </div>
    </div>
  )
}

function formatSourceBreakdown(stats: CompetitorCollectionStats, dataMode: string): string {
  if (dataMode === 'demo') {
    return stats.demo_source_count !== undefined ? `${stats.demo_source_count} 个 Demo` : '—'
  }
  const live = stats.live_source_count ?? 0
  const demo = stats.fallback_source_count ?? 0
  if (live === 0 && demo === 0) return '0 个真实来源'
  if (demo === 0) return `${live} 个真实来源`
  return `${live} 个真实来源 · ${demo} 个 Demo`
}

function formatFallbackStatus(stats: CompetitorCollectionStats, dataMode: string): string {
  if (dataMode === 'demo') return 'Demo'
  if (!stats.fallback_attempted) return '真实采集成功'
  if (stats.fallback_attempted && !stats.fallback_available) return '无可用 Demo 兜底'
  if (stats.fallback_used) return '已使用兜底'
  return '已尝试兜底'
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
    return <p className="text-sm text-gray-500">暂无条目。</p>
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
            <dt className="font-medium text-gray-700">功能：</dt>
            <dd className="text-gray-500">{featureCategoryCount} 个类别</dd>
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
    return <p className="text-sm text-gray-500">暂无用户画像数据。</p>
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
                    <span className="font-medium text-gray-600">需求： </span>
                    {persona.needs.join(', ')}
                  </p>
                )}
                {(persona.pain_points?.length ?? 0) > 0 && (
                  <p className="mt-0.5 text-xs text-gray-500">
                    <span className="font-medium text-gray-600">痛点： </span>
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
    { key: 'strengths', label: '优势', borderClass: 'border-green-200', headingClass: 'text-green-800' },
    { key: 'weaknesses', label: '劣势', borderClass: 'border-red-200', headingClass: 'text-red-800' },
    { key: 'opportunities', label: '机会', borderClass: 'border-blue-200', headingClass: 'text-blue-800' },
    { key: 'threats', label: '威胁', borderClass: 'border-orange-200', headingClass: 'text-orange-800' },
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
    return <p className="text-sm text-gray-500">暂无 SWOT 数据。</p>
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
                    <p className="text-xs text-gray-400">暂无条目。</p>
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
  high:   '阻塞问题',
  medium: '警告',
  low:    '提示',
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
          {result.passed ? '✓ 通过' : '✗ 未通过'}
        </span>
        <span className="text-gray-600">评分：{result.score}/100</span>
        {blockingIssues.length > 0 && (
          <span className="text-gray-500">
            {blockingIssues.length} 个阻塞问题
          </span>
        )}
        {warnings.length > 0 && (
          <span className="text-gray-500">
            {warnings.length} 个警告
          </span>
        )}
        {advisories.length > 0 && (
          <span className="text-gray-500">
            {advisories.length} 个提示
          </span>
        )}
        {blockingIssues.length === 0 && warnings.length === 0 && advisories.length === 0 && (
          <span className="text-gray-500">没有问题</span>
        )}
      </div>

      {blockingIssues.length > 0 && (
        <>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-600">
            阻塞问题
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
                  <p className="mt-1 text-xs text-gray-500">建议：{issue.suggested_action}</p>
                )}
              </li>
            ))}
          </ul>
        </>
      )}

      {warnings.length > 0 && (
        <>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-600">
            警告
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
                  <p className="mt-1 text-xs text-gray-500">建议：{issue.suggested_action}</p>
                )}
              </li>
            ))}
          </ul>
        </>
      )}

      {advisories.length > 0 && (
        <>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-500">
            提示
          </h3>
          <ul className="space-y-2">
            {advisories.map((issue, i) => (
              <li key={issue.issue_id ?? i} className="print-card rounded border border-gray-100 p-3">
                <div className="mb-1 flex items-center gap-2">
                  <span className="text-xs font-semibold uppercase text-gray-500">
                    提示
                  </span>
                  <span className="text-xs text-gray-400">
                    {issue.target_agent} · {issue.issue_type}
                  </span>
                </div>
                <p className="text-sm text-gray-700">{issue.message}</p>
                {issue.suggested_action && (
                  <p className="mt-1 text-xs text-gray-400">建议：{issue.suggested_action}</p>
                )}
              </li>
            ))}
          </ul>
        </>
      )}

      <p className="mt-3 text-xs text-gray-400">
        QA 100 分不代表事实一定正确，仍需对照引用来源核验关键结论。
      </p>
    </div>
  )
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
        name: c.competitor_name || c.competitor_id || '竞品',
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
    if (cov.score === 0) return '未采集到可用来源'
    if (cov.score < 40) return `来源覆盖较弱（${cov.score}/100）`
  }

  if (dataMode === 'demo') return '未找到 Demo fixture'
  return '可用于分析的来源不足'
}
