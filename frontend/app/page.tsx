'use client'

/**
 * Project creation page.
 *
 * Renders a single-column form with industry, dynamic competitor list,
 * and analysis goals. On submit it POSTs to /api/projects and forwards
 * the user to the execution page where they can start the workflow.
 */

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useState, type FormEvent } from 'react'
import { useMutation } from '@tanstack/react-query'

import { api } from '@/lib/api'
import { cn } from '@/lib/cn'
import type { CompetitorInput, ProjectCreate } from '@/lib/types'

interface GoalOption {
  value: string
  label: string
  description: string
}

const GOAL_OPTIONS: GoalOption[] = [
  {
    value: 'feature_comparison',
    label: '功能对比',
    description: 'Map feature coverage across competitors.',
  },
  {
    value: 'pricing_analysis',
    label: '定价分析',
    description: 'Compare plan structure and price points.',
  },
  {
    value: 'user_personas',
    label: '用户画像',
    description: 'Identify each product’s primary audiences.',
  },
  {
    value: 'swot',
    label: 'SWOT 分析',
    description: 'Strengths, weaknesses, opportunities, threats.',
  },
]

const DEFAULT_COMPETITORS: CompetitorInput[] = [
  { name: 'Cursor', url: 'https://cursor.com' },
  { name: 'Trae', url: 'https://www.trae.ai' },
  { name: 'Windsurf', url: 'https://windsurf.ai' },
]

export default function NewProjectPage() {
  const router = useRouter()
  const [industry, setIndustry] = useState('AI Coding Tools')
  const [competitors, setCompetitors] = useState<CompetitorInput[]>(
    DEFAULT_COMPETITORS
  )
  const [goals, setGoals] = useState<string[]>(
    GOAL_OPTIONS.map((g) => g.value)
  )

  const createMutation = useMutation({
    mutationFn: (payload: ProjectCreate) => api.createProject(payload),
    onSuccess: (result) => {
      router.push(`/projects/${result.project_id}`)
    },
  })

  const handleCompetitorChange = (
    index: number,
    field: keyof CompetitorInput,
    value: string
  ) => {
    setCompetitors((prev) =>
      prev.map((row, i) => (i === index ? { ...row, [field]: value } : row))
    )
  }

  const handleAddCompetitor = () => {
    setCompetitors((prev) => [...prev, { name: '', url: '' }])
  }

  const handleRemoveCompetitor = (index: number) => {
    setCompetitors((prev) => prev.filter((_, i) => i !== index))
  }

  const handleToggleGoal = (value: string) => {
    setGoals((prev) =>
      prev.includes(value) ? prev.filter((g) => g !== value) : [...prev, value]
    )
  }

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const cleanedCompetitors = competitors
      .map((c) => ({ name: c.name.trim(), url: c.url.trim() }))
      .filter((c) => c.name.length > 0 && c.url.length > 0)
    const payload: ProjectCreate = {
      industry: industry.trim(),
      competitors: cleanedCompetitors,
      goals,
      output_language: 'zh',
      report_depth: 'standard',
    }
    createMutation.mutate(payload)
  }

  const submitDisabled =
    createMutation.isPending ||
    industry.trim().length === 0 ||
    competitors.every((c) => !c.name.trim() || !c.url.trim())

  return (
    <div className="mx-auto max-w-3xl">
      <header className="mb-8">
        <p className="text-xs font-medium uppercase tracking-wider text-blue-700">
          New Analysis
        </p>
        <h1 className="mt-2 text-3xl font-semibold text-gray-900">
          Create a competitive analysis project
        </h1>
        <p className="mt-2 max-w-xl text-sm text-gray-600">
          Define the industry, the competitors you want analyzed, and the
          analytical goals. The Collector, Analyst, Writer, and QA agents
          will run as a LangGraph workflow once you start the run.
        </p>
      </header>

      <form
        onSubmit={handleSubmit}
        className="space-y-6 rounded-xl border border-gray-200 bg-white p-6 shadow-sm"
      >
        <section className="space-y-2">
          <label
            htmlFor="industry"
            className="text-sm font-medium text-gray-900"
          >
            Industry / Topic
          </label>
          <input
            id="industry"
            value={industry}
            onChange={(e) => setIndustry(e.target.value)}
            placeholder="e.g. AI Coding Tools"
            className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 placeholder-gray-400 transition-shadow focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
            required
          />
          <p className="text-xs text-gray-500">
            The agents use this as topical framing across collection,
            analysis, and writing.
          </p>
        </section>

        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-medium text-gray-900">Competitors</h2>
            <button
              type="button"
              onClick={handleAddCompetitor}
              className="text-xs font-medium text-blue-700 hover:text-blue-800"
            >
              + Add competitor
            </button>
          </div>
          <div className="space-y-2">
            {competitors.map((row, index) => (
              <div
                key={index}
                className="flex flex-col gap-2 rounded-md border border-gray-200 bg-gray-50 p-3 sm:flex-row"
              >
                <input
                  value={row.name}
                  onChange={(e) =>
                    handleCompetitorChange(index, 'name', e.target.value)
                  }
                  placeholder="Name"
                  className="w-full rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200 sm:max-w-[180px]"
                />
                <input
                  value={row.url}
                  onChange={(e) =>
                    handleCompetitorChange(index, 'url', e.target.value)
                  }
                  placeholder="https://example.com"
                  className="w-full rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
                />
                <button
                  type="button"
                  onClick={() => handleRemoveCompetitor(index)}
                  disabled={competitors.length === 1}
                  className="rounded-md px-2 py-1 text-xs text-gray-500 transition-colors hover:bg-gray-200 hover:text-gray-900 disabled:cursor-not-allowed disabled:opacity-50"
                  aria-label={`Remove ${row.name || 'competitor'}`}
                >
                  Remove
                </button>
              </div>
            ))}
          </div>
        </section>

        <section className="space-y-3">
          <h2 className="text-sm font-medium text-gray-900">Analysis goals</h2>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {GOAL_OPTIONS.map((goal) => {
              const checked = goals.includes(goal.value)
              return (
                <label
                  key={goal.value}
                  className={cn(
                    'flex cursor-pointer items-start gap-3 rounded-md border p-3 text-sm transition-colors',
                    checked
                      ? 'border-blue-300 bg-blue-50'
                      : 'border-gray-200 bg-white hover:bg-gray-50'
                  )}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => handleToggleGoal(goal.value)}
                    className="mt-0.5 h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                  />
                  <div>
                    <div className="font-medium text-gray-900">{goal.label}</div>
                    <div className="text-xs text-gray-500">{goal.description}</div>
                  </div>
                </label>
              )
            })}
          </div>
        </section>

        {createMutation.isError && (
          <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {createMutation.error instanceof Error
              ? createMutation.error.message
              : 'Failed to create project.'}
          </div>
        )}

        <div className="flex items-center justify-between border-t border-gray-100 pt-4">
          <Link
            href="/projects"
            className="text-sm text-gray-600 hover:text-gray-900"
          >
            View existing projects &rarr;
          </Link>
          <button
            type="submit"
            disabled={submitDisabled}
            className={cn(
              'inline-flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium text-white transition-colors',
              submitDisabled
                ? 'cursor-not-allowed bg-gray-300'
                : 'bg-blue-600 hover:bg-blue-700'
            )}
          >
            {createMutation.isPending && (
              <span
                className="h-3 w-3 animate-spin rounded-full border-2 border-white border-t-transparent"
                aria-hidden
              />
            )}
            {createMutation.isPending ? 'Creating...' : 'Create project'}
          </button>
        </div>
      </form>
    </div>
  )
}
