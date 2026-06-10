import { cn } from '@/lib/cn'
import type { IssueSeverity, QAResult } from '@/lib/types'

interface QAResultBannerProps {
  result: QAResult
}

const SEVERITY_STYLE: Record<IssueSeverity, string> = {
  high: 'bg-red-100 text-red-800 border-red-200',
  medium: 'bg-yellow-100 text-yellow-800 border-yellow-200',
  low: 'bg-gray-100 text-gray-700 border-gray-200',
}

const SEVERITY_BADGE_LABEL: Record<IssueSeverity, string> = {
  high: 'blocking',
  medium: 'warning',
  low: 'advisory',
}

function pluralise(n: number, singular: string, plural: string): string {
  return `${n} ${n === 1 ? singular : plural}`
}

function buildSummary(
  blockingCount: number,
  warningCount: number,
  advisoryCount: number,
  passed: boolean,
): string {
  const parts: string[] = []
  if (!passed && blockingCount > 0) parts.push(pluralise(blockingCount, 'blocking issue', 'blocking issues'))
  if (warningCount > 0) parts.push(pluralise(warningCount, 'warning', 'warnings'))
  if (advisoryCount > 0) parts.push(pluralise(advisoryCount, 'advisory', 'advisories'))
  return parts.length > 0 ? parts.join(' · ') : 'No issues raised.'
}

export function QAResultBanner({ result }: QAResultBannerProps) {
  const verdictStyle = result.passed
    ? 'border-green-200 bg-green-50 text-green-800'
    : 'border-red-200 bg-red-50 text-red-800'
  const issues = result.issues ?? []

  const blockingIssues = issues.filter((i) => i.severity === 'high')
  const warnings       = issues.filter((i) => i.severity === 'medium')
  const advisories     = issues.filter((i) => i.severity === 'low')

  return (
    <section
      className={cn('rounded-xl border p-5 shadow-sm', verdictStyle)}
      aria-live="polite"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs font-medium uppercase tracking-wider opacity-80">
            QA Verdict
          </p>
          <h2 className="mt-1 text-xl font-semibold">
            {result.passed ? '✓ QA Passed' : '✗ QA Failed'}{' '}
            <span className="font-mono">· Score {result.score}/100</span>
          </h2>
        </div>
        <span className="text-sm opacity-80">
          {buildSummary(blockingIssues.length, warnings.length, advisories.length, result.passed)}
        </span>
      </div>

      {blockingIssues.length > 0 && (
        <>
          <h3 className="mt-4 text-xs font-semibold uppercase tracking-wider opacity-70">
            Blocking Issues
          </h3>
          <ul className="mt-2 space-y-2">
            {blockingIssues.map((issue, i) => (
              <IssueRow key={issue.issue_id ?? i} issue={issue} />
            ))}
          </ul>
        </>
      )}

      {warnings.length > 0 && (
        <>
          <h3 className="mt-4 text-xs font-semibold uppercase tracking-wider opacity-70">
            Warnings
          </h3>
          <ul className="mt-2 space-y-2">
            {warnings.map((issue, i) => (
              <IssueRow key={issue.issue_id ?? i} issue={issue} />
            ))}
          </ul>
        </>
      )}

      {advisories.length > 0 && (
        <>
          <h3 className="mt-4 text-xs font-semibold uppercase tracking-wider opacity-70">
            Advisories
          </h3>
          <ul className="mt-2 space-y-2">
            {advisories.map((issue, i) => (
              <IssueRow key={issue.issue_id ?? i} issue={issue} />
            ))}
          </ul>
        </>
      )}

      <p className="mt-4 text-xs text-gray-600">
        A QA score of 100 does not guarantee factual accuracy — always
        verify claims with the cited sources.
      </p>
    </section>
  )
}

function IssueRow({ issue }: { issue: QAResult['issues'][number] }) {
  const severity = issue.severity as IssueSeverity
  return (
    <li className="rounded-md border border-white/40 bg-white/60 p-3 text-sm text-gray-800">
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={cn(
            'rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider',
            SEVERITY_STYLE[severity] ?? SEVERITY_STYLE.low
          )}
        >
          {SEVERITY_BADGE_LABEL[severity] ?? severity}
        </span>
        <span className="text-xs text-gray-500">
          {issue.target_agent} · {issue.issue_type}
        </span>
      </div>
      <p className="mt-1 text-sm font-medium text-gray-900">{issue.message}</p>
      {issue.suggested_action && (
        <p className="mt-1 text-xs text-gray-600">
          Suggested action: {issue.suggested_action}
        </p>
      )}
    </li>
  )
}
