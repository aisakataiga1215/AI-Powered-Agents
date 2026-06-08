import { cn } from '@/lib/cn'
import type { IssueSeverity, QAResult } from '@/lib/types'

interface QAResultBannerProps {
  result: QAResult
}

const SEVERITY_STYLE: Record<IssueSeverity, string> = {
  critical: 'bg-red-100 text-red-800 border-red-200',
  high: 'bg-orange-100 text-orange-800 border-orange-200',
  medium: 'bg-yellow-100 text-yellow-800 border-yellow-200',
  low: 'bg-gray-100 text-gray-700 border-gray-200',
}

function summariseIssues(blocking: number, advisories: number): string {
  if (blocking === 0 && advisories === 0) return 'No issues raised.'
  if (blocking > 0 && advisories > 0) {
    return `${blocking} blocking · ${advisories} advisor${advisories > 1 ? 'ies' : 'y'}`
  }
  if (blocking > 0) {
    return `${blocking} blocking issue${blocking > 1 ? 's' : ''}`
  }
  return `${advisories} advisor${advisories > 1 ? 'ies' : 'y'}`
}

/**
 * QAResultBanner — top-of-report verdict and issue list.
 *
 * Low-severity issues are shown as "advisories" — they do not reduce the QA
 * score (0 deduction per the model_validator in qa.py) and are rendered under
 * a separate sub-heading so they are visually distinct from blocking issues.
 *
 * We deliberately surface the caveat that a high QA score does not
 * imply factual correctness. The QA agent checks coverage and structure;
 * truth verification requires the source panel.
 */
export function QAResultBanner({ result }: QAResultBannerProps) {
  const verdictStyle = result.passed
    ? 'border-green-200 bg-green-50 text-green-800'
    : 'border-red-200 bg-red-50 text-red-800'
  const issues = result.issues ?? []

  const blockingIssues = issues.filter((i) => i.severity !== 'low')
  const advisories = issues.filter((i) => i.severity === 'low')

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
            {result.passed ? '✓ QA Passed' : '✗ QA Failed'} —{' '}
            <span className="font-mono">Score: {result.score}/100</span>
          </h2>
        </div>
        <span className="text-sm opacity-80">
          {summariseIssues(blockingIssues.length, advisories.length)}
        </span>
      </div>

      {blockingIssues.length > 0 && (
        <>
          <h3 className="mt-4 text-xs font-semibold uppercase tracking-wider opacity-70">
            Blocking Issues
          </h3>
          <ul className="mt-2 space-y-2">
            {blockingIssues.map((issue, i) => (
              <li
                key={issue.issue_id ?? i}
                className="rounded-md border border-white/40 bg-white/60 p-3 text-sm text-gray-800"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span
                    className={cn(
                      'rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider',
                      SEVERITY_STYLE[issue.severity] ?? SEVERITY_STYLE.low
                    )}
                  >
                    {issue.severity}
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
              <li
                key={issue.issue_id ?? i}
                className="rounded-md border border-white/40 bg-white/60 p-3 text-sm text-gray-700"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span
                    className={cn(
                      'rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider',
                      SEVERITY_STYLE.low
                    )}
                  >
                    advisory
                  </span>
                  <span className="text-xs text-gray-500">
                    {issue.target_agent} · {issue.issue_type}
                  </span>
                </div>
                <p className="mt-1 text-sm text-gray-800">{issue.message}</p>
                {issue.suggested_action && (
                  <p className="mt-1 text-xs text-gray-500">
                    Suggested action: {issue.suggested_action}
                  </p>
                )}
              </li>
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
