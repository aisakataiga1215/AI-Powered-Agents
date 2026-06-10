# Project Status

**Last updated:** 2026-06-10

## Current Status: M17.1 Complete — Purpose-Driven Decision Support Phase 1

---

## Milestones

### Milestone 17.1: Purpose-Driven Decision Support Phase 1 ✅ COMPLETE

- [x] Canonical `analysis_purpose` contract uses four decision intents: build similar product, choose product to use, market research, and competitor success analysis.
- [x] Legacy purpose values normalize to canonical values for stored/API compatibility; unknown create payload values are rejected.
- [x] Canonical purpose flows through project persistence, API responses, LangGraph state, AnalystAgent, WriterAgent, QAAgent, reports, and print/PDF rendering.
- [x] Project creation UI shows four Chinese decision-intent purpose options.
- [x] Custom dimensions support suggestion chips, trimming, dedupe, and max-8 cap.
- [x] Purpose report tabs/print sections render all four canonical purposes, including clickable source badges for generic evidence arrays.
- [x] Backend targeted regressions pass: `test_api_projects.py`, `test_qa_purpose_checks.py`, `test_graph_workflow.py`.
- [x] Frontend lint and production build pass.

### Milestone 1: Project Setup ✅ COMPLETE

- Repository structure created
- FastAPI backend set up
- Base documentation added
- Environment variables configured
- Initial Pydantic schemas added
- Runtime business agent skeletons added

### Milestone 2: Schema Design ✅ COMPLETE

- Competitor knowledge schema (`CompetitorKnowledge`, `ProductProfile`, `FeatureItem`, etc.)
- Source evidence schema (`SourceEvidence`, `SourceType`, `Reliability`)
- Claim schema (`Claim`, `ConfidenceLevel`)
- Agent message schema (`AgentMessage`, `MessageType`)
- QA result schema (`QAResult`, `QAIssue`, `IssueSeverity`)
- Report schema (`CompetitiveReport`)
- Raw extraction schema (`RawCompetitorExtraction`) for two-stage LLM pipeline
- All schemas documented in `docs/schema_design.md`

### Milestone 3: Basic Agent Workflow ✅ COMPLETE

- [x] CollectorAgent (demo fixtures for Cursor, Trae, Windsurf)
- [x] AnalystAgent (two-stage extraction: RawCompetitorExtraction → normalization_service → CompetitorKnowledge)
- [x] WriterAgent (deterministic pricing + feature tables; inline `[src_xxx]` citations in markdown)
- [x] QAAgent (rule-based checks, rework routing)
- [x] LangGraph workflow with rework loop
- [x] Retry and routing logic (MAX_REPAIR_LOOPS)
- [x] QAAgent rejects outputs with missing citations, missing pricing, missing required fields

### Milestone 4: Traceability and Observability ✅ COMPLETE

- [x] Agent inputs and outputs stored (AgentRun table)
- [x] Source references stored (Source table)
- [x] Agent execution status stored
- [x] QA feedback stored (QAResult table)
- [x] Retry and rework records stored
- [x] Token usage captured for AnalystAgent and WriterAgent
- [x] Agent trace timeline displayed in frontend (TraceTimeline + AgentRunCard)

### Milestone 5: Report Viewer ✅ COMPLETE

- [x] Report rendered in frontend (7-tab layout: Summary, Pricing, Features, SWOT, Recommendations, Markdown, QA Result)
- [x] FeatureComparisonTable: matrix table with competitors as columns, feature categories as rows
- [x] Citation click behavior: numbered `[N]` badges in ClaimList and `[src_xxx]` badges in MarkdownTab
- [x] Source inspection panel: slide-in SourcePanel with full source detail

### Milestone 6: Demo Scenario ✅ COMPLETE

- [x] AI coding tools demo case (Cursor / Trae / Windsurf)
- [x] Demo fixtures (no network needed)
- [x] Real DeepSeek LLM workflow runs end-to-end
- [x] Status `completed`, QA passes first attempt
- [x] Frontend demo flow: create project → run workflow → view traces → view report → click citations

### Milestone 7 (v1): Live Data Collection ✅ COMPLETE

- [x] Per-project `data_mode` (`demo` | `live_with_fallback`) — schema, DB migration, frontend selector
- [x] `crawler_service.crawl_page()` — httpx + BeautifulSoup, 10s timeout, 1 retry, best-effort robots.txt
- [x] `source_discovery` — probes well-known paths (`/pricing`, `/features`, `/docs`, `/about`, `/security`, `/privacy`)
- [x] `source_classifier` — URL-path-first keyword classifier mapping to `SourceType`
- [x] `coverage_evaluator` — per-competitor scoring with `WEAK_THRESHOLD=40`
- [x] `CollectorAgent._collect_live()` — per-competitor live path with demo fallback merge
- [x] `QAAgent.check_source_coverage()` — per-competitor coverage issues (`missing_pricing_source`, `missing_features_source`)
- [x] Frontend Live/Demo source badges and source-count breakdown in report viewer
- [x] 226 tests passing (5 new test modules)

### Milestone 8 (v1 Hardening): Source Quality Validation ✅ COMPLETE

- [x] `SourceClassifier` content validation — URL path is hint only; title + content must confirm `SourceType`; empty content trusts URL (backward-compat)
- [x] Bad-page blocklist in `crawl_page()` — rejects Discord/Cloudflare/captcha/access-denied pages (checks both title and body preview)
- [x] New QA issue types: `weak_source_quality`, `source_type_content_mismatch`
- [x] `QAAgent.check_source_quality()` — per-source content mismatch check; high severity for blocked content, medium for weak content
- [x] Feature taxonomy normalization — `normalize_feature_category()` + `CATEGORY_ALIASES` in `normalization_service.py`, applied in both `_normalize_features()` and `writer_agent._build_feature_comparison()`
- [x] Tests: 239 passing (+13 new)

### Milestone 11: Partial Report / QA-Failed Visibility ✅ COMPLETE

- [x] **`ProjectResponse.competitors`** — backend now returns all requested competitors (name + url) via `GET /projects/{id}`; no new DB query needed (uses existing ORM relationship).
- [x] **`QaStatusBanner`** — orange warning for `qa_failed`, red for `failed`; shows dropped-competitor count.
- [x] **`DroppedCompetitorsList`** — shows each dropped competitor with name, URL, and inferred reason (demo fixture missing, homepage unreachable, weak coverage score, etc.).
- [x] **Report page** — project query added; banner shown for non-`completed` / non-`running` status; header chip shows "N of M analysed (K dropped)"; QA tab includes dropped-competitors list; PDF button label changes to "Export Partial PDF" for `qa_failed`.
- [x] **Print page** — same project query; warning banner at top of printed document; "Dropped / Insufficient Competitors" section between QA Result and References.
- [x] 259 backend tests still passing; clean TypeScript build.

### Milestone 12: v1.5 Robustness Hardening ✅ COMPLETE

- [x] **Industry-specific source discovery**: `_INDUSTRY_PATHS` + `_INDUSTRY_MAX_PAGES` — ecommerce (14 paths, 8 pages), local_services (12 paths, 8 pages), ai_saas (10 paths, 5 pages), general (6 paths, 5 pages). `CANDIDATE_PATHS` backward-compat alias preserved.
- [x] **`industry_type` field end-to-end**: schema → DB migration → project service → API response → workflow state → collector agent → frontend.
- [x] **Fixed fallback semantics**: demo mode no longer sets `fallback_*` fields (those are `live_with_fallback`-only). `fixture_exists()` side-effect-free check before `load_demo_fixtures()`.
- [x] **Coverage-quality "analyzed" gate**: `_is_adequately_covered()` — score ≥ 40 OR (homepage AND (pricing OR features/docs)). `sufficiently_collected_competitors` in trace for observability (does NOT gate AnalystAgent).
- [x] **`_CollectionResult` dataclass**: typed replacement for bare 4-tuple with `attempted_urls`, per-competitor stats, and explicit fallback semantics fields.
- [x] **`_infer_drop_reason()`**: human-readable drop reasons per mode ("No demo fallback available", "Crawl failed — no usable sources", etc.).
- [x] **`attempted_urls_by_competitor` in trace**: logs every URL probed for each competitor.
- [x] **`InsufficientDataView` component**: amber diagnostic section when `citedSources==0 || summaryLen==0 || qaScore<30 || analysedCount<2`. Receives `qaResult` directly; reads CollectorAgent trace for stats/URLs only.
- [x] **Industry type selector in frontend**: 4-option radio card group; default `'general'`; submitted with project payload.
- [x] **Print page `isInsufficientData` gate**: `PrintInsufficientDataSection` rendered instead of full report when data is insufficient.
- [x] 280 backend tests passing (+21 new); clean TypeScript build.

### Milestone 14: Search-Plus-Crawl (Tavily) ✅ COMPLETE

- [x] `backend/app/services/search_provider.py` (NEW) — `SearchResult` Pydantic model, `SearchProvider` Protocol, `TavilySearchProvider` (wraps Tavily SDK), `NullSearchProvider` (no-op), `create_search_provider()` factory
- [x] `backend/app/services/search_service.py` (NEW) — industry-keyed query templates, `_is_crawlable` URL filter (`_BLOCKED_DOMAINS`: youtube/twitter/reddit/linkedin etc.; `_UNSUPPORTED_EXTENSIONS`), `_normalize_url`, `SearchService.discover_urls` capped at `_SEARCH_MAX_URLS=5`
- [x] `SourceEvidence.data_source` extended with `"search"` value (discovery channel only; not reliability)
- [x] `Settings.tavily_api_key` config field; `TAVILY_API_KEY` added to `.env.example`; `tavily-python>=0.3.0` added to `pyproject.toml`
- [x] `source_discovery.get_industry_max_pages()` public helper exposed for the collector
- [x] `CollectorAgent._normalize_url()` (strips `utm_*`, `fbclid`, `gclid` via `_TRACKING_PARAMS`) + `_deduplicate_urls()`; `_collect_live()` accepts `search_service` param; `run()` accepts `_search_service` injection param; combined cap = `industry_max + 5`
- [x] Activation gated on `ENABLE_LIVE_SEARCH=true` AND `TAVILY_API_KEY` set; default `NullSearchProvider` preserves pre-M14 behavior
- [x] Demo mode never triggers search; Tavily errors caught per-query and globally — workflow continues with known-path URLs only
- [x] Frontend: `data_source` union extended with `'search'`; teal Search badge in `SourcePanel`; `SourceCountChip` counts search-discovered sources
- [x] `backend/tests/test_search_service.py` (NEW) — 12 new tests
- [x] **316 backend tests passing** (+12 new); clean TypeScript build

### Milestone 15A: Interactive Source Search ✅ COMPLETE

- [x] `backend/app/schemas/search.py` (NEW) — `CandidateSource` (10 fields: `candidate_id`, `competitor_name`, `url`, `title`, `snippet` [display-only], `suggested_source_type`, `discovery_query`, `provider`, `confidence`, `reason`, `selected_by_default`). **Not evidence** — becomes evidence only after user selection + CrawlerService crawl.
- [x] `CompetitorInput.extra_urls: list[str]` — user-selected URLs propagated to live collection.
- [x] `search_provider.create_provider_from_settings()` factory.
- [x] `SearchService.search_sources()` method alongside `discover_urls()`; new constants (`_GOAL_QUERY_TEMPLATES`, `_DEFAULT_SOURCE_QUERIES`, `_SOURCE_TYPE_PRIORITY`) + helpers (`_infer_source_confidence`, `_infer_source_reason`).
- [x] `POST /api/search/sources` endpoint (`backend/app/api/routes/search.py`); router registered in `backend/app/main.py`.
- [x] `CollectorAgent._collect_live()` accepts `extra_urls` param; trace output adds `selected_extra_urls`, `silent_search_urls`, `rejected_extra_urls`.
- [x] Frontend: `CandidateSource` interface + `searchSources()` client; new `CandidateSourcePanel.tsx` per-competitor search panel; `app/page.tsx` integration with stable keys and `extra_urls` in submit.
- [x] Activation reuses M14 flags (`ENABLE_LIVE_SEARCH=true` + `TAVILY_API_KEY`); shows disabled state with message when unavailable.
- [x] Tavily snippets are display-only; never stored as `SourceEvidence.content`. M14 silent background search unchanged.
- [x] **332 backend tests passing** (+16 new); clean TypeScript build.

### Milestone 15B: Competitor Discovery ✅ COMPLETE

- [x] `backend/app/schemas/discovery.py` (NEW) — `CandidateCompetitor` with provenance (`raw_title`, `source_url`, `domain`) and quality signals (`relevance_score` 0–100, `relevance_reason`, `role_confidence`). Suggested role defaults to `direct_competitor`.
- [x] `SearchService.discover_competitors()` method; constants `_DISCOVERY_BLOCKED_DOMAINS` (aggregators/listings/news excluded), `_LISTICLE_TITLE_RE` (filters "Top 10…" titles), `_DISCOVERY_TEMPLATES` (per industry type including `ai_saas`/`social`); helpers `_extract_company_name()`, `_score_competitor_relevance()`.
- [x] `POST /api/search/competitors` endpoint — accepts `{ industry, industry_type }`, returns `list[CandidateCompetitor]`.
- [x] Frontend: `CandidateCompetitor` interface + `discoverCompetitors()` client; new `CompetitorDiscoveryPanel.tsx` with "Discover competitors" trigger, relevance badges, suggested-role label, "Add N selected" action; mounted in the Competitors section header on `app/page.tsx`.
- [x] No DB changes — candidates are selection input only; once accepted they enter the form as ordinary `CompetitorInput` rows.
- [x] Activation reuses M14 flags (`ENABLE_LIVE_SEARCH=true` + `TAVILY_API_KEY`).
- [x] +11 new tests — 8 service (`test_search_service.py`) + 3 API (`test_search_api.py`).
- Note: Real Tavily tests showed noisy false-positive competitors (Zapier, DigitalOcean blog pages, Gartner, DevGenius Blog, Axify articles).

### Milestone 16: QA Severity Semantics Refactor ✅ COMPLETE

- [x] QA severity semantics tightened: `high` = blocking (forces failure), `medium` = warning (deducts score, can still pass), `low` = advisory (no deduction).
- [x] `blocking_issue_count` now counts only `high` severity (previously high + medium). `medium_severity_count` surfaces as the "warnings" count for UI/PDF.
- [x] `backend/app/agents/qa_agent.py`: severity bookkeeping in `_build_trace_output` updated.
- [x] `frontend/lib/types.ts`: typing comments updated.
- [x] `frontend/components/qa/QAResultBanner.tsx`, `frontend/app/projects/[id]/{report,traces,print}/page.tsx`: banner / tab badge / PDF copy render the new categories (e.g. `QA Passed · Score 95/100 · 1 warning · 2 advisories`, `QA Failed · Score 55/100 · 2 blocking issues · 3 warnings`).
- [x] `backend/tests/test_qa_trace_output.py`: regression tests updated for the new counting rules.

### Milestone 16.1: Discovery Quality Recovery ✅ COMPLETE

- [x] `_ARTICLE_PATH_RE`: caps relevance_score at 30 for blog/article/guide/review/resource/content URL paths
- [x] `_BLOG_DOMAIN_RE`: scores `.blog` TLD and ghost.io domains at 5; `blog.*` subdomains are also suppressed
- [x] Extended `_LISTICLE_TITLE_RE` and `_LISTICLE_TITLE_END_RE`: covers guide, complete guide, how to, I tested, full comparison, market reports, statistics, and root-level listicle slugs
- [x] Expanded `_DISCOVERY_BLOCKED_DOMAINS`: aggregators, analyst/research firms, app stores, publisher/media domains, and developer blogging platforms
- [x] `_DISCOVERY_MIN_SCORE = 60`: discover_competitors() only returns candidates with relevance_score >= 60
- [x] Homepage depth bonus (+15 for root path) to push product homepages reliably above min score
- [x] DigitalOcean/Zapier NOT globally blocked — only their blog/article paths are penalized
- [x] Frontend (`frontend/app/page.tsx`): deduplicate discovered competitors by normalized domain and name before appending
- [x] Regression tests: Gartner blocked, article path <= 30, product homepage >= min score, all results >= min score, sorted by score
- [x] Cross-category robustness tests for ecommerce, local_services, social, and general discovery false positives plus positive homepages

### Milestone 16.2: Search and Discovery Quality Recovery ✅ COMPLETE

- [x] Tavily provider accepts Tavily-specific optional parameters (`search_depth`, `topic`, `include_domains`, `exclude_domains`, `exact_match`) while preserving the generic provider abstraction
- [x] Source search uses official-domain first pass with product aliases, then falls back to general web search only if no official-domain sources are found
- [x] Windsurf, Cursor, Trae, Codeium, Claude Code, Devin, Tabnine, Replit, Qodo, and related aliases are recognized for source search
- [x] AI SaaS discovery boosts known AI coding products and extracts known product names from listicle snippets without returning the listicle domain as a competitor
- [x] Ambiguous brand/topic handling caps non-tech Windsurf-like results and avoids boosting deep GitHub repository paths as products
- [x] Third-party docs/hosting domains are not classified as official websites or high-confidence official sources
- [x] Social discovery uses dating templates only for dating-related user queries
- [x] Manual live category QA covered ai_saas, ecommerce, local_services, social, and general discovery

### Milestone 13B: PM-Style Report Structure ✅ COMPLETE

- [x] `backend/app/schemas/pm_sections.py` (NEW) — MarketTrend, MarketBackground, FeatureInsights, GtmProfile, OperationMonetization
- [x] `CompetitiveReport` extended with 3 new optional fields: market_background, feature_insights, operation_monetization
- [x] `IssueType` extended with 3 new values: missing_market_background, missing_feature_insights, missing_operation_monetization
- [x] WriterAgent: `_PM_SECTIONS_INSTRUCTION` appended to all user messages (always, regardless of analysis_purpose); `_normalize_report_payload` handles all 3 with try/except
- [x] QAAgent: advisory-only `check_pm_sections()` (3 medium-severity checks, never block pass/fail)
- [x] `MarketBackground.tsx` (NEW) — market overview prose, market_size_notes badge, trend list, drivers/challenges chip grid
- [x] `FeatureInsights.tsx` (NEW) — table-stakes chips, differentiator table, gap opportunity cards, cross-competitor patterns list
- [x] `OperationMonetization.tsx` (NEW) — GTM profile cards, monetization patterns, AARRR funnel table
- [x] Report viewer: new "Market & Ops" tab (index 3, after Features, before SWOT)
- [x] Print page: 3 new PrintSections for all PM-framework sections
- [x] `general` purpose: sections always generated; existing behavior unchanged
- [x] 304 backend tests passing (+10 new); clean TypeScript build

### Milestone 13A: Minimal Product Analysis Framework ✅ COMPLETE

- [x] `analysis_purpose` field (`general` | `build_product` | `choose_product`) — schema, DB migration, API, workflow state, frontend selector
- [x] `custom_dimensions: string[]` — user-defined analysis axes; DB migration (JSON TEXT), frontend tag-chip input, injected into analyst + writer prompts
- [x] `CompetitorRole` (`direct_competitor` | `indirect_competitor` | `inspiration_product` | `benchmark_leader`) — competitor-level annotation; DB migration, frontend per-competitor `<select>`, propagated through workflow
- [x] `social` added to `IndustryType` — source discovery paths + frontend 5th radio card
- [x] `backend/app/schemas/scoring.py` (NEW) — `DimensionScore`, `CompetitorScore`, `OpportunityDimension`, `OpportunityScore` with Pydantic field-range validation
- [x] `CompetitiveReport` extended — 7 new fields: `analysis_purpose`, `analysis_objective`, `competitor_selection_rationale`, `purpose_sections`, `competitor_scores`, `opportunity_score`, `custom_dimension_analysis`
- [x] `AnalystAgent` — purpose directives and competitor-role cues injected into user message; custom dimension instructions appended
- [x] `WriterAgent` — purpose-specific JSON output instructions; `_normalize_report_payload()` validates all new fields gracefully; sets `report.analysis_purpose` after bind
- [x] `QAAgent` — 2 advisory-only medium-severity checks (`check_custom_dimensions`, `check_scoring_rationale`); never affect pass/fail threshold
- [x] `frontend/components/report-viewer/ScoringMatrix.tsx` (NEW) — choose_product: competitor-column matrix; build_product: single-column opportunity table; color-coded scores + confidence badges
- [x] `frontend/components/report-viewer/PurposeSections.tsx` (NEW) — choose_product: ranking, best_for, avoid, decision_matrix; build_product: gaps, learn_from, pitfalls, differentiation, mvp_direction
- [x] Report viewer — dynamic "Build Insights" / "Decision Guide" tab; analysis_objective + competitor_selection_rationale summary card; inline `CustomDimensionTable`
- [x] Print page — `PrintSection` blocks for scoring matrix + purpose sections; rendered only when `analysis_purpose !== 'general'`
- [x] `general` purpose default — all existing behavior unchanged; purpose tab hidden; QA advisory checks return no issues
- [x] ~291 backend tests passing (+11 new: test_scoring_schema.py ×5, test_qa_purpose_checks.py ×7); clean TypeScript build

### Milestone 10: QA Display Fix + Trace Export ✅ COMPLETE

- [x] **QA display mismatch fixed** — `_build_trace_output` now includes full `issues` array +
  `medium_severity_count`, `low_severity_count`, `blocking_issue_count`, `advisory_count`.
  UI report page QA tab and PDF print page now show all issues/advisories correctly.
- [x] **Advisory display** — low-severity issues shown as "advisories" throughout;
  QA tab badge shows amber "N adv" when passed with advisories, green "ok" when clean,
  red count when failing; `QAResultBanner` and `PrintQAResult` use separate sub-headings.
- [x] **`QATraceOutput` TypeScript type** — explicit interface for QAAgent trace output shape.
- [x] **Trace export** — Export Trace JSON and Export Trace Markdown buttons on
  `/projects/[id]/traces`; browser-only Blob downloads; no new API endpoints.
- [x] **5 new backend regression tests** — 259 passing total.



- [x] QA score invariant enforced via `@model_validator` on `QAResult`
- [x] Feature taxonomy: CATEGORY_ALIASES extended (Agent Command Center, TRAE SOLO,
      Agent Requests, Agent Management, Agent Execution → "AI Agents";
      Cloud Agents / Devin Cloud → "Cloud Agents" separate canonical)
- [x] Writer `_build_feature_comparison()` merges same-canonical categories (no duplicate rows)
- [x] `IssueType.brand_mismatch` (low severity, advisory) with `_PRODUCT_BRAND_MAP`
- [x] Persona fallback descriptions derived from product name + positioning hint
- [x] 254 tests passing (+15 new)



## Component Status

| Component | Status |
|-----------|--------|
| FastAPI backend | ✅ Complete |
| SQLite database | ✅ Complete |
| CollectorAgent (demo fixtures) | ✅ Complete |
| CollectorAgent (live + fallback) | ✅ Complete (v1) |
| AnalystAgent (two-stage extraction) | ✅ Complete |
| WriterAgent (deterministic pricing + features) | ✅ Complete |
| QAAgent (rule-based, rework routing) | ✅ Complete |
| QAAgent source coverage checks | ✅ Complete (v1) |
| LangGraph workflow with rework loop | ✅ Complete |
| SourceDiscoveryService | ✅ Complete (v1) |
| SourceClassifier | ✅ Complete (v1) |
| CoverageEvaluator | ✅ Complete (v1) |
| HTTP crawler (httpx + BeautifulSoup) | ✅ Complete (v1) |
| 239 passing tests | ✅ Complete (v1 hardening) |
| QA score invariant (`@model_validator`) | ✅ Complete (Phase 2) |
| Feature taxonomy merge in writer | ✅ Complete (Phase 2) |
| Brand mismatch advisory check | ✅ Complete (Phase 2) |
| Persona fallback descriptions | ✅ Complete (Phase 2) |
| 254 passing tests | ✅ Complete (Phase 2) |
| SourceClassifier content validation | ✅ Complete (v1 hardening) |
| Bad-page blocklist (Discord/captcha/Cloudflare) | ✅ Complete (v1 hardening) |
| QA source quality checks (`weak_source_quality`) | ✅ Complete (v1 hardening) |
| Feature taxonomy normalization | ✅ Complete (v1 hardening) |
| Real DeepSeek LLM workflow end-to-end | ✅ Complete |
| Token usage tracking | ✅ Complete |
| Dedicated print/export page (`/print`) | ✅ Complete |
| Next.js frontend (4 pages) | ✅ Complete |
| Data mode selector (frontend) | ✅ Complete (v1) |
| Live/Demo source badges | ✅ Complete (v1) |
| Report viewer UI (7 tabs) | ✅ Complete |
| Agent trace timeline UI | ✅ Complete |
| Source citation side panel | ✅ Complete |
| AgentDAG visualization (React Flow) | ✅ Complete |
| QA-failed / partial report visibility | ✅ Complete (Milestone 11) |
| Industry-type source discovery | ✅ Complete (Milestone 12) |
| `InsufficientDataView` + insufficient-data gate | ✅ Complete (Milestone 12) |
| Industry type selector (frontend) | ✅ Complete (Milestone 12) |
| Fixed fallback semantics (demo vs live_with_fallback) | ✅ Complete (Milestone 12) |
| Coverage-quality analyzed/dropped gate | ✅ Complete (Milestone 12) |
| `analysis_purpose` field + workflow propagation | ✅ Complete (Milestone 13A) |
| `custom_dimensions` + analyst/writer injection | ✅ Complete (Milestone 13A) |
| `CompetitorRole` annotation end-to-end | ✅ Complete (Milestone 13A) |
| `social` IndustryType + source discovery paths | ✅ Complete (Milestone 13A) |
| Scoring schemas (DimensionScore, CompetitorScore, OpportunityScore) | ✅ Complete (Milestone 13A) |
| WriterAgent purpose-specific sections + scoring | ✅ Complete (Milestone 13A) |
| QAAgent advisory purpose checks (medium severity) | ✅ Complete (Milestone 13A) |
| ScoringMatrix.tsx + PurposeSections.tsx (frontend) | ✅ Complete (Milestone 13A) |
| Report viewer purpose tab ("Build Insights" / "Decision Guide") | ✅ Complete (Milestone 13A) |
| Print page scoring + purpose sections | ✅ Complete (Milestone 13A) |
| `pm_sections.py` schema (MarketBackground, FeatureInsights, OperationMonetization) | ✅ Complete (Milestone 13B) |
| WriterAgent PM-framework section instructions | ✅ Complete (Milestone 13B) |
| QAAgent advisory PM checks (check_pm_sections) | ✅ Complete (Milestone 13B) |
| MarketBackground.tsx + FeatureInsights.tsx + OperationMonetization.tsx | ✅ Complete (Milestone 13B) |
| Report viewer "Market & Ops" tab | ✅ Complete (Milestone 13B) |
| Print page PM-framework sections | ✅ Complete (Milestone 13B) |
| `SearchProvider` protocol + `TavilySearchProvider` + `NullSearchProvider` | ✅ Complete (Milestone 14) |
| `SearchService` (query templates, `_is_crawlable` URL filter, `_SEARCH_MAX_URLS=5`) | ✅ Complete (Milestone 14) |
| `CollectorAgent._normalize_url()` (tracking param stripping) + `_deduplicate_urls()` | ✅ Complete (Milestone 14) |
| `source_discovery.get_industry_max_pages()` public helper | ✅ Complete (Milestone 14) |
| `data_source="search"` badge + `SourceCountChip` search count (frontend) | ✅ Complete (Milestone 14) |
| `CandidateSource` schema (display-only candidates, not evidence) | ✅ Complete (Milestone 15A) |
| `POST /api/search/sources` endpoint | ✅ Complete (Milestone 15A) |
| `CandidateSourcePanel.tsx` per-competitor search picker (frontend) | ✅ Complete (Milestone 15A) |
| `CompetitorInput.extra_urls` end-to-end (frontend → API → CollectorAgent) | ✅ Complete (Milestone 15A) |
| `CandidateCompetitor` schema (competitor discovery candidates) | ✅ Complete (Milestone 15B) |
| `POST /api/search/competitors` endpoint | ✅ Complete (Milestone 15B) |
| `CompetitorDiscoveryPanel.tsx` industry-driven competitor picker (frontend) | ✅ Complete (Milestone 15B) |
| QA severity refactor (high=blocking, medium=warning, low=advisory) | ✅ Complete (Milestone 16) |

---

## Current Focus

Fix M15B competitor discovery quality before starting M17.

## Next Steps

### After M13B (v2)

1. Add frontend automated tests (Playwright E2E for the golden path)
2. Improve `user_personas` (needs/pain_points currently empty when LLM omits them)
3. Add project title field to creation form (currently shows project_id in listings)
4. Pagination on projects list page (currently unbounded)
5. Add PostgreSQL support as an alternative to SQLite
6. Improve MarkdownTab prose styling (code blocks, tables, lists)
7. Expand live crawler beyond well-known paths (sitemap parsing, link following with depth limit)
8. Persist robots.txt cache and crawl budget per project

---

## Known Limitations (Not Blocking v1)

- `user_personas` needs/pain_points are empty stubs when LLM omits them
- Live crawler limited to well-known paths on the root domain (no link following, no sitemap parsing)
- Single-user, no auth
- SQLite only (no PostgreSQL)
- No frontend automated tests

---

## Risks

### Risk 1: Web data collection instability

Mitigation: Use fallback demo data. Store source snapshots. Allow manual source input.

### Risk 2: LLM output format instability

Mitigation: Two-stage extraction pipeline (RawCompetitorExtraction → normalization_service). StrList coercion for list/string quirks. Rule-based QA rejects malformed outputs.

### Risk 3: QA feedback loop becomes fake

Mitigation: Rule-based QA checks implemented. Deterministic pricing/feature overrides prevent LLM from contradicting structured data. Rework routing tested with integration tests.

### Risk 4: Demo latency too high

Mitigation: ENABLE_DEMO_FIXTURES=true for offline dev. DeepSeek API significantly cheaper than OpenAI for live runs.
