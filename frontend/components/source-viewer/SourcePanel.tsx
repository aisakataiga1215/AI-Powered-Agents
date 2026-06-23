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

import { api, apiAssetUrl } from '@/lib/api'
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
        aria-label="来源详情"
      >
        <header className="flex items-center justify-between border-b border-gray-200 px-5 py-3">
          <div>
            <p className="text-xs font-medium tracking-wider text-blue-700 uppercase">来源</p>
            <h2 className="text-sm font-semibold text-gray-900">证据详情</h2>
          </div>
          <button
            type="button"
            onClick={closeSource}
            className="rounded-md p-1.5 text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-900"
            aria-label="关闭来源面板"
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
            <p className="text-sm text-gray-500">选择引用编号查看对应来源。</p>
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
              来源加载失败。{sourceQuery.error instanceof Error ? sourceQuery.error.message : '未知错误。'}
            </div>
          )}

          {sourceQuery.data && (
            <article className="space-y-4">
              <div>
                <h3 className="text-lg font-semibold text-gray-900">
                  {sourceQuery.data.title || '未命名来源'}
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
                  可靠性：{sourceQuery.data.reliability}
                </Badge>
                {sourceQuery.data.data_source && (
                  <Badge
                    className={
                      sourceQuery.data.data_source === 'live'
                        ? 'border-green-200 bg-green-100 text-green-800'
                        : sourceQuery.data.data_source === 'search'
                        ? 'border-teal-200 bg-teal-100 text-teal-800'
                        : 'border-gray-200 bg-gray-100 text-gray-500'
                    }
                  >
                    {sourceQuery.data.data_source === 'live'
                      ? '真实采集'
                      : sourceQuery.data.data_source === 'search'
                      ? '搜索'
                      : 'Demo'}
                  </Badge>
                )}
                {sourceQuery.data.desensitized && (
                  <Badge className="border-purple-200 bg-purple-50 text-purple-700">
                    已脱敏
                  </Badge>
                )}
                {sourceQuery.data.contains_pii && (
                  <Badge className="border-orange-200 bg-orange-50 text-orange-700">
                    检测到 PII
                  </Badge>
                )}
              </div>

              {sourceQuery.data.url && (
                <div>
                  {toExternalHref(sourceQuery.data.url) ? (
                    <a
                      href={toExternalHref(sourceQuery.data.url)!}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center rounded-md border border-blue-200 bg-blue-50 px-2.5 py-1.5 text-sm font-medium text-blue-700 hover:bg-blue-100"
                    >
                      打开原始链接
                    </a>
                  ) : (
                    <span className="rounded-md border border-gray-200 bg-gray-50 px-2.5 py-1.5 text-xs text-gray-500">
                      原始链接格式无效，无法直接打开
                    </span>
                  )}
                  <p className="mt-2 break-all font-mono text-xs text-gray-500">
                    {sourceQuery.data.url}
                  </p>
                </div>
              )}

              {sourceQuery.data.screenshot_url && (
                <figure className="overflow-hidden rounded-md border border-gray-200 bg-gray-50">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={apiAssetUrl(sourceQuery.data.screenshot_url)}
                    alt={`${sourceQuery.data.title || sourceQuery.data.url} 页面截图`}
                    className="max-h-64 w-full object-cover object-top"
                  />
                  <figcaption className="border-t border-gray-200 px-3 py-2 text-xs text-gray-500">
                    页面截图证据
                  </figcaption>
                </figure>
              )}

              <p className="text-xs text-gray-500">
                获取时间：{formatDateTime(sourceQuery.data.retrieved_at)}
              </p>

              {sourceQuery.data.snippet && (
                <blockquote className="border-l-4 border-blue-200 bg-blue-50 px-4 py-3 text-sm text-gray-800 italic">
                  {sourceQuery.data.snippet}
                </blockquote>
              )}

              {sourceQuery.data.content && (
                <details className="rounded-md border border-gray-200 bg-gray-50">
                  <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-gray-700 select-none hover:bg-gray-100">
                    完整内容
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

function toExternalHref(rawUrl: string): string | null {
  const trimmed = rawUrl.trim()
  if (!trimmed) return null
  const withProtocol = /^https?:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`
  try {
    const url = new URL(withProtocol)
    if (url.protocol !== 'http:' && url.protocol !== 'https:') return null
    return url.toString()
  } catch {
    return null
  }
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
