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

/**
 * QAResultBanner — top-of-report verdict and issue list.
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

  return (
    <section
      className={cn(
        'rounded-xl border p-5 shadow-sm',
        verdictStyle
      )}
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
          {issues.length === 0
            ? 'No issues raised.'
            : `${issues.length} issue${issues.length > 1 ? 's' : ''} raised`}
        </span>
      </div>

      {issues.length > 0 && (
        <ul className="mt-4 space-y-2">
          {issues.map((issue, i) => (
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
              <p className="mt-1 text-sm font-medium text-gray-900">
                {issue.message}
              </p>
              {issue.suggested_action && (
                <p className="mt-1 text-xs text-gray-600">
                  Suggested action: {issue.suggested_action}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}

      <p className="mt-4 text-xs text-gray-600">
        A QA score of 100 does not guarantee factual accuracy — always
        verify claims with the cited sources.
      </p>
    </section>
  )
}
