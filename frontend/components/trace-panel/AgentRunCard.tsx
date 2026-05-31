import { AgentStatusBadge } from '@/components/agent-flow/AgentStatusBadge'
import { cn } from '@/lib/cn'
import type { AgentRun, QAResult } from '@/lib/types'

interface AgentRunCardProps {
  run: AgentRun
}

/**
 * AgentRunCard — renders one row of the Agent trace timeline.
 *
 * Special handling: when the agent is a QAAgent and its output payload
 * contains `passed`, we lift the QA verdict into its own pill so the
 * user does not need to expand the raw JSON to spot a failure.
 */
export function AgentRunCard({ run }: AgentRunCardProps) {
  const qa = extractQAResult(run)
  return (
    <article className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <h3 className="font-semibold text-gray-900">{run.agent_name}</h3>
          <AgentStatusBadge status={run.status} />
          {run.retry_count > 0 && (
            <span className="inline-flex items-center rounded border border-orange-200 bg-orange-50 px-2 py-0.5 text-xs font-medium text-orange-700">
              Retried {run.retry_count}×
            </span>
          )}
        </div>
        <div className="flex items-center gap-3 text-xs text-gray-500">
          <span>{run.latency_ms}ms</span>
          <span>~{run.token_usage.total_tokens.toLocaleString()} tokens</span>
        </div>
      </header>

      {qa && (
        <div
          className={cn(
            'mt-3 flex flex-wrap items-center gap-3 rounded-md border p-2 text-xs',
            qa.passed
              ? 'border-green-200 bg-green-50 text-green-800'
              : 'border-red-200 bg-red-50 text-red-800'
          )}
        >
          <span className="font-semibold">
            QA {qa.passed ? 'passed' : 'failed'} — score {qa.score}/100
          </span>
          {qa.issues.length > 0 && (
            <ul className="list-disc space-y-0.5 pl-5">
              {qa.issues.slice(0, 3).map((issue, i) => (
                <li key={i}>
                  <span className="font-medium uppercase">{issue.severity}</span>{' '}
                  · {issue.message}
                </li>
              ))}
              {qa.issues.length > 3 && (
                <li className="text-gray-600">
                  + {qa.issues.length - 3} more issues (see report QA tab)
                </li>
              )}
            </ul>
          )}
        </div>
      )}

      {run.error_message && (
        <div className="mt-3 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          <span className="font-semibold">Error: </span>
          {run.error_message}
        </div>
      )}

      <details className="mt-3 rounded border border-gray-200 bg-gray-50">
        <summary className="cursor-pointer select-none px-3 py-2 text-xs font-medium text-gray-700 hover:bg-gray-100">
          Input
        </summary>
        <pre className="max-h-60 overflow-auto rounded-b border-t border-gray-200 bg-gray-50 p-3 text-xs leading-relaxed text-gray-700">
          {safeStringify(run.input)}
        </pre>
      </details>

      <details className="mt-2 rounded border border-gray-200 bg-gray-50">
        <summary className="cursor-pointer select-none px-3 py-2 text-xs font-medium text-gray-700 hover:bg-gray-100">
          Output
        </summary>
        <pre className="max-h-60 overflow-auto rounded-b border-t border-gray-200 bg-gray-50 p-3 text-xs leading-relaxed text-gray-700">
          {safeStringify(run.output)}
        </pre>
      </details>
    </article>
  )
}

function extractQAResult(run: AgentRun): QAResult | null {
  if (!run.agent_name.includes('QA')) return null
  const out = run.output as Partial<QAResult>
  if (typeof out?.passed === 'boolean' && typeof out?.score === 'number') {
    return {
      passed: out.passed,
      score: out.score,
      issues: out.issues ?? [],
    }
  }
  return null
}

function safeStringify(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}
