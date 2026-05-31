'use client'

import Link from 'next/link'
import { useQuery } from '@tanstack/react-query'

import { api } from '@/lib/api'
import type { ProjectResponse, ProjectStatus } from '@/lib/types'
import { cn } from '@/lib/cn'

interface StatusStyle {
  bg: string
  text: string
  border: string
  pulse?: boolean
}

const STATUS_STYLES: Record<ProjectStatus, StatusStyle> = {
  created: {
    bg: 'bg-gray-100',
    text: 'text-gray-600',
    border: 'border-gray-200',
  },
  running: {
    bg: 'bg-blue-50',
    text: 'text-blue-700',
    border: 'border-blue-200',
    pulse: true,
  },
  completed: {
    bg: 'bg-green-50',
    text: 'text-green-700',
    border: 'border-green-200',
  },
  qa_failed: {
    bg: 'bg-orange-50',
    text: 'text-orange-700',
    border: 'border-orange-200',
  },
  failed: {
    bg: 'bg-red-50',
    text: 'text-red-700',
    border: 'border-red-200',
  },
}

function StatusBadge({ status }: { status: ProjectStatus }) {
  const style = STATUS_STYLES[status] ?? STATUS_STYLES.created
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium',
        style.bg,
        style.text,
        style.border
      )}
    >
      {style.pulse && (
        <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-blue-500" />
      )}
      {status.replace('_', ' ')}
    </span>
  )
}

function formatDate(iso: string): string {
  if (!iso) return ''
  try {
    const d = new Date(iso)
    if (Number.isNaN(d.getTime())) return iso
    return d.toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return iso
  }
}

export default function ProjectsListPage() {
  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ['projects'],
    queryFn: () => api.listProjects(),
    refetchOnMount: 'always',
  })

  return (
    <div>
      <header className="mb-6 flex items-end justify-between">
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-blue-700">
            Workspace
          </p>
          <h1 className="mt-1 text-3xl font-semibold text-gray-900">
            Projects
          </h1>
          <p className="mt-1 text-sm text-gray-600">
            All competitive analysis runs created in this workspace.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => refetch()}
            className="text-sm text-gray-600 hover:text-gray-900"
            disabled={isFetching}
          >
            {isFetching ? 'Refreshing...' : 'Refresh'}
          </button>
          <Link
            href="/"
            className="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-blue-700"
          >
            New project
          </Link>
        </div>
      </header>

      {isLoading && (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className="h-20 animate-pulse rounded-lg border border-gray-200 bg-white"
            />
          ))}
        </div>
      )}

      {isError && (
        <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          Failed to load projects.{' '}
          {error instanceof Error ? error.message : 'Unknown error.'}
        </div>
      )}

      {!isLoading && !isError && data && data.length === 0 && (
        <EmptyState />
      )}

      {!isLoading && !isError && data && data.length > 0 && (
        <ProjectsTable projects={data} />
      )}
    </div>
  )
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-gray-300 bg-white p-12 text-center">
      <div className="mb-3 inline-block rounded-full bg-blue-50 p-3 text-blue-600">
        <svg
          aria-hidden
          xmlns="http://www.w3.org/2000/svg"
          width="24"
          height="24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M5 5h14v3H5zm0 6h14v3H5zm0 6h14v2H5z"
          />
        </svg>
      </div>
      <h2 className="mb-1 text-lg font-semibold text-gray-900">
        No projects yet
      </h2>
      <p className="mb-4 max-w-sm text-sm text-gray-600">
        Create your first competitive analysis project to see the agent
        workflow in action.
      </p>
      <Link
        href="/"
        className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700"
      >
        Create your first project
      </Link>
    </div>
  )
}

function ProjectsTable({ projects }: { projects: ProjectResponse[] }) {
  return (
    <div className="overflow-hidden rounded-xl border border-gray-200 bg-white">
      <table className="min-w-full divide-y divide-gray-200">
        <thead className="bg-gray-50">
          <tr>
            <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
              Industry
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
              Status
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
              Goals
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
              Created
            </th>
            <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">
              <span className="sr-only">Open</span>
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100 bg-white">
          {projects.map((project) => (
            <tr key={project.project_id} className="hover:bg-gray-50">
              <td className="px-4 py-3">
                <div className="text-sm font-medium text-gray-900">
                  {project.industry || 'Untitled'}
                </div>
                <div className="font-mono text-xs text-gray-400">
                  {project.project_id}
                </div>
              </td>
              <td className="px-4 py-3">
                <StatusBadge status={project.status} />
              </td>
              <td className="px-4 py-3">
                <div className="flex flex-wrap gap-1">
                  {project.goals.length === 0 && (
                    <span className="text-xs text-gray-400">—</span>
                  )}
                  {project.goals.map((g) => (
                    <span
                      key={g}
                      className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-600"
                    >
                      {g}
                    </span>
                  ))}
                </div>
              </td>
              <td className="px-4 py-3 text-sm text-gray-600">
                {formatDate(project.created_at)}
              </td>
              <td className="px-4 py-3 text-right">
                <Link
                  href={`/projects/${project.project_id}`}
                  className="text-sm font-medium text-blue-700 hover:text-blue-800"
                >
                  Open &rarr;
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
