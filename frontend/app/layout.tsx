import type { Metadata } from 'next'
import Link from 'next/link'
import './globals.css'
import { ClientProviders } from '@/components/ClientProviders'

export const metadata: Metadata = {
  title: 'AgentInsight — 竞品分析',
  description:
    '基于多 Agent 的竞品分析系统：采集公开信息、抽取结构化知识，并生成带来源的报告。',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" className="h-full" suppressHydrationWarning>
      <body className="min-h-full bg-gray-50 text-gray-900 antialiased" suppressHydrationWarning>
        <ClientProviders>
          <div className="flex min-h-screen flex-col">
            <header className="border-b border-gray-200 bg-white print:hidden">
              <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
                <div className="flex items-center gap-3">
                  <Link
                    href="/"
                    className="flex items-center gap-2 text-lg font-semibold text-gray-900 transition-colors hover:text-blue-600"
                  >
                    <span
                      aria-hidden
                      className="inline-block h-6 w-6 rounded bg-gradient-to-br from-blue-600 to-indigo-700"
                    />
                    AgentInsight
                  </Link>
                  <span className="hidden text-sm text-gray-400 sm:inline">
                    竞品分析
                  </span>
                </div>
                <nav className="flex items-center gap-5 text-sm text-gray-600">
                  <Link href="/projects" className="transition-colors hover:text-gray-900">
                    项目
                  </Link>
                  <Link
                    href="/"
                    className="rounded-md bg-gray-900 px-3 py-1.5 text-white transition-colors hover:bg-gray-700"
                  >
                    新建分析
                  </Link>
                </nav>
              </div>
            </header>
            <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-8">{children}</main>
            <footer className="border-t border-gray-200 bg-white print:hidden">
              <div className="mx-auto max-w-6xl px-6 py-4 text-xs text-gray-500">
                AgentInsight MVP — 多 Agent 竞品分析系统。对外分享报告前，请先核验引用来源。
              </div>
            </footer>
          </div>
        </ClientProviders>
      </body>
    </html>
  )
}
