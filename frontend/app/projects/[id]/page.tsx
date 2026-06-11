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
import type { AgentRun, ProjectStatus, QAIssue, QATraceOutput, WorkflowJob } from '@/lib/types'
import { AgentDAG } from '@/components/agent-flow/AgentDAG'

const POLL_INTERVAL_MS = 3000

const STATUS_PILLS: Record<ProjectStatus, string> = {
  created: 'bg-gray-100 text-gray-700 border-gray-200',
  running: 'bg-blue-50 text-blue-700 border-blue-200',
  completed: 'bg-green-50 text-green-700 border-green-200',
  qa_failed: 'bg-orange-50 text-orange-700 border-orange-200',
  failed: 'bg-red-50 text-red-700 border-red-200',
}

const STATUS_LABELS: Record<ProjectStatus, string> = {
  created: '待运行',
  running: '运行中',
  completed: '已完成',
  qa_failed: 'QA 未通过',
  failed: '失败',
}

const GOAL_LABELS: Record<string, string> = {
  feature_comparison: '功能对比',
  pricing_analysis: '定价分析',
  user_personas: '用户画像',
  swot: 'SWOT',
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

  const jobsQuery = useQuery({
    queryKey: ['jobs', id],
    queryFn: () => api.getProjectJobs(id),
    refetchInterval: isRunning ? POLL_INTERVAL_MS : false,
    enabled: !!projectQuery.data,
  })

  const runMutation = useMutation({
    mutationFn: () => api.runProject(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project', id] })
      queryClient.invalidateQueries({ queryKey: ['traces', id] })
      queryClient.invalidateQueries({ queryKey: ['jobs', id] })
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

  const failedRun = useMemo(
    () => [...traces].reverse().find((r) => r.status === 'failed' || r.error_message),
    [traces],
  )
  const latestQA = useMemo(() => extractLatestQA(traces), [traces])

  return (
    <div className="space-y-6">
      <Breadcrumb industry={projectQuery.data?.industry} id={id} />

      {projectQuery.isLoading && <ProjectSkeleton />}

      {projectQuery.isError && (
        <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          项目加载失败。{projectQuery.error instanceof Error ? projectQuery.error.message : '未知错误。'}
        </div>
      )}

      {projectQuery.data && (
        <section className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-xs font-medium tracking-wider text-blue-700 uppercase">项目</p>
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
                  {STATUS_LABELS[projectQuery.data.status] ?? projectQuery.data.status}
                </span>
                {projectQuery.data.goals.map((g) => (
                  <span key={g} className="rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-600">
                    {GOAL_LABELS[g] ?? g}
                  </span>
                ))}
              </div>
              <p className="mt-2 text-xs text-gray-500">
                创建于 {formatDateTime(projectQuery.data.created_at)} · 更新于{' '}
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
                {runMutation.isPending ? '启动中...' : '运行工作流'}
              </button>
              {projectQuery.data.status !== 'created' && (
                <p className="text-xs text-gray-500">
                  该项目已触发工作流。
                </p>
              )}
              {runMutation.isError && (
                <p className="text-xs text-red-600">
                  {runMutation.error instanceof Error
                    ? runMutation.error.message
                    : '工作流启动失败。'}
                </p>
              )}
            </div>
          </div>
        </section>
      )}

      {jobsQuery.data && jobsQuery.data.length > 0 && (
        <WorkflowJobPanel jobs={jobsQuery.data} />
      )}

      {projectQuery.data && ['failed', 'qa_failed'].includes(projectQuery.data.status) && (
        <FailureSummary
          status={projectQuery.data.status}
          failedRun={failedRun}
          qaIssues={latestQA?.issues ?? []}
          qaScore={latestQA?.score}
          projectId={id}
        />
      )}

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold tracking-wider text-gray-700 uppercase">
            Agent 工作流
          </h2>
          {isRunning && (
            <span className="text-xs text-blue-700">工作流运行中，每 3 秒刷新一次</span>
          )}
        </div>
        <AgentDAG traces={traces} projectStatus={projectQuery.data?.status} />
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

      <section className="relative z-10 flex flex-wrap gap-3">
        <Link
          href={`/projects/${id}/traces`}
          className="inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-4 py-3 text-sm font-medium text-gray-900 transition-colors hover:bg-gray-50"
        >
          <span className="text-blue-600">Trace 时间线</span>
          <span className="text-gray-400">查看输入、输出、耗时和重试</span>
        </Link>
        {reportAvailable ? (
          <Link
            href={`/projects/${id}/report`}
            className="inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-4 py-3 text-sm font-medium text-gray-900 transition-colors hover:bg-gray-50"
          >
            <span className="text-blue-600">最终报告</span>
            <span className="text-gray-400">查看结构化输出和引用来源</span>
          </Link>
        ) : (
          <span
            className="inline-flex items-center gap-2 rounded-lg border border-dashed border-gray-200 bg-gray-50 px-4 py-3 text-sm font-medium text-gray-400"
            title="工作流完成后可查看报告。"
          >
            <span>最终报告</span>
            <span>（工作流完成后可用）</span>
          </span>
        )}
      </section>
    </div>
  )
}

function WorkflowJobPanel({ jobs }: { jobs: WorkflowJob[] }) {
  const latest = jobs[0]
  return (
    <section className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold tracking-wider text-gray-700 uppercase">
            Workflow Job
          </h2>
          <p className="mt-1 font-mono text-xs text-gray-400">{latest.job_id}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className={cn('rounded-full border px-2.5 py-0.5 font-medium', jobStatusStyle(latest.status))}>
            {latest.status}
          </span>
          <span className="rounded bg-gray-100 px-2 py-0.5 text-gray-600">
            {latest.backend}
          </span>
          <span className="text-gray-500">attempts {latest.attempts}</span>
        </div>
      </div>
      {latest.error_message && (
        <p className="mt-3 rounded border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
          {latest.error_message}
        </p>
      )}
    </section>
  )
}

function jobStatusStyle(status: WorkflowJob['status']): string {
  switch (status) {
    case 'queued':
      return 'border-gray-200 bg-gray-50 text-gray-700'
    case 'running':
      return 'border-blue-200 bg-blue-50 text-blue-700'
    case 'completed':
      return 'border-green-200 bg-green-50 text-green-700'
    case 'failed':
      return 'border-red-200 bg-red-50 text-red-700'
  }
}

function FailureSummary({
  status,
  failedRun,
  qaIssues,
  qaScore,
  projectId,
}: {
  status: ProjectStatus
  failedRun?: AgentRun
  qaIssues: QAIssue[]
  qaScore?: number
  projectId: string
}) {
  return (
    <section className="rounded-xl border border-orange-200 bg-orange-50 p-5 text-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-semibold text-orange-900">
            {status === 'qa_failed' ? 'QA 未通过，报告需要复核' : '工作流失败'}
          </h2>
          <p className="mt-1 text-orange-800">
            {status === 'qa_failed'
              ? '工作流已生成部分报告，但 QA 发现阻塞问题。'
              : '工作流在生成最终报告前停止。'}
          </p>
        </div>
        {qaScore !== undefined && (
          <span className="rounded-full border border-orange-300 bg-white px-2.5 py-1 text-xs font-semibold text-orange-800">
            QA {qaScore}/100
          </span>
        )}
      </div>

      {failedRun?.error_message && (
        <div className="mt-3 rounded-md border border-orange-200 bg-white px-3 py-2">
          <div className="text-xs font-medium text-orange-700">
            {failedRun.agent_name} 错误
          </div>
          <pre className="mt-1 whitespace-pre-wrap break-words text-xs text-gray-700">
            {failedRun.error_message}
          </pre>
        </div>
      )}

      {qaIssues.length > 0 && (
        <ul className="mt-3 space-y-2">
          {qaIssues.slice(0, 5).map((issue, index) => (
            <li
              key={issue.issue_id ?? index}
              className="rounded-md border border-orange-200 bg-white px-3 py-2 text-xs"
            >
              <span className="font-semibold uppercase text-orange-700">
                {issue.severity}
              </span>
              <span className="ml-2 text-gray-500">
                {issue.target_agent} · {issue.issue_type}
              </span>
              <p className="mt-1 text-gray-800">{issue.message}</p>
              {issue.suggested_action && (
                <p className="mt-1 text-gray-500">建议：{issue.suggested_action}</p>
              )}
            </li>
          ))}
        </ul>
      )}

      <Link
        href={`/projects/${projectId}/traces`}
        className="mt-3 inline-flex rounded-md border border-orange-200 bg-white px-3 py-1.5 text-xs font-medium text-orange-800 hover:bg-orange-100"
      >
        查看完整 Trace
      </Link>
    </section>
  )
}

function extractLatestQA(traces: AgentRun[]): { score: number; issues: QAIssue[] } | undefined {
  const qaRun = [...traces].reverse().find((t) => t.agent_name.includes('QA'))
  if (!qaRun) return undefined
  const out = qaRun.output as Partial<QATraceOutput>
  if (typeof out?.score !== 'number') return undefined
  return {
    score: out.score,
    issues: out.issues ?? [],
  }
}

function Breadcrumb({ industry, id }: { industry?: string; id: string }) {
  return (
    <nav className="text-sm text-gray-500">
      <Link href="/projects" className="hover:text-gray-900">
        项目
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
