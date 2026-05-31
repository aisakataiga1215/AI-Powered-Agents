import { cn } from '@/lib/cn'

const STATUS_COLORS: Record<string, string> = {
  success: 'bg-green-100 text-green-800 border-green-200',
  failed: 'bg-red-100 text-red-800 border-red-200',
  running: 'bg-blue-100 text-blue-800 border-blue-200',
  skipped: 'bg-gray-100 text-gray-500 border-gray-200',
}

interface AgentStatusBadgeProps {
  status: string
  className?: string
}

export function AgentStatusBadge({ status, className }: AgentStatusBadgeProps) {
  const cls = STATUS_COLORS[status] ?? 'bg-gray-100 text-gray-500 border-gray-200'
  return (
    <span
      className={cn(
        'inline-flex items-center rounded border px-2 py-0.5 text-xs font-medium',
        cls,
        className
      )}
    >
      {status}
    </span>
  )
}
