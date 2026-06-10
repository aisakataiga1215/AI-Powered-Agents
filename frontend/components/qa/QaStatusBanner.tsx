import type { ProjectStatus } from '@/lib/types'

interface QaStatusBannerProps {
  status: ProjectStatus
  droppedCount?: number
}

export function QaStatusBanner({ status, droppedCount }: QaStatusBannerProps) {
  if (status === 'qa_failed') {
    return (
      <div className="rounded-md border border-orange-200 bg-orange-50 p-4 text-sm text-orange-900">
        <span className="font-semibold">⚠ 部分报告 — QA 未通过</span>
        <p className="mt-1 text-xs">
          这份报告没有通过质量检查，部分来源缺失或较弱。
          {droppedCount
            ? ` ${droppedCount} 个竞品未能完整分析。`
            : ''}{' '}
          请谨慎使用结果，并对照引用来源核验结论。
        </p>
      </div>
    )
  }
  if (status === 'failed') {
    return (
      <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-900">
        <span className="font-semibold">✗ 工作流失败</span>
        <p className="mt-1 text-xs">
          分析工作流遇到错误，报告可能不完整。
        </p>
      </div>
    )
  }
  return null
}
