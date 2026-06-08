import type { ProjectStatus } from '@/lib/types'

interface QaStatusBannerProps {
  status: ProjectStatus
  droppedCount?: number
}

export function QaStatusBanner({ status, droppedCount }: QaStatusBannerProps) {
  if (status === 'qa_failed') {
    return (
      <div className="rounded-md border border-orange-200 bg-orange-50 p-4 text-sm text-orange-900">
        <span className="font-semibold">⚠ Partial Report — QA Failed</span>
        <p className="mt-1 text-xs">
          This report did not pass quality checks. Some sources are missing or weak.
          {droppedCount
            ? ` ${droppedCount} competitor${droppedCount > 1 ? 's' : ''} could not be fully analysed.`
            : ''}{' '}
          Treat results with caution and verify claims against cited sources.
        </p>
      </div>
    )
  }
  if (status === 'failed') {
    return (
      <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-900">
        <span className="font-semibold">✗ Workflow Failed</span>
        <p className="mt-1 text-xs">
          The analysis workflow encountered an error. This report may be incomplete.
        </p>
      </div>
    )
  }
  return null
}
