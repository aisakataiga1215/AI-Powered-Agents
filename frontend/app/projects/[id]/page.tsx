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
import type { UseMutationResult } from '@tanstack/react-query'

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
  pricing_analysis: '定价模式',
  user_personas: '用户画像',
  user_reviews: '用户评价',
  swot: 'SWOT',
  three_c: '3C',
  aarrr: 'AARRR',
}

const FRAMEWORK_KEYS = new Set(['swot', 'three_c', 'aarrr'])

interface PageProps {
  params: Promise<{ id: string }>
}

export default function ProjectExecutionPage({ params }: PageProps) {
  const { id } = use(params)
  const queryClient = useQueryClient()

  const projectQuery = useQuery({
    queryKey: ['project', id],
    queryFn: () => api.getProject(id),
    refetchInterval: (query) => (query.state.data?.status !== 'created' ? POLL_INTERVAL_MS : false),
    refetchIntervalInBackground: true,
  })

  const isRunning = projectQuery.data?.status === 'running'
  const shouldRefreshWorkflow = projectQuery.data?.status !== 'created'

  const tracesQuery = useQuery({
    queryKey: ['traces', id],
    queryFn: () => api.getTraces(id),
    refetchInterval: shouldRefreshWorkflow ? POLL_INTERVAL_MS : false,
    refetchIntervalInBackground: true,
    enabled: !!projectQuery.data,
  })

  const jobsQuery = useQuery({
    queryKey: ['jobs', id],
    queryFn: () => api.getProjectJobs(id),
    refetchInterval: shouldRefreshWorkflow ? POLL_INTERVAL_MS : false,
    refetchIntervalInBackground: true,
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
        <ProjectHero
          id={id}
          project={projectQuery.data}
          traces={traces}
          latestQA={latestQA}
          isRunning={isRunning}
          runMutation={runMutation}
        />
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

      <section className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs font-semibold tracking-wider text-gray-500 uppercase">
              Agent 工作流
            </p>
            <h2 className="mt-1 text-lg font-semibold text-gray-950">
              编排 DAG 与实时执行状态
            </h2>
          </div>
          {isRunning && (
            <span className="rounded-full border border-blue-200 bg-blue-50 px-3 py-1 text-xs font-medium text-blue-700">
              每 3 秒刷新
            </span>
          )}
        </div>
        <AgentDAG traces={traces} projectStatus={projectQuery.data?.status} />
        {latestPerAgent.length > 0 && (
          <ul className="mt-4 grid gap-2 text-xs text-gray-600 sm:grid-cols-2 lg:grid-cols-4">
            {latestPerAgent.map((r) => (
              <li
                key={r.agent_run_id}
                className="rounded-lg border border-gray-200 bg-gray-50 p-3"
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="truncate font-medium text-gray-900">{r.agent_name}</div>
                  <span className={cn('h-2 w-2 shrink-0 rounded-full', runDotClass(r.status))} />
                </div>
                <div className="mt-1 text-gray-500">
                  {r.status} · {r.latency_ms}ms · retry {r.retry_count}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <ProjectActions id={id} reportAvailable={reportAvailable} />
    </div>
  )
}

function ProjectHero({
  id,
  project,
  traces,
  latestQA,
  isRunning,
  runMutation,
}: {
  id: string
  project: {
    industry: string
    goals: string[]
    analysis_frameworks?: string[]
    status: ProjectStatus
    created_at: string
    updated_at: string
  }
  traces: AgentRun[]
  latestQA?: { score: number; issues: QAIssue[] }
  isRunning: boolean
  runMutation: UseMutationResult<
    { project_id: string; status: string },
    Error,
    void,
    unknown
  >
}) {
  const completedRuns = traces.filter((run) => run.status === 'success').length
  const failedRuns = traces.filter((run) => run.status === 'failed' || run.error_message).length
  const totalTokens = traces.reduce((sum, run) => sum + (run.token_usage?.total_tokens ?? 0), 0)
  const displayTags = uniqueStrings([
    ...project.goals.filter((goal) => !FRAMEWORK_KEYS.has(goal)),
    ...(project.analysis_frameworks ?? []),
  ])

  return (
    <section className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
      <div className="border-b border-gray-200 bg-gray-50 px-6 py-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-xs font-semibold tracking-wider text-blue-700 uppercase">
                竞品分析项目
              </p>
              <span
                className={cn(
                  'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium',
                  STATUS_PILLS[project.status]
                )}
              >
                {isRunning && (
                  <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-blue-500" />
                )}
                {STATUS_LABELS[project.status] ?? project.status}
              </span>
            </div>
            <h1 className="mt-2 truncate text-2xl font-semibold text-gray-950">
              {project.industry}
            </h1>
            <p className="mt-1 font-mono text-xs text-gray-500">{id}</p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              {displayTags.map((goal) => (
                <span
                  key={goal}
                  className="rounded-md border border-gray-200 bg-white px-2.5 py-1 text-xs text-gray-700"
                >
                  {GOAL_LABELS[goal] ?? goal}
                </span>
              ))}
            </div>
          </div>

          <div className="flex flex-col items-start gap-2 sm:items-end">
            <button
              type="button"
              onClick={() => runMutation.mutate()}
              disabled={project.status !== 'created' || runMutation.isPending}
              className={cn(
                'inline-flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium text-white transition-colors',
                project.status === 'created' && !runMutation.isPending
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
            {project.status !== 'created' && (
              <p className="text-xs text-gray-500">该项目已触发工作流。</p>
            )}
            {runMutation.isError && (
              <p className="max-w-xs text-xs text-red-600">
                {runMutation.error instanceof Error
                  ? runMutation.error.message
                  : '工作流启动失败。'}
              </p>
            )}
          </div>
        </div>
      </div>

      <div className="grid gap-px bg-gray-200 md:grid-cols-5">
        <HeroMetric label="成功 Agent" value={completedRuns.toString()} />
        <HeroMetric label="异常 Agent" value={failedRuns.toString()} tone={failedRuns ? 'danger' : 'neutral'} />
        <HeroMetric label="QA 分数" value={latestQA ? `${latestQA.score}/100` : '-'} />
        <HeroMetric label="Token" value={formatCompactNumber(totalTokens)} />
        <HeroMetric
          label="最后更新"
          value={formatDateTime(project.updated_at)}
          compact
        />
      </div>

      <div className="px-6 py-3 text-xs text-gray-500">
        创建于 {formatDateTime(project.created_at)}
      </div>
    </section>
  )
}

function HeroMetric({
  label,
  value,
  tone = 'neutral',
  compact = false,
}: {
  label: string
  value: string
  tone?: 'neutral' | 'danger'
  compact?: boolean
}) {
  return (
    <div className="bg-white px-4 py-3">
      <p className="text-xs text-gray-500">{label}</p>
      <p
        className={cn(
          'mt-1 truncate font-semibold',
          compact ? 'whitespace-normal text-lg leading-snug' : 'text-xl',
          tone === 'danger' ? 'text-red-700' : 'text-gray-950'
        )}
      >
        {value}
      </p>
    </div>
  )
}

function WorkflowJobPanel({ jobs }: { jobs: WorkflowJob[] }) {
  const latest = jobs[0]
  const visibleJobs = jobs.slice(0, 4)
  return (
    <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold tracking-wider text-gray-500 uppercase">
            Background Job
          </p>
          <h2 className="mt-1 text-lg font-semibold text-gray-950">
            任务运行记录
          </h2>
          <p className="mt-1 text-xs text-gray-500">
            记录后台工作流是否已排队、运行、完成或失败，用来避免重复启动并排查重试。
          </p>
          <p className="mt-1 font-mono text-xs text-gray-400">{latest.job_id}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className={cn('rounded-full border px-2.5 py-0.5 font-medium', jobStatusStyle(latest.status))}>
            {jobStatusLabel(latest.status)}
          </span>
          <span className="rounded bg-gray-100 px-2 py-0.5 text-gray-600">
            {latest.backend === 'background_tasks' ? '本机后台任务' : latest.backend}
          </span>
          <span className="text-gray-500">尝试 {latest.attempts} 次</span>
        </div>
      </div>
      <ol className="mt-4 grid gap-3 md:grid-cols-4">
        {visibleJobs.map((job, index) => (
          <li
            key={job.job_id}
            className="rounded-lg border border-gray-200 bg-gray-50 p-3 text-xs"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="font-medium text-gray-900">#{index + 1}</span>
              <span
                className={cn(
                  'rounded-full border px-2 py-0.5 font-medium',
                  jobStatusStyle(job.status)
                )}
              >
                  {jobStatusLabel(job.status)}
              </span>
            </div>
            <p className="mt-2 font-mono text-gray-500">{shortId(job.job_id)}</p>
            <p className="mt-1 text-gray-500">{formatDateTime(job.created_at)}</p>
          </li>
        ))}
      </ol>
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

function jobStatusLabel(status: WorkflowJob['status']): string {
  if (status === 'queued') return '排队中'
  if (status === 'running') return '运行中'
  if (status === 'completed') return '已完成'
  return '失败'
}

function ProjectActions({
  id,
  reportAvailable,
}: {
  id: string
  reportAvailable: boolean
}) {
  return (
    <section className="grid gap-3 md:grid-cols-2">
      <Link
        href={`/projects/${id}/traces`}
        className="group rounded-xl border border-gray-200 bg-white p-4 shadow-sm transition-colors hover:border-blue-200 hover:bg-blue-50"
      >
        <p className="text-sm font-semibold text-gray-950 group-hover:text-blue-800">
          Trace 时间线
        </p>
        <p className="mt-1 text-sm text-gray-500">
          查看每个 Agent 的输入、输出、耗时、Token 和重试。
        </p>
      </Link>
      {reportAvailable ? (
        <Link
          href={`/projects/${id}/report`}
          className="group rounded-xl border border-gray-200 bg-white p-4 shadow-sm transition-colors hover:border-blue-200 hover:bg-blue-50"
        >
          <p className="text-sm font-semibold text-gray-950 group-hover:text-blue-800">
            最终报告
          </p>
          <p className="mt-1 text-sm text-gray-500">
            查看结构化结论、竞品知识 Schema 和引用来源。
          </p>
        </Link>
      ) : (
        <span className="rounded-xl border border-dashed border-gray-200 bg-gray-50 p-4">
          <p className="text-sm font-semibold text-gray-400">最终报告</p>
          <p className="mt-1 text-sm text-gray-400">工作流完成后可查看。</p>
        </span>
      )}
    </section>
  )
}

function runDotClass(status: AgentRun['status']): string {
  if (status === 'success') return 'bg-green-500'
  if (status === 'failed' || status === 'timeout') return 'bg-red-500'
  if (status === 'running') return 'bg-blue-500'
  return 'bg-gray-400'
}

function formatCompactNumber(value: number): string {
  return new Intl.NumberFormat('en', { notation: 'compact' }).format(value)
}

function uniqueStrings(values: string[]): string[] {
  return values.filter((value, index) => value && values.indexOf(value) === index)
}

function shortId(value: string): string {
  if (value.length <= 12) return value
  return `${value.slice(0, 8)}...${value.slice(-4)}`
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
