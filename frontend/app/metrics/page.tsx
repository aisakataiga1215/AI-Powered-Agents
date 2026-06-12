'use client'

import { useQuery } from '@tanstack/react-query'

import { api } from '@/lib/api'
import type { MetricBucket } from '@/lib/types'

export default function MetricsPage() {
  const metricsQuery = useQuery({
    queryKey: ['metrics'],
    queryFn: () => api.getMetrics(),
    refetchInterval: 10_000,
  })

  const metrics = metricsQuery.data
  const byAgent = Object.entries(metrics?.by_agent ?? {})
    .sort((a, b) => b[1].cost_usd - a[1].cost_usd)
  const byDay = Object.entries(metrics?.by_day ?? {})
  const maxDayCost = Math.max(...byDay.map(([, value]) => value.cost_usd), 0)

  return (
    <div className="space-y-6">
      <header>
        <p className="text-xs font-medium uppercase tracking-wider text-blue-700">Metrics</p>
        <h1 className="mt-2 text-3xl font-semibold text-gray-900">运行成本与 Token</h1>
        <p className="mt-2 max-w-xl text-sm text-gray-600">
          汇总每次 AgentRun 的 token、估算成本和运行次数，评估模型调用成本与<span className="whitespace-nowrap">优化空间。</span>
        </p>
      </header>

      {metricsQuery.isError && (
        <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          Metrics 加载失败。{metricsQuery.error instanceof Error ? metricsQuery.error.message : '未知错误。'}
        </div>
      )}

      <section className="grid gap-3 md:grid-cols-3">
        <KpiCard label="估算总成本" value={formatUsd(metrics?.total_cost_usd ?? 0)} />
        <KpiCard label="总 Token" value={(metrics?.total_tokens ?? 0).toLocaleString()} />
        <KpiCard label="AgentRun 数" value={(metrics?.run_count ?? 0).toLocaleString()} />
      </section>

      <section className="grid gap-6 lg:grid-cols-2">
        <MetricTable title="按 Agent 汇总" rows={byAgent} />
        <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
          <h2 className="text-sm font-semibold text-gray-900">按日期汇总</h2>
          <div className="mt-4 space-y-3">
            {byDay.length === 0 && (
              <p className="rounded-md border border-dashed border-gray-200 p-4 text-center text-sm text-gray-500">
                暂无数据。
              </p>
            )}
            {byDay.map(([day, value]) => {
              const width = maxDayCost > 0 ? Math.max((value.cost_usd / maxDayCost) * 100, 4) : 0
              return (
                <div key={day} className="space-y-1">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-medium text-gray-700">{day}</span>
                    <span className="text-gray-500">
                      {formatUsd(value.cost_usd)} · {value.total_tokens.toLocaleString()} tokens
                    </span>
                  </div>
                  <div className="h-2 rounded-full bg-gray-100">
                    <div
                      className="h-2 rounded-full bg-blue-500"
                      style={{ width: `${width}%` }}
                    />
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </section>
    </div>
  )
}

function KpiCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <p className="text-xs font-medium uppercase tracking-wider text-gray-500">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-gray-900">{value}</p>
    </div>
  )
}

function MetricTable({ title, rows }: { title: string; rows: [string, MetricBucket][] }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <h2 className="text-sm font-semibold text-gray-900">{title}</h2>
      <div className="mt-4 overflow-hidden rounded-md border border-gray-200">
        <table className="w-full text-left text-sm">
          <thead className="bg-gray-50 text-xs uppercase tracking-wider text-gray-500">
            <tr>
              <th className="px-3 py-2">名称</th>
              <th className="px-3 py-2">Run</th>
              <th className="px-3 py-2">Token</th>
              <th className="px-3 py-2">成本</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {rows.length === 0 && (
              <tr>
                <td colSpan={4} className="px-3 py-6 text-center text-gray-500">暂无数据。</td>
              </tr>
            )}
            {rows.map(([name, value]) => (
              <tr key={name}>
                <td className="px-3 py-2 font-medium text-gray-900">{name}</td>
                <td className="px-3 py-2 text-gray-600">{value.run_count}</td>
                <td className="px-3 py-2 text-gray-600">{value.total_tokens.toLocaleString()}</td>
                <td className="px-3 py-2 text-gray-600">{formatUsd(value.cost_usd)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function formatUsd(value: number) {
  return `$${value.toFixed(6)}`
}
