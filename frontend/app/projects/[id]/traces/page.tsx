'use client'

/**
 * Trace timeline page.
 *
 * Renders the full audit trail for a project — every Agent invocation
 * with input, output, latency, and retries. Polls every 2s while the
 * project is running so new traces appear without a manual refresh.
 */

import Link from 'next/link'
import { use } from 'react'
import { useQuery } from '@tanstack/react-query'

import { api } from '@/lib/api'
import type { AgentRun, ProjectResponse, QAIssue, QATraceOutput } from '@/lib/types'
import { TraceTimeline } from '@/components/trace-panel/TraceTimeline'

const POLL_MS = 2000

interface PageProps {
  params: Promise<{ id: string }>
}

// ---------------------------------------------------------------------------
// JSON export
// ---------------------------------------------------------------------------

function exportTraceJSON(
  projectId: string,
  traces: AgentRun[],
  projectData?: ProjectResponse
) {
  const payload: Record<string, unknown> = {
    project_id: projectId,
    exported_at: new Date().toISOString(),
    trace_count: traces.length,
  }
  if (projectData) {
    payload.industry = projectData.industry
    payload.status = projectData.status
    if (projectData.data_mode) payload.data_mode = projectData.data_mode
  }
  payload.traces = traces

  const blob = new Blob([JSON.stringify(payload, null, 2)], {
    type: 'application/json;charset=utf-8',
  })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${projectId}_traces.json`
  a.click()
  URL.revokeObjectURL(url)
}

// ---------------------------------------------------------------------------
// Markdown export helpers
// ---------------------------------------------------------------------------

function fmtTokens(usage: AgentRun['token_usage'] | undefined): string {
  if (!usage) return 'n/a'
  return `prompt=${usage.prompt_tokens} completion=${usage.completion_tokens} total=${usage.total_tokens}`
}

function extractQAFromTraces(traces: AgentRun[]): (QATraceOutput & { found: true }) | { found: false } {
  const qaRun = [...traces].reverse().find((t) => t.agent_name.includes('QA'))
  if (!qaRun) return { found: false }
  const out = qaRun.output as Partial<QATraceOutput>
  if (typeof out?.passed !== 'boolean' || typeof out?.score !== 'number') return { found: false }
  return {
    found: true,
    passed: out.passed,
    score: out.score,
    issues: out.issues ?? [],
    issue_count: out.issue_count ?? (out.issues?.length ?? 0),
    high_severity_count: out.high_severity_count ?? 0,
    medium_severity_count: out.medium_severity_count ?? 0,
    low_severity_count: out.low_severity_count ?? 0,
    blocking_issue_count: out.blocking_issue_count ?? 0,
    advisory_count: out.advisory_count ?? 0,
  }
}

function buildQAMarkdown(qa: ReturnType<typeof extractQAFromTraces>): string {
  if (!qa.found) return ''

  const issues = (qa.issues ?? []) as QAIssue[]
  const blockingIssues = issues.filter((i) => i.severity !== 'low')
  const advisories = issues.filter((i) => i.severity === 'low')

  const lines: string[] = [
    '',
    '---',
    '',
    '## QA Summary',
    '',
    `**Score:** ${qa.score}/100 · **Verdict:** ${qa.passed ? 'Passed ✓' : 'Failed ✗'}`,
    `**Blocking issues:** ${qa.blocking_issue_count} · **Advisories:** ${qa.advisory_count}`,
  ]

  if (blockingIssues.length > 0) {
    lines.push('', '### Blocking Issues', '')
    blockingIssues.forEach((issue, i) => {
      lines.push(
        `#### Issue ${i + 1} — ${issue.severity}`,
        '',
        `- **Type:** ${issue.issue_type}`,
        `- **Agent:** ${issue.target_agent}`,
        `- **Message:** ${issue.message}`,
      )
      if (issue.suggested_action) {
        lines.push(`- **Action:** ${issue.suggested_action}`)
      }
      lines.push('')
    })
  }

  if (advisories.length > 0) {
    lines.push('### Advisories', '')
    advisories.forEach((issue, i) => {
      lines.push(
        `#### Advisory ${i + 1}`,
        '',
        `- **Type:** ${issue.issue_type}`,
        `- **Agent:** ${issue.target_agent}`,
        `- **Message:** ${issue.message}`,
      )
      if (issue.suggested_action) {
        lines.push(`- **Action:** ${issue.suggested_action}`)
      }
      lines.push('')
    })
  }

  return lines.join('\n')
}

function exportTraceMarkdown(
  projectId: string,
  traces: AgentRun[],
  projectData?: ProjectResponse
) {
  const lines: string[] = [
    '# Agent Trace Export',
    '',
    `**Project:** ${projectId}`,
    `**Exported:** ${new Date().toISOString()}`,
  ]

  if (projectData) {
    if (projectData.industry) lines.push(`**Industry:** ${projectData.industry}`)
    if (projectData.status) lines.push(`**Status:** ${projectData.status}`)
    if (projectData.data_mode) lines.push(`**Data mode:** ${projectData.data_mode}`)
  }

  lines.push(`**Traces:** ${traces.length}`, '')

  for (const trace of traces) {
    lines.push(
      '---',
      '',
      `## ${trace.agent_name} — ${trace.status}`,
      '',
      `**Run ID:** ${trace.agent_run_id} · **Latency:** ${trace.latency_ms} ms · **Retries:** ${trace.retry_count}`,
      `**Token usage:** ${fmtTokens(trace.token_usage)}`,
      `**Created:** ${trace.created_at}`,
    )

    if (trace.error_message) {
      lines.push('', `> **Error:** ${trace.error_message}`)
    }

    lines.push(
      '',
      '### Input',
      '',
      '```json',
      JSON.stringify(trace.input, null, 2),
      '```',
      '',
      '### Output',
      '',
      '```json',
      JSON.stringify(trace.output, null, 2),
      '```',
      '',
    )
  }

  const qa = extractQAFromTraces(traces)
  lines.push(buildQAMarkdown(qa))

  const blob = new Blob([lines.join('\n')], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${projectId}_traces.md`
  a.click()
  URL.revokeObjectURL(url)
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function TracesPage({ params }: PageProps) {
  const { id } = use(params)

  const projectQuery = useQuery({
    queryKey: ['project', id],
    queryFn: () => api.getProject(id),
    refetchInterval: (query) =>
      query.state.data?.status === 'running' ? POLL_MS : false,
  })

  const isRunning = projectQuery.data?.status === 'running'
  const reportAvailable =
    projectQuery.data?.status === 'completed' ||
    projectQuery.data?.status === 'qa_failed'

  const tracesQuery = useQuery({
    queryKey: ['traces', id],
    queryFn: () => api.getTraces(id),
    refetchInterval: isRunning ? POLL_MS : false,
    enabled: !!projectQuery.data,
  })

  const traces = tracesQuery.data?.traces ?? []

  return (
    <div className="space-y-6">
      <nav className="text-sm text-gray-500">
        <Link href="/projects" className="hover:text-gray-900">
          Projects
        </Link>
        <span className="mx-1">/</span>
        <Link href={`/projects/${id}`} className="hover:text-gray-900">
          {projectQuery.data?.industry ?? id}
        </Link>
        <span className="mx-1">/</span>
        <span className="text-gray-900">Traces</span>
      </nav>

      <header className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs font-medium uppercase tracking-wider text-blue-700">
              Trace Timeline
            </p>
            <h1 className="mt-1 text-2xl font-semibold text-gray-900">
              Agent execution log
            </h1>
            <p className="mt-1 text-sm text-gray-600">
              Each entry corresponds to one Agent invocation persisted in the
              backend <code className="font-mono text-xs">agent_runs</code> table.
              Expand input/output to inspect the payloads.
            </p>
          </div>
          {isRunning && (
            <span className="flex shrink-0 items-center gap-1.5 rounded-full border border-blue-200 bg-blue-50 px-3 py-1 text-xs font-medium text-blue-700">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-blue-500" />
              Live · polling every 2s
            </span>
          )}
        </div>
        <div className="mt-3 flex items-center gap-3 text-xs text-gray-500">
          <span>{traces.length} runs</span>
          <span>Project: {projectQuery.data?.industry ?? id}</span>
        </div>
      </header>

      {tracesQuery.isLoading && (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className="h-32 animate-pulse rounded-lg border border-gray-200 bg-white"
            />
          ))}
        </div>
      )}

      {tracesQuery.isError && (
        <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          Failed to load traces.{' '}
          {tracesQuery.error instanceof Error
            ? tracesQuery.error.message
            : 'Unknown error.'}
        </div>
      )}

      {!tracesQuery.isLoading && !tracesQuery.isError && (
        <TraceTimeline traces={traces} />
      )}

      <div className="flex flex-wrap gap-3">
        <Link
          href={`/projects/${id}`}
          className="rounded-md border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
        >
          &larr; Back to project
        </Link>
        {reportAvailable && (
          <Link
            href={`/projects/${id}/report`}
            className="rounded-md border border-blue-200 bg-blue-50 px-4 py-2 text-sm font-medium text-blue-700 transition-colors hover:bg-blue-100"
          >
            View Report &rarr;
          </Link>
        )}
        {traces.length > 0 && (
          <>
            <button
              type="button"
              onClick={() => exportTraceJSON(id, traces, projectQuery.data ?? undefined)}
              className="rounded-md border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
            >
              Export Trace JSON
            </button>
            <button
              type="button"
              onClick={() => exportTraceMarkdown(id, traces, projectQuery.data ?? undefined)}
              className="rounded-md border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
            >
              Export Trace Markdown
            </button>
          </>
        )}
      </div>
    </div>
  )
}
