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
  const inputSummary = typeof run.input.decision_summary === 'string' ? run.input.decision_summary : null
  const outputSummary = typeof run.output.decision_summary === 'string' ? run.output.decision_summary : null
  const parseStatus = isRenderablePreview(run.output.parse_status) ? formatTraceValue(run.output.parse_status) : null
  const promptPreview = run.output.prompt_preview ?? run.input.prompt_preview
  const llmOutputPreview = run.output.llm_output_preview
  const reworkTarget = typeof run.output.rework_target === 'string' ? run.output.rework_target : null
  const reworkHints = Array.isArray(run.output.rework_hints)
    ? run.output.rework_hints.filter((hint): hint is string => typeof hint === 'string')
    : []
  const reworkHintsUsed = Array.isArray(run.output.rework_hints_used)
    ? run.output.rework_hints_used.filter((hint): hint is string => typeof hint === 'string')
    : []
  const totalTokens = typeof run.token_usage?.total_tokens === 'number'
    ? run.token_usage.total_tokens
    : 0

  return (
    <article className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <h3 className="font-semibold text-gray-900">{run.agent_name}</h3>
          <AgentStatusBadge status={run.status} />
          {run.retry_count > 0 && (
            <span className="inline-flex items-center rounded border border-orange-200 bg-orange-50 px-2 py-0.5 text-xs font-medium text-orange-700">
              已重试 {run.retry_count} 次
            </span>
          )}
        </div>
        <div className="flex items-center gap-3 text-xs text-gray-500">
          <span>{run.latency_ms}ms</span>
          <span>约 {totalTokens.toLocaleString()} tokens</span>
        </div>
      </header>

      {(inputSummary || outputSummary || parseStatus || reworkTarget || reworkHints.length > 0 || reworkHintsUsed.length > 0) && (
        <div className="mt-3 grid gap-2 rounded-md border border-blue-100 bg-blue-50/70 p-3 text-xs text-blue-950 md:grid-cols-2">
          {inputSummary && (
            <TraceFact label="为什么运行" value={inputSummary} />
          )}
          {outputSummary && (
            <TraceFact label="执行结果" value={outputSummary} />
          )}
          {parseStatus && (
            <TraceFact label="解析状态" value={parseStatus} />
          )}
          {reworkTarget && (
            <TraceFact label="打回目标" value={reworkTarget} />
          )}
          {reworkHints.length > 0 && (
            <TraceList title="重做提示" items={reworkHints} runId={run.agent_run_id} itemKey="hint" />
          )}
          {reworkHintsUsed.length > 0 && (
            <TraceList title="已使用提示" items={reworkHintsUsed} runId={run.agent_run_id} itemKey="used-hint" />
          )}
        </div>
      )}

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
            QA {qa.passed ? '通过' : '未通过'} - 评分 {qa.score}/100
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
                  还有 {qa.issues.length - 3} 个问题（见报告 QA 页签）
                </li>
              )}
            </ul>
          )}
        </div>
      )}

      {run.error_message && (
        <div className="mt-3 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          <span className="font-semibold">错误： </span>
          {run.error_message}
        </div>
      )}

      {isRenderablePreview(promptPreview) && (
        <PreviewBlock title="Prompt 预览" value={promptPreview} />
      )}

      {isRenderablePreview(llmOutputPreview) && (
        <PreviewBlock title="LLM 输出预览" value={llmOutputPreview} />
      )}

      <details className="mt-3 rounded border border-gray-200 bg-gray-50">
        <summary className="cursor-pointer select-none px-3 py-2 text-xs font-medium text-gray-700 hover:bg-gray-100">
          输入
        </summary>
        <pre className="max-h-60 overflow-auto rounded-b border-t border-gray-200 bg-gray-50 p-3 text-xs leading-relaxed text-gray-700">
          {safeStringify(run.input)}
        </pre>
      </details>

      <details className="mt-2 rounded border border-gray-200 bg-gray-50">
        <summary className="cursor-pointer select-none px-3 py-2 text-xs font-medium text-gray-700 hover:bg-gray-100">
          输出
        </summary>
        <pre className="max-h-60 overflow-auto rounded-b border-t border-gray-200 bg-gray-50 p-3 text-xs leading-relaxed text-gray-700">
          {safeStringify(run.output)}
        </pre>
      </details>
    </article>
  )
}

function TraceFact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="font-semibold text-blue-900">{label}</p>
      <p className="mt-0.5 leading-relaxed">{value}</p>
    </div>
  )
}

function TraceList({ title, items, runId, itemKey }: { title: string; items: string[]; runId: string; itemKey: string }) {
  return (
    <div className="md:col-span-2">
      <p className="font-semibold text-blue-900">{title}</p>
      <ul className="mt-1 list-disc space-y-0.5 pl-4">
        {items.map((item, index) => (
          <li key={`${runId}-${itemKey}-${index}`}>{item}</li>
        ))}
      </ul>
    </div>
  )
}

function PreviewBlock({ title, value }: { title: string; value: unknown }) {
  return (
    <details className="mt-3 rounded border border-indigo-100 bg-indigo-50/70">
      <summary className="cursor-pointer select-none px-3 py-2 text-xs font-medium text-indigo-800 hover:bg-indigo-100/70">
        {title}
      </summary>
      <pre className="max-h-44 overflow-auto rounded-b border-t border-indigo-100 p-3 text-xs leading-relaxed text-indigo-900">
        {typeof value === 'string' ? value : safeStringify(value)}
      </pre>
    </details>
  )
}

function isRenderablePreview(value: unknown): boolean {
  if (typeof value === 'string') return value.trim().length > 0
  if (value && typeof value === 'object') return Object.keys(value).length > 0
  return false
}

function extractQAResult(run: AgentRun): QAResult | null {
  if (!run.agent_name.includes('QA')) return null
  const out = run.output as Partial<QAResult>
  if (typeof out?.passed === 'boolean' && typeof out?.score === 'number') {
    return {
      passed: out.passed,
      score: out.score,
      issues: Array.isArray(out.issues) ? out.issues : [],
    }
  }
  return null
}

function formatTraceValue(value: unknown): string {
  if (typeof value === 'string') return value
  return safeStringify(value)
}

function safeStringify(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}
