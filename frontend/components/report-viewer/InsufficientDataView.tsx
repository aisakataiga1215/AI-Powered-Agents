import type {
  AgentRun,
  CompetitorInProject,
  CompetitiveReport,
  CompetitorCollectionStats,
  QAResult,
} from '@/lib/types'
import { DroppedCompetitorsList } from './DroppedCompetitorsList'

interface Props {
  report: CompetitiveReport
  qaResult: QAResult | undefined
  traces: AgentRun[]
  requestedCompetitors: CompetitorInProject[]
  qaScore: number
  citedSources: number
}

export function InsufficientDataView({
  report,
  qaResult,
  traces,
  requestedCompetitors,
  qaScore,
  citedSources,
}: Props) {
  const collectorTrace = traces.find((t) => t.agent_name.includes('Collector'))
  const collectorOutput = (collectorTrace?.output ?? {}) as Record<string, unknown>
  const failedUrls = (collectorOutput.failed_urls as string[] | undefined) ?? []
  const statsMap =
    (collectorOutput.collection_stats_by_competitor as
      | Record<string, CompetitorCollectionStats>
      | undefined) ?? {}
  const droppedCompetitors = (
    (collectorOutput.dropped_competitors as
      | Array<{ name: string; url: string; reason: string }>
      | undefined) ?? []
  )
  const attemptedUrlsMap =
    (collectorOutput.attempted_urls_by_competitor as
      | Record<string, string[]>
      | undefined) ?? {}
  const dataMode = (collectorOutput.data_mode as string | undefined) ?? ''

  const allIssues = qaResult?.issues ?? []
  const summaryLen = report.executive_summary?.length ?? 0

  const suggestedActions: string[] = []
  if (dataMode === 'demo') {
    suggestedActions.push('非 SaaS 竞品建议切换到“真实采集 + Demo 兜底”。')
  } else if (dataMode === 'live_with_fallback') {
    suggestedActions.push('检查竞品网站是否可公开访问。')
  }
  suggestedActions.push('创建项目时选择正确的行业类型。')
  suggestedActions.push('确认竞品 URL 正确且可访问。')

  const allAttemptedUrls = Object.entries(attemptedUrlsMap).flatMap(([comp, urls]) =>
    urls.map((u) => ({ competitor: comp, url: u }))
  )

  return (
    <div className="space-y-4 rounded-xl border border-amber-300 bg-amber-50 p-6">
      <div>
        <h2 className="text-base font-semibold text-amber-900">
          数据不足，无法生成可靠报告
        </h2>
        <div className="mt-2 flex flex-wrap gap-4 text-sm text-amber-800">
          <span>引用来源：{citedSources}</span>
          <span>摘要结论：{summaryLen}</span>
          <span>QA 评分：{qaScore}/100</span>
        </div>
      </div>

      {requestedCompetitors.length > 0 && (
        <div>
          <h3 className="mb-2 text-sm font-medium text-amber-900">
            按竞品采集情况
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-amber-200 text-left text-amber-700">
                  <th className="pb-1.5 pr-3 font-semibold">竞品</th>
                  <th className="pb-1.5 pr-3 font-semibold">来源数</th>
                  <th className="pb-1.5 pr-3 font-semibold">真实 / Demo</th>
                  <th className="pb-1.5 font-semibold">状态</th>
                </tr>
              </thead>
              <tbody>
                {requestedCompetitors.map((comp) => {
                  const stats = statsMap[comp.name]
                  return (
                    <tr
                      key={comp.name}
                      className="border-b border-amber-100 last:border-0"
                    >
                      <td className="py-1.5 pr-3 font-medium text-gray-900">
                        {comp.name}
                      </td>
                      <td className="py-1.5 pr-3 text-gray-700">
                        {stats?.source_count ?? 0}
                      </td>
                      <td className="py-1.5 pr-3 text-gray-600">
                        {stats
                          ? formatSourceBreakdown(stats, dataMode)
                          : '—'}
                      </td>
                      <td className="py-1.5 text-gray-600">
                        {stats
                          ? formatFallbackStatus(stats, dataMode)
                          : '—'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {droppedCompetitors.length > 0 && (
        <div>
          <h3 className="mb-2 text-sm font-medium text-amber-900">
            已剔除竞品
          </h3>
          <DroppedCompetitorsList dropped={droppedCompetitors} />
        </div>
      )}

      {allIssues.length > 0 && (
        <div>
          <h3 className="mb-2 text-sm font-medium text-amber-900">
            QA 问题（{allIssues.length}）
          </h3>
          <ul className="space-y-1.5">
            {allIssues.map((issue, i) => (
              <li
                key={issue.issue_id ?? i}
                className="rounded border border-amber-200 bg-white px-3 py-2 text-xs text-gray-700"
              >
                <span
                  className={`mr-1.5 font-semibold uppercase ${severityClass(issue.severity)}`}
                >
                  {issue.severity}
                </span>
                <span className="text-gray-500">
                  {issue.target_agent} · {issue.issue_type}
                </span>
                <p className="mt-0.5 text-gray-800">{issue.message}</p>
                {issue.suggested_action && (
                  <p className="mt-0.5 text-gray-500">
                    建议：{issue.suggested_action}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {failedUrls.length > 0 && (
        <details className="text-xs">
          <summary className="cursor-pointer select-none font-medium text-amber-800">
            失败 URL（{failedUrls.length}）
          </summary>
          <ul className="mt-1.5 space-y-0.5 pl-3 text-gray-600">
            {failedUrls.map((u) => (
              <li key={u} className="break-all">
                {u}
              </li>
            ))}
          </ul>
        </details>
      )}

      {allAttemptedUrls.length > 0 && (
        <details className="text-xs">
          <summary className="cursor-pointer select-none font-medium text-amber-800">
            尝试发现的 URL（{allAttemptedUrls.length}）
          </summary>
          <ul className="mt-1.5 space-y-0.5 pl-3 text-gray-600">
            {allAttemptedUrls.map(({ competitor, url }) => (
              <li key={`${competitor}:${url}`} className="break-all">
                <span className="font-medium text-gray-700">{competitor}:</span> {url}
              </li>
            ))}
          </ul>
        </details>
      )}

      {suggestedActions.length > 0 && (
        <div>
          <h3 className="mb-1.5 text-sm font-medium text-amber-900">
            建议下一步
          </h3>
          <ul className="list-disc space-y-1 pl-5 text-xs text-amber-800">
            {suggestedActions.map((action) => (
              <li key={action}>{action}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function formatSourceBreakdown(
  stats: CompetitorCollectionStats,
  dataMode: string,
): string {
  if (dataMode === 'demo') {
    return stats.demo_source_count !== undefined ? `${stats.demo_source_count} 个 Demo` : '—'
  }
  const live = stats.live_source_count ?? 0
  const demo = stats.fallback_source_count ?? 0
  if (live === 0 && demo === 0) return '0 个真实来源'
  if (demo === 0) return `${live} 个真实来源`
  return `${live} 个真实来源 · ${demo} 个 Demo`
}

function formatFallbackStatus(
  stats: CompetitorCollectionStats,
  dataMode: string,
): string {
  if (dataMode === 'demo') return 'Demo'
  if (!stats.fallback_attempted) return '真实采集成功'
  if (stats.fallback_attempted && !stats.fallback_available) {
    return '无可用 Demo 兜底'
  }
  if (stats.fallback_used) return '已使用兜底'
  return '已尝试兜底'
}

function severityClass(severity: string): string {
  switch (severity) {
    case 'critical':
      return 'text-red-700'
    case 'high':
      return 'text-orange-700'
    case 'medium':
      return 'text-yellow-700'
    default:
      return 'text-gray-500'
  }
}
