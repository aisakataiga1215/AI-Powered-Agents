import type { AgentRun } from '@/lib/types'
import { AgentRunCard } from '@/components/trace-panel/AgentRunCard'
import { formatTime } from '@/lib/formatDateTime'

interface TraceTimelineProps {
  traces: AgentRun[]
}

/**
 * TraceTimeline — vertical timeline of agent runs.
 *
 * Runs are ordered chronologically by `created_at`. Each timeline node
 * carries a colored dot derived from the run's status so the user can
 * scan for failures and reworks at a glance.
 */
export function TraceTimeline({ traces }: TraceTimelineProps) {
  if (traces.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-gray-300 bg-white p-6 text-center text-sm text-gray-500">
        No traces yet — run the workflow.
      </div>
    )
  }

  const sorted = [...traces].sort((a, b) => a.created_at.localeCompare(b.created_at))

  return (
    <ol className="relative space-y-4 border-l-2 border-gray-200 pl-6">
      {sorted.map((run) => (
        <li key={run.agent_run_id} className="relative">
          <span
            className={`absolute top-3 -left-[31px] flex h-3 w-3 items-center justify-center rounded-full border-2 border-white ${dotColor(run.status)}`}
            aria-hidden
          />
          <div className="mb-1 flex items-center gap-2 text-xs text-gray-500">
            <time dateTime={run.created_at}>{formatTime(run.created_at)}</time>
            <span className="font-mono text-[10px] text-gray-400">{run.agent_run_id}</span>
          </div>
          <AgentRunCard run={run} />
        </li>
      ))}
    </ol>
  )
}

function dotColor(status: string): string {
  switch (status) {
    case 'success':
      return 'bg-green-500'
    case 'failed':
      return 'bg-red-500'
    case 'running':
      return 'bg-blue-500'
    case 'skipped':
      return 'bg-gray-300'
    default:
      return 'bg-gray-400'
  }
}
