'use client'

/**
 * SourcePanel — slide-in side drawer for source evidence.
 *
 * Driven by the global `useSourcePanel` store so any citation badge in
 * the report can open it. We render a custom Sheet-style drawer to keep
 * the dependency surface small (no shadcn/Radix required).
 */

import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'

import { api } from '@/lib/api'
import { cn } from '@/lib/cn'
import { useSourcePanel } from '@/lib/store'
import { formatDateTime } from '@/lib/formatDateTime'

const RELIABILITY_STYLE: Record<string, string> = {
  high: 'bg-green-50 text-green-700 border-green-200',
  medium: 'bg-yellow-50 text-yellow-700 border-yellow-200',
  low: 'bg-gray-50 text-gray-600 border-gray-200',
}

export function SourcePanel() {
  const { isOpen, selectedSourceId, closeSource } = useSourcePanel()

  const sourceQuery = useQuery({
    queryKey: ['source', selectedSourceId],
    queryFn: () => api.getSource(selectedSourceId!),
    enabled: !!selectedSourceId && isOpen,
  })

  // Close on Escape
  useEffect(() => {
    if (!isOpen) return
    const handler = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closeSource()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [isOpen, closeSource])

  return (
    <>
      <div
        className={cn(
          'fixed inset-0 z-40 bg-gray-900/30 backdrop-blur-[1px] transition-opacity duration-150',
          isOpen ? 'opacity-100' : 'pointer-events-none opacity-0'
        )}
        onClick={closeSource}
        aria-hidden
      />
      <aside
        className={cn(
          'fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col border-l border-gray-200 bg-white shadow-xl transition-transform duration-200',
          isOpen ? 'translate-x-0' : 'translate-x-full'
        )}
        role="dialog"
        aria-label="Source detail"
      >
        <header className="flex items-center justify-between border-b border-gray-200 px-5 py-3">
          <div>
            <p className="text-xs font-medium tracking-wider text-blue-700 uppercase">Source</p>
            <h2 className="text-sm font-semibold text-gray-900">Evidence detail</h2>
          </div>
          <button
            type="button"
            onClick={closeSource}
            className="rounded-md p-1.5 text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-900"
            aria-label="Close source panel"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </header>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          {!selectedSourceId && (
            <p className="text-sm text-gray-500">Select a citation badge to inspect its source.</p>
          )}

          {sourceQuery.isLoading && (
            <div className="space-y-3">
              <div className="h-5 w-3/4 animate-pulse rounded bg-gray-100" />
              <div className="h-3 w-1/2 animate-pulse rounded bg-gray-100" />
              <div className="h-24 animate-pulse rounded bg-gray-100" />
              <div className="h-32 animate-pulse rounded bg-gray-100" />
            </div>
          )}

          {sourceQuery.isError && (
            <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
              Failed to load source.{' '}
              {sourceQuery.error instanceof Error ? sourceQuery.error.message : 'Unknown error.'}
            </div>
          )}

          {sourceQuery.data && (
            <article className="space-y-4">
              <div>
                <h3 className="text-lg font-semibold text-gray-900">
                  {sourceQuery.data.title || 'Untitled source'}
                </h3>
                <p className="mt-1 font-mono text-xs text-gray-400">{sourceQuery.data.source_id}</p>
              </div>

              <div className="flex flex-wrap gap-2 text-xs">
                <Badge>{sourceQuery.data.competitor_name}</Badge>
                <Badge>{sourceQuery.data.source_type}</Badge>
                <Badge
                  className={
                    RELIABILITY_STYLE[sourceQuery.data.reliability] ??
                    'border-gray-200 bg-gray-50 text-gray-600'
                  }
                >
                  reliability: {sourceQuery.data.reliability}
                </Badge>
                {sourceQuery.data.data_source && (
                  <Badge
                    className={
                      sourceQuery.data.data_source === 'live'
                        ? 'border-green-200 bg-green-100 text-green-800'
                        : 'border-gray-200 bg-gray-100 text-gray-500'
                    }
                  >
                    {sourceQuery.data.data_source === 'live' ? 'Live' : 'Demo'}
                  </Badge>
                )}
              </div>

              {sourceQuery.data.url && (
                <div>
                  <a
                    href={sourceQuery.data.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm break-all text-blue-700 underline hover:text-blue-800"
                  >
                    {sourceQuery.data.url}
                  </a>
                </div>
              )}

              <p className="text-xs text-gray-500">
                Retrieved {formatDateTime(sourceQuery.data.retrieved_at)}
              </p>

              {sourceQuery.data.snippet && (
                <blockquote className="border-l-4 border-blue-200 bg-blue-50 px-4 py-3 text-sm text-gray-800 italic">
                  {sourceQuery.data.snippet}
                </blockquote>
              )}

              {sourceQuery.data.content && (
                <details className="rounded-md border border-gray-200 bg-gray-50">
                  <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-gray-700 select-none hover:bg-gray-100">
                    Full content
                  </summary>
                  <div className="max-h-[420px] overflow-auto border-t border-gray-200 px-3 py-3 text-xs whitespace-pre-wrap text-gray-700">
                    {sourceQuery.data.content}
                  </div>
                </details>
              )}
            </article>
          )}
        </div>
      </aside>
    </>
  )
}

function Badge({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded border px-2 py-0.5 text-xs font-medium',
        className ?? 'border-gray-200 bg-gray-100 text-gray-700'
      )}
    >
      {children}
    </span>
  )
}
