import type { AgentRun } from '@/lib/types'

interface QAReworkStoryProps {
  traces: AgentRun[]
}

interface StoryStep {
  title: string
  detail: string
  tone: 'neutral' | 'warning' | 'success'
}

export function QAReworkStory({ traces }: QAReworkStoryProps) {
  const steps = buildReworkSteps(traces)
  if (steps.length === 0) return null

  return (
    <section className="rounded-xl border border-amber-200 bg-gradient-to-br from-amber-50 to-white p-4 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold tracking-wider text-amber-700 uppercase">
            QA 闭环演示
          </p>
          <h2 className="mt-1 text-base font-semibold text-gray-900">
            真实打回 → 重采 → 复检通过
          </h2>
        </div>
        <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-800">
          {steps.length} 步可追溯
        </span>
      </div>
      <ol className="mt-4 grid gap-3 md:grid-cols-5">
        {steps.map((step, index) => (
          <li key={`${step.title}-${index}`} className="relative rounded-lg border border-white bg-white/80 p-3 shadow-sm">
            <span className={`inline-flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold ${stepToneClass(step.tone)}`}>
              {index + 1}
            </span>
            <h3 className="mt-2 text-sm font-semibold text-gray-900">{step.title}</h3>
            <p className="mt-1 text-xs leading-relaxed text-gray-600">{step.detail}</p>
          </li>
        ))}
      </ol>
    </section>
  )
}

function buildReworkSteps(traces: AgentRun[]): StoryStep[] {
  const sorted = [...traces].sort((a, b) => a.created_at.localeCompare(b.created_at))
  const qaRuns = sorted.filter((run) => run.agent_name.includes('QA'))
  const failedQa = qaRuns.find((run) => run.output.passed === false)
  const passedQaAfterFailure = failedQa
    ? qaRuns.find((run) => run.created_at > failedQa.created_at && run.output.passed === true)
    : undefined
  const routerRun = sorted.find(
    (run) =>
      run.agent_name === 'WorkflowRouter' &&
      run.output.route === 'rework' &&
      (!failedQa || run.created_at > failedQa.created_at)
  )

  if (!failedQa || !passedQaAfterFailure || !routerRun) return []

  const collectorBeforeFailure = [...sorted]
    .filter((run) => run.agent_name.includes('Collector') && run.created_at < failedQa.created_at)
    .pop()
  const collectorAfterRouter = sorted.find(
    (run) => run.agent_name.includes('Collector') && run.created_at > routerRun.created_at
  )

  const target = typeof routerRun.output.rework_target === 'string'
    ? routerRun.output.rework_target
    : 'upstream agent'
  const firstIssue = Array.isArray(failedQa.output.issues) ? failedQa.output.issues[0] : null
  const issueMessage = isIssueLike(firstIssue) ? firstIssue.message : 'QA detected a blocking issue.'
  const initialNote = typeof collectorBeforeFailure?.output.demo_rework_note === 'string'
    ? collectorBeforeFailure.output.demo_rework_note
    : ''
  const usedHintCount = Array.isArray(collectorAfterRouter?.output.rework_hints_used)
    ? collectorAfterRouter.output.rework_hints_used.length
    : 0

  return [
    {
      title: '首次采集',
      detail: initialNote || 'Collector produced initial evidence for QA review.',
      tone: 'neutral',
    },
    {
      title: 'QA 未通过',
      detail: issueMessage,
      tone: 'warning',
    },
    {
      title: '路由打回',
      detail: `WorkflowRouter selected ${target} and attached repair hints.`,
      tone: 'warning',
    },
    {
      title: '重做修复',
      detail: usedHintCount > 0
        ? `Collector reran with ${usedHintCount} hint(s).`
        : 'Target agent reran with QA feedback.',
      tone: 'neutral',
    },
    {
      title: '复检通过',
      detail: `Final QA score: ${passedQaAfterFailure.output.score ?? 'passed'}/100.`,
      tone: 'success',
    },
  ]
}

function isIssueLike(value: unknown): value is { message: string } {
  return Boolean(value && typeof value === 'object' && 'message' in value && typeof value.message === 'string')
}

function stepToneClass(tone: StoryStep['tone']): string {
  if (tone === 'success') return 'bg-green-100 text-green-800'
  if (tone === 'warning') return 'bg-red-100 text-red-800'
  return 'bg-blue-100 text-blue-800'
}
