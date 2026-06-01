'use client'

/**
 * Project execution page.
 *
 * Shows project metadata, lets the user trigger the LangGraph workflow,
 * polls project + traces while the run is in flight, and renders the
 * AgentDAG with live status.
 */

import Link from 'next/link'
import { use, useMemo } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/lib/api'
import { cn } from '@/lib/cn'
import { formatDateTime } from '@/lib/formatDateTime'
import type { AgentRun, ProjectStatus } from '@/lib/types'
import { AgentDAG } from '@/components/agent-flow/AgentDAG'

const POLL_INTERVAL_MS = 3000

const STATUS_PILLS: Record<ProjectStatus, string> = {
  created: 'bg-gray-100 text-gray-700 border-gray-200',
  running: 'bg-blue-50 text-blue-700 border-blue-200',
  completed: 'bg-green-50 text-green-700 border-green-200',
  qa_failed: 'bg-orange-50 text-orange-700 border-orange-200',
  failed: 'bg-red-50 text-red-700 border-red-200',
}

interface PageProps {
  params: Promise<{ id: string }>
}

export default function ProjectExecutionPage({ params }: PageProps) {
  const { id } = use(params)
  const queryClient = useQueryClient()

  const projectQuery = useQuery({
    queryKey: ['project', id],
    queryFn: () => api.getProject(id),
    refetchInterval: (query) => (query.state.data?.status === 'running' ? POLL_INTERVAL_MS : false),
  })

  const isRunning = projectQuery.data?.status === 'running'

  const tracesQuery = useQuery({
    queryKey: ['traces', id],
    queryFn: () => api.getTraces(id),
    refetchInterval: isRunning ? POLL_INTERVAL_MS : false,
    enabled: !!projectQuery.data,
  })

  const runMutation = useMutation({
    mutationFn: () => api.runProject(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project', id] })
      queryClient.invalidateQueries({ queryKey: ['traces', id] })
    },
  })

  const traces: AgentRun[] = useMemo(() => tracesQuery.data?.traces ?? [], [tracesQuery.data])
  const reportAvailable =
    projectQuery.data?.status === 'completed' || projectQuery.data?.status === 'qa_failed'

  const latestPerAgent = useMemo(() => {
    const map = new Map<string, AgentRun>()
    for (const run of traces) {
      const key = run.agent_name
      const existing = map.get(key)
      if (!existing || run.created_at > existing.created_at) {
        map.set(key, run)
      }
    }
    return Array.from(map.values())
  }, [traces])

  return (
    <div className="space-y-6">
      <Breadcrumb industry={projectQuery.data?.industry} id={id} />

      {projectQuery.isLoading && <ProjectSkeleton />}

      {projectQuery.isError && (
        <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          Failed to load project.{' '}
          {projectQuery.error instanceof Error ? projectQuery.error.message : 'Unknown error.'}
        </div>
      )}

      {projectQuery.data && (
        <section className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-xs font-medium tracking-wider text-blue-700 uppercase">Project</p>
              <h1 className="mt-1 text-2xl font-semibold text-gray-900">
                {projectQuery.data.industry}
              </h1>
              <p className="mt-1 font-mono text-xs text-gray-400">{id}</p>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <span
                  className={cn(
                    'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium',
                    STATUS_PILLS[projectQuery.data.status]
                  )}
                >
                  {isRunning && (
                    <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-blue-500" />
                  )}
                  {projectQuery.data.status.replace('_', ' ')}
                </span>
                {projectQuery.data.goals.map((g) => (
                  <span key={g} className="rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-600">
                    {g}
                  </span>
                ))}
              </div>
              <p className="mt-2 text-xs text-gray-500">
                Created {formatDateTime(projectQuery.data.created_at)} · Updated{' '}
                {formatDateTime(projectQuery.data.updated_at)}
              </p>
            </div>
            <div className="flex flex-col items-end gap-2">
              <button
                type="button"
                onClick={() => runMutation.mutate()}
                disabled={projectQuery.data.status !== 'created' || runMutation.isPending}
                className={cn(
                  'inline-flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium text-white transition-colors',
                  projectQuery.data.status === 'created' && !runMutation.isPending
                    ? 'bg-blue-600 hover:bg-blue-700'
                    : 'cursor-not-allowed bg-gray-300'
                )}
              >
                {runMutation.isPending && (
                  <span
                    className="h-3 w-3 animate-spin rounded-full border-2 border-white border-t-transparent"
                    aria-hidden
                  />
                )}
                {runMutation.isPending ? 'Starting...' : 'Run workflow'}
              </button>
              {projectQuery.data.status !== 'created' && (
                <p className="text-xs text-gray-500">
                  Workflow already triggered for this project.
                </p>
              )}
              {runMutation.isError && (
                <p className="text-xs text-red-600">
                  {runMutation.error instanceof Error
                    ? runMutation.error.message
                    : 'Failed to start workflow.'}
                </p>
              )}
            </div>
          </div>
        </section>
      )}

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold tracking-wider text-gray-700 uppercase">
            Agent workflow
          </h2>
          {isRunning && (
            <span className="text-xs text-blue-700">Workflow running... polling every 3s</span>
          )}
        </div>
        <AgentDAG traces={traces} />
        {latestPerAgent.length > 0 && (
          <ul className="mt-3 grid grid-cols-2 gap-2 text-xs text-gray-600 sm:grid-cols-4">
            {latestPerAgent.map((r) => (
              <li key={r.agent_run_id} className="rounded border border-gray-200 bg-white p-2">
                <div className="font-medium text-gray-800">{r.agent_name}</div>
                <div className="text-gray-500">
                  {r.status} · {r.latency_ms}ms
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="flex flex-wrap gap-3">
        <Link
          href={`/projects/${id}/traces`}
          className="inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-4 py-3 text-sm font-medium text-gray-900 transition-colors hover:bg-gray-50"
        >
          <span className="text-blue-600">Trace timeline</span>
          <span className="text-gray-400">Inspect inputs, outputs, latency, and retries</span>
        </Link>
        {reportAvailable ? (
          <Link
            href={`/projects/${id}/report`}
            className="inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-4 py-3 text-sm font-medium text-gray-900 transition-colors hover:bg-gray-50"
          >
            <span className="text-blue-600">Final report</span>
            <span className="text-gray-400">View structured output and citations</span>
          </Link>
        ) : (
          <span
            className="inline-flex items-center gap-2 rounded-lg border border-dashed border-gray-200 bg-gray-50 px-4 py-3 text-sm font-medium text-gray-400"
            title="Report becomes available once the workflow finishes."
          >
            <span>Final report</span>
            <span>(available after workflow finishes)</span>
          </span>
        )}
      </section>
    </div>
  )
}

function Breadcrumb({ industry, id }: { industry?: string; id: string }) {
  return (
    <nav className="text-sm text-gray-500">
      <Link href="/projects" className="hover:text-gray-900">
        Projects
      </Link>
      <span className="mx-1">/</span>
      <span className="text-gray-900">{industry ?? id}</span>
    </nav>
  )
}

function ProjectSkeleton() {
  return (
    <div className="space-y-3">
      <div className="h-24 animate-pulse rounded-xl border border-gray-200 bg-white" />
      <div className="h-64 animate-pulse rounded-xl border border-gray-200 bg-white" />
    </div>
  )
}
