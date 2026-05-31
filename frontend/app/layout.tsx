import type { Metadata } from 'next'
import Link from 'next/link'
import './globals.css'
import { ClientProviders } from '@/components/ClientProviders'

export const metadata: Metadata = {
  title: 'AgentInsight — Competitive Analysis',
  description:
    'AI-powered competitive analysis multi-agent system. Collect public information, extract structured knowledge, and generate cited reports.',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" className="h-full">
      <body className="min-h-full bg-gray-50 text-gray-900 antialiased">
        <ClientProviders>
          <div className="flex min-h-screen flex-col">
            <header className="border-b border-gray-200 bg-white">
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
                    Competitive Analysis
                  </span>
                </div>
                <nav className="flex items-center gap-5 text-sm text-gray-600">
                  <Link
                    href="/projects"
                    className="transition-colors hover:text-gray-900"
                  >
                    Projects
                  </Link>
                  <Link
                    href="/"
                    className="rounded-md bg-gray-900 px-3 py-1.5 text-white transition-colors hover:bg-gray-700"
                  >
                    New Analysis
                  </Link>
                </nav>
              </div>
            </header>
            <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-8">
              {children}
            </main>
            <footer className="border-t border-gray-200 bg-white">
              <div className="mx-auto max-w-6xl px-6 py-4 text-xs text-gray-500">
                AgentInsight MVP — multi-agent competitive analysis with
                source-traceable claims. Verify cited evidence before sharing
                generated reports externally.
              </div>
            </footer>
          </div>
        </ClientProviders>
      </body>
    </html>
  )
}
