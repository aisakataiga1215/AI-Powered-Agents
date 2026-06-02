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
import { TraceTimeline } from '@/components/trace-panel/TraceTimeline'

const POLL_MS = 2000

interface PageProps {
  params: Promise<{ id: string }>
}

export default function TracesPage({ params }: PageProps) {
  const { id } = use(params)

  const projectQuery = useQuery({
    queryKey: ['project', id],
    queryFn: () => api.getProject(id),
    refetchInterval: (query) =>
      query.state.data?.status === 'running' ? POLL_MS : false,
  })

  const isRunning = projectQuery.data?.status === 'running'

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

      <div className="flex gap-3">
        <Link
          href={`/projects/${id}`}
          className="rounded-md border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
        >
          &larr; Back to project
        </Link>
      </div>
    </div>
  )
}
