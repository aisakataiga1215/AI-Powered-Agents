/**
 * Typed REST client for the competitive analysis backend.
 *
 * All endpoints are mounted under `${NEXT_PUBLIC_API_BASE_URL}/api/`.
 * Errors are surfaced as Error instances with status code and response
 * body context so the caller can render meaningful messages.
 */

import type {
  CandidateCompetitor,
  CandidateSource,
  CompetitiveReport,
  GraphResponse,
  MetricsResponse,
  ProjectCreate,
  ProjectResponse,
  SourceEvidence,
  TracesResponse,
} from './types'

const BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000'

export class ApiError extends Error {
  status: number
  body: string

  constructor(status: number, body: string) {
    super(`API ${status}: ${body || 'request failed'}`)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
    cache: 'no-store',
    ...init,
  })
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new ApiError(res.status, text)
  }
  return (await res.json()) as T
}

export const api = {
  createProject: (payload: ProjectCreate) =>
    request<{ project_id: string; status: string }>('/api/projects', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  listProjects: () => request<ProjectResponse[]>('/api/projects'),

  getProject: (id: string) =>
    request<ProjectResponse>(`/api/projects/${id}`),

  runProject: (id: string) =>
    request<{ project_id: string; status: string }>(
      `/api/projects/${id}/run`,
      { method: 'POST' }
    ),

  getTraces: (id: string) =>
    request<TracesResponse>(`/api/projects/${id}/traces`),

  getReport: (id: string) =>
    request<CompetitiveReport>(`/api/projects/${id}/report`),

  patchReport: (
    id: string,
    payload: Partial<Pick<CompetitiveReport, 'title' | 'markdown_content' | 'analysis_objective' | 'competitor_selection_rationale'>>
  ) =>
    request<CompetitiveReport>(`/api/projects/${id}/report`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),

  getSource: (sourceId: string) =>
    request<SourceEvidence>(`/api/sources/${sourceId}`),

  getSearchStatus: () =>
    request<{ search_available: boolean }>('/api/search/status'),

  getGraph: () => request<GraphResponse>('/api/graph'),

  getMetrics: (params?: { project_id?: string; since?: string }) => {
    const query = new URLSearchParams()
    if (params?.project_id) query.set('project_id', params.project_id)
    if (params?.since) query.set('since', params.since)
    const suffix = query.toString() ? `?${query.toString()}` : ''
    return request<MetricsResponse>(`/api/metrics${suffix}`)
  },

  searchSources: (payload: {
    competitor_name: string
    website: string
    goals: string[]
    industry_type: string
  }) =>
    request<{ candidates: CandidateSource[]; search_available: boolean }>(
      '/api/search/sources',
      { method: 'POST', body: JSON.stringify(payload) }
    ),

  discoverCompetitors: (payload: { industry: string; industry_type: string }) =>
    request<{ candidates: CandidateCompetitor[]; search_available: boolean }>(
      '/api/search/competitors',
      { method: 'POST', body: JSON.stringify(payload) }
    ),
}
