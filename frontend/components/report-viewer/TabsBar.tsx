'use client'

/**
 * Tabs — lightweight controlled tabs.
 *
 * Keeps the dependency surface tiny (no Radix). Each tab is a button
 * with `role="tab"` and panels are toggled by `value`.
 */

import { cn } from '@/lib/cn'

export interface TabItem {
  value: string
  label: string
  badge?: React.ReactNode
}

interface TabsProps {
  items: TabItem[]
  value: string
  onChange: (value: string) => void
  className?: string
}

export function TabsBar({ items, value, onChange, className }: TabsProps) {
  return (
    <div
      role="tablist"
      className={cn(
        'flex gap-1 overflow-x-auto border-b border-gray-200',
        className
      )}
    >
      {items.map((item) => {
        const active = item.value === value
        return (
          <button
            key={item.value}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(item.value)}
            className={cn(
              'flex shrink-0 items-center gap-2 border-b-2 px-3 py-2 text-sm transition-colors',
              active
                ? 'border-blue-600 font-medium text-blue-700'
                : 'border-transparent text-gray-600 hover:border-gray-300 hover:text-gray-900'
            )}
          >
            {item.label}
            {item.badge}
          </button>
        )
      })}
    </div>
  )
}
