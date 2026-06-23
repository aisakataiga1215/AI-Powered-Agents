/**
 * Shared frontend types for the competitive analysis system.
 *
 * These mirror the Pydantic schemas in `backend/app/schemas/`. The fields
 * marked OPTIONAL with `?` cover cases where the backend may serialize a
 * partial payload (e.g. WriterAgent fallback mode) or where the LLM
 * structured-output validation accepts loosely typed dicts.
 *
 * Keep this file in sync with:
 *   backend/app/schemas/project.py
 *   backend/app/schemas/competitor.py
 *   backend/app/schemas/source.py
 *   backend/app/schemas/claim.py
 *   backend/app/schemas/knowledge.py
 *   backend/app/schemas/report.py
 *   backend/app/schemas/trace.py
 *   backend/app/schemas/qa.py
 */

export type ProjectStatus =
  | 'created'
  | 'running'
  | 'stopped'
  | 'completed'
  | 'qa_failed'
  | 'failed'

export type IndustryType =
  | 'ai_saas'
  | 'ai_search'
  | 'design_tools'
  | 'ecommerce'
  | 'local_services'
  | 'open_source'
  | 'social'
  | 'general'

export type AnalysisPurpose =
  | 'build_product'
  | 'choose_product'
  | 'understand_industry'
  | 'analyze_growth_ops'

export type AnalysisFramework = 'swot' | 'three_c' | 'aarrr'

export type CompetitorRole =
  | 'direct_competitor'
  | 'indirect_competitor'
  | 'inspiration_product'
  | 'benchmark_leader'

export type SourceConfidence = 'high' | 'medium' | 'low' | 'unknown'

export interface DimensionScore {
  dimension_name: string
  score: number
  weight?: number
  rationale: string
  evidence: string[]
  source_confidence: SourceConfidence
}

export interface CompetitorScore {
  competitor_name: string
  overall_score: number
  dimensions: DimensionScore[]
  scoring_note?: string
}

export interface OpportunityScore {
  overall_score: number
  dimensions: DimensionScore[]
  scoring_note?: string
}

export interface CompetitorInput {
  name: string
  url: string
  role?: CompetitorRole
  extra_urls?: string[]
}

export type ResearchInputKind = 'survey' | 'interview' | 'questionnaire' | 'desk_research' | 'notes'

export interface ResearchInput {
  title: string
  content: string
  source_kind: ResearchInputKind
  competitor_name?: string
}

export interface CompetitorInProject {
  name: string
  url: string
  role?: CompetitorRole
  extra_urls?: string[]
}

export interface ProjectCreate {
  industry: string
  industry_type?: IndustryType
  analysis_purpose: AnalysisPurpose
  analysis_frameworks?: AnalysisFramework[]
  custom_dimensions?: string[]
  competitors: CompetitorInput[]
  goals: string[]
  output_language?: string
  report_depth?: string
  data_mode?: 'demo' | 'live_with_fallback'
  research_inputs?: ResearchInput[]
}

export interface ProjectResponse {
  project_id: string
  industry: string
  industry_type?: string
  analysis_purpose?: string
  analysis_frameworks?: string[]
  custom_dimensions?: string[]
  goals: string[]
  status: ProjectStatus
  created_at: string
  updated_at: string
  data_mode?: string
  research_inputs?: ResearchInput[]
  competitors?: CompetitorInProject[]
}

export interface CompetitorCollectionStats {
  source_count: number
  live_source_count?: number
  demo_source_count?: number
  fallback_attempted?: boolean
  fallback_used?: boolean
  fallback_available?: boolean
  fallback_source_count?: number
  attempted_urls?: string[]
}

export interface TokenUsage {
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  cost_usd?: number | null
}

export type AgentRunStatus = 'success' | 'failed' | 'skipped' | 'running' | 'timeout'

export interface AgentRun {
  agent_run_id: string
  project_id: string
  agent_name: string
  input: Record<string, unknown>
  output: Record<string, unknown>
  status: AgentRunStatus
  error_message: string | null
  latency_ms: number
  token_usage: TokenUsage
  retry_count: number
  created_at: string
}

export interface TracesResponse {
  project_id: string
  traces: AgentRun[]
}

export type WorkflowJobStatus = 'queued' | 'running' | 'completed' | 'failed' | 'canceled'

export interface WorkflowJob {
  job_id: string
  project_id: string
  status: WorkflowJobStatus
  backend: string
  attempts: number
  created_at: string
  started_at?: string | null
  finished_at?: string | null
  error_message?: string | null
}

export interface GraphNode {
  id: string
  label: string
  type: string
}

export interface GraphEdge {
  source: string
  target: string
  condition?: string
}

export interface GraphResponse {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export interface MetricsResponse {
  total_cost_usd: number
  total_tokens: number
  run_count: number
  by_agent: Record<string, MetricBucket>
  by_project: Record<string, MetricBucket>
  by_day: Record<string, MetricBucket>
}

export interface MetricBucket {
  cost_usd: number
  total_tokens: number
  run_count: number
}

/**
 * Backend Claim schema uses `text` (not `claim`).
 * `evidence` is a list of source IDs.
 */
export interface Claim {
  claim_id?: string
  text: string
  confidence?: 'high' | 'medium' | 'low'
  evidence: string[]
  sentences?: { text: string; sources: string[] }[] | null
  is_hypothesis?: boolean
  created_by?: string
}

export interface FeatureItem {
  name: string
  description: string
  availability: string
  evidence: string[]
}

export interface FeatureCategory {
  category: string
  features: FeatureItem[]
}

export interface PricingPlan {
  name: string
  price: string
  currency?: string
  billing_cycle: string
  features: string[]
  evidence: string[]
}

export interface PricingModel {
  has_free_plan: boolean
  pricing_url?: string
  plans: PricingPlan[]
  summary?: Claim | null
}

export interface ProductProfile {
  name: string
  website: string
  company: string
  positioning?: Claim | null
  target_users: Claim[]
}

export interface UserPersona {
  name: string
  description: string
  needs: string[]
  pain_points: string[]
  evidence: string[]
}

export interface SWOTAnalysis {
  strengths: Claim[]
  weaknesses: Claim[]
  opportunities: Claim[]
  threats: Claim[]
}

export interface CompetitorKnowledge {
  competitor_id?: string
  competitor_name: string
  product_profile?: ProductProfile | null
  feature_tree: FeatureCategory[]
  pricing_model?: PricingModel | null
  user_personas: UserPersona[]
  swot?: SWOTAnalysis | null
  sources: string[]
}

export type SourceType =
  | 'official_website'
  | 'pricing_page'
  | 'docs'
  | 'features_page'
  | 'security'
  | 'privacy'
  | 'blog'
  | 'review'
  | 'news'
  | 'manual_input'
  | 'unknown'

export type Reliability = 'high' | 'medium' | 'low'

export interface CandidateSource {
  candidate_id: string
  competitor_name: string
  url: string
  title: string
  snippet: string
  suggested_source_type?: string
  discovery_query?: string
  provider?: string
  confidence?: 'high' | 'medium' | 'low'
  reason?: string
  selected_by_default?: boolean
}

export interface CandidateCompetitor {
  candidate_id: string
  name: string
  website: string
  description: string
  raw_title?: string
  source_url?: string
  domain?: string
  discovery_query?: string
  provider?: string
  confidence?: 'high' | 'medium' | 'low'
  relevance_score?: number
  relevance_reason?: string
  suggested_role?: CompetitorRole
  role_confidence?: 'high' | 'medium' | 'low'
  reason?: string
  selected_by_default?: boolean
}

export interface SourceEvidence {
  source_id: string
  project_id: string
  competitor_id: string
  competitor_name: string
  source_type: SourceType | string
  url: string
  title: string
  snippet: string
  content: string
  retrieved_at: string
  reliability: Reliability | string
  data_source?: 'live' | 'demo' | 'search' | 'manual'
  contains_pii?: boolean
  desensitized?: boolean
  screenshot_path?: string
  screenshot_url?: string
}

/**
 * NOTE: `feature_comparison`, `pricing_comparison`,
 * `user_persona_comparison`, and `swot_comparison` are loosely typed
 * `Record<string, unknown>` in the backend. The MVP UI renders the first
 * two as `Record<string, string>` (competitor_name → summary string),
 * which matches the WriterAgent's default output shape.
 */
export interface CompetitiveReport {
  report_id: string
  project_id: string
  title: string
  executive_summary: Claim[]
  competitor_overview: CompetitorKnowledge[]
  feature_comparison: Record<string, string>
  pricing_comparison: Record<string, string>
  user_persona_comparison: Record<string, unknown>
  swot_comparison: Record<string, unknown>
  strategic_recommendations: Claim[]
  source_list: SourceEvidence[]
  markdown_content: string
  created_at: string
  analysis_purpose?: string
  analysis_frameworks?: string[]
  selected_report_tabs?: string[]
  framework_sections?: Record<string, unknown>
  custom_dimension_sections?: Record<string, unknown>
  custom_dimension_analysis?: Record<string, DimensionScore>
  purpose_sections?: Record<string, unknown>
  competitor_scores?: Record<string, CompetitorScore>
  opportunity_score?: OpportunityScore | null
  market_background?: Record<string, unknown> | null
  feature_insights?: Record<string, unknown> | null
  operation_monetization?: Record<string, unknown> | null
  analysis_objective?: string
  competitor_selection_rationale?: Record<string, string>
}

/**
 * Backend QAIssue severity is `high | medium | low` only. We accept
 * `critical` here so the UI can display it if future versions emit it,
 * but the backend MVP will not produce that value.
 */
export type IssueSeverity = 'high' | 'medium' | 'low'

export interface QAIssue {
  issue_id?: string
  severity: IssueSeverity
  target_agent: string
  issue_type: string
  message: string
  suggested_action?: string
}

export interface QAResult {
  qa_result_id?: string
  project_id?: string
  passed: boolean
  score: number
  issues: QAIssue[]
  created_at?: string
}

export interface QAComparison {
  issues_before: number
  issues_high_before: number
  qa_score_before: number
  citation_coverage_before: number
  issues_after: number
  issues_high_after: number
  qa_score_after: number
  citation_coverage_after: number
  claims_affected: number
  rework_target?: string
}

/**
 * Shape of the QAAgent trace output stored in AgentRun.output.
 * Extends QAResult fields with pre-computed severity breakdown counts.
 */
export interface QATraceOutput {
  qa_result_id?: string
  passed: boolean
  score: number
  issues: QAIssue[]
  issue_count: number
  high_severity_count: number
  medium_severity_count: number
  low_severity_count: number
  blocking_issue_count: number
  advisory_count: number
  llm_review_status?: string
  llm_issue_count?: number
  qa_comparison?: QAComparison | null
}
