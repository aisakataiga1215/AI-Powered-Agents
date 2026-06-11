# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased] — LLM Provider Switch and Function Calling

### LLM Provider

- **Switched from DeepSeek to Volcengine Doubao (火山引擎豆包)**: `OPENAI_BASE_URL` now points to `https://ark.cn-beijing.volces.com/api/v3` and `DEFAULT_MODEL` uses a Volcengine endpoint ID (`ep-20260514111325-xjmj7`). The Doubao endpoint is OpenAI-compatible and supports full function calling.
- Removed `LLM_DISABLE_THINKING` setting from `.env` — the Volcengine endpoint does not require disabling thinking mode. The setting still exists in `.env.example` (default `false`) and in `config.py` (default `false`) for any providers that may need it.
- Updated `OPENAI_INPUT_PRICE_PER_1M` and `OPENAI_OUTPUT_PRICE_PER_1M` defaults to match gpt-4o pricing in `config.py`.

### Function Calling

- **AnalystAgent**: Primary output path is now function calling via `ChatOpenAI.with_structured_output(RawCompetitorExtraction, method="function_calling", include_raw=True)`. Falls back to JSON output mode (`response_format: json_object`) only when function calling raises an exception. Trace records `parse_status` as `function_calling_parsed`, `json_output_parsed`, or `llm_error_fallback_empty`. Token usage is extracted from the raw provider metadata.
- **WriterAgent**: Same dual-path pattern — primary is function calling via `with_structured_output(CompetitiveReport, ...)`, with JSON output fallback. The `_produce_report_function_calling()` helper raises on tool-call/parsing failure so the caller can fall back to JSON mode without marking the report as a true fallback.
- Both agents build their `ChatOpenAI` clients via a shared `_build_base_llm(json_mode=False)` helper that respects `OPENAI_BASE_URL` and `LLM_DISABLE_THINKING`.

### QA Improvements

- **Industry-specific issue detection**: QA checks now correctly identify issues for any industry (not just AI-coding). Source coverage checks, pricing existence checks, and feature-tree checks all work with the generic competitor names from any industry.
- Pass threshold remains **80/100** with high-severity blocking only. `max_repair_loops=1` unchanged.

### Collector Enhancement: Hint-Keyword Rework Queries

- When QA reports missing pricing or features sources during a rework loop, `CollectorAgent._collect_live()` passes `rework_hints` to `SearchService.discover_urls()`.
- `SearchService._HINT_KEYWORD_QUERIES` maps hint keywords to targeted Tavily search templates:
  - `pricing` -> `"{name} official pricing plans subscription cost"`
  - `features` -> `"{name} features overview capabilities"`
  - `docs` -> `"{name} official documentation docs"`
  - `security` -> `"{name} security privacy compliance"`
  - `enterprise` -> `"{name} enterprise plan business pricing"`
- `_build_hint_queries()` generates extra search queries from QA rework hint text; these are **prepended** to the standard industry templates so they take priority in URL discovery.

### Prompt Bias Fix

- **Analyst prompt** (`analyst.md`): Example JSON changed from Cursor/AI-coding product to a generic SaaS product (small business tool with collaboration, reporting, integrations). Added a **CRITICAL** instruction: "The product and industry may be anything — food delivery, ecommerce, AI tools, design software, etc. Do NOT assume AI/coding terminology."
- **Writer prompt** (`writer.md`): Example title changed from `"AI Coding Tools"` to `"Project Management Tools"`.
- **Fallback executive summary** (`writer_agent.py`): Changed from AI-coding-specific text (mentioning `Claude Code`, `Copilot`, model access, agent limits) to industry-neutral text covering capabilities, user experience, pricing strategy, and ecosystem maturity.
- **Fallback strategic recommendations** (`writer_agent.py`): Changed from AI-coding-specific (SSO, audit, agent limits, model credits) to industry-neutral (privacy, SSO, audit, usage-management controls).

### Frontend Fixes

- **Report page `isInsufficientData` gate** (`report/page.tsx`): Removed the `analysedCount < 2` and `qaScore < 30` checks. Now only shows the insufficient-data view when `citedSources === 0 || summaryLen === 0`. Reports with sources and summary claims but low competitor counts or low QA scores render normally instead of showing "数据不足".
- **AgentDAG visualization** (`AgentDAG.tsx`):
  - Emoji icons per agent (Collector=📡, Analyst=🧠, Writer=📝, QA=🛡️, END=🏁)
  - Status dot (colored circle, top-right of each node)
  - Pulse animation on running nodes (CSS keyframes)
  - Arrow markers on all forward edges (smoothstep type with `MarkerType.ArrowClosed`)
  - QA rework edges: dashed amber arcs with "QA 打回" label badge
  - PASS label on the QA-to-END edge when QA passed
  - Legend panel at bottom-center

### Bug Fixes

- Removed 8 accidentally committed debug files: `docs/.system_architecture_baked.svg`, `dag_verify2.png`, `dag_verify3.png`, `workflow_current.png`, `workflow_diagram.png`, `workflow_updated.png`.
- Removed `LLM_DISABLE_THINKING` from `.env` (default `false` in `config.py` is correct for the Volcengine endpoint).

---

## M17.1.1 — Print/PDF Custom Dimension Coverage

### Frontend
- Added custom dimension analysis to the print/PDF report page, including score, rationale, evidence source IDs, and confidence.
- Verified the print/PDF page with Chrome DevTools MCP after generating an AI coding tools report with custom dimensions.

### Tests
- Verified frontend lint and production build.

---

## M17.1 — Purpose-Driven Decision Support Phase 1

### Backend
- Canonicalized `analysis_purpose` to four decision intents: `build_similar_product`, `choose_product_to_use`, `market_research`, and `competitor_success_analysis`.
- Added legacy purpose normalization for stored/API compatibility while rejecting unknown public create values with 422 validation.
- Threaded canonical purpose values through project persistence, API responses, LangGraph initial state, AnalystAgent, WriterAgent, and QAAgent.
- Updated default persisted report/project purpose to `market_research`.
- Restored `research_inputs` create/get/run propagation in `ProjectCreate` while updating purpose validation.

### Frontend
- Replaced purpose choices with four Chinese decision-intent labels.
- Added custom-dimension suggestion chips, trim/dedupe behavior, and max-8 cap in project creation.
- Updated report and print purpose tabs/sections for all four canonical purposes.
- Improved scoring matrix rendering so dimensions from any competitor are visible.
- Generic purpose evidence arrays now render as clickable source badges when source IDs are known.

### Tests
- Added/updated backend coverage for canonical round trip, legacy normalization, unknown-purpose rejection, workflow state normalization, QA purpose checks, and graph regressions.
- Verified frontend lint and production build.

---

## M16.2 - Search and Discovery Quality Recovery

### Competitor Discovery
- Boost known AI coding product domains (Cursor, Copilot, Claude Code, Trae, Windsurf, Tabnine, Qodo, Codeium, Replit, Amazon Q Developer) for ai_saas industry type
- Raise _DISCOVERY_MIN_SCORE from 40 to 60 to filter marginal candidates
- Add _LISTICLE_TITLE_END_RE to catch titles ending with listicle keywords (e.g. "AI Coding Tools Comparison")
- Add brand negative-term penalty: ambiguous brand names (windsurfing, surf, sailing, board, kite, weather, sport) capped at score <= 35 when no AI/coding signals present
- Known AI product domains exempt from negative-term penalty
- GitHub deep repo paths (e.g. github.com/openearth/windsurf) not boosted as product pages
- Improve non-AI category robustness for ecommerce, local services, social, and general discovery by filtering research/publisher domains, app-store pages, blog subdomains, root-level listicle slugs, and market-report URLs
- Social discovery now only uses dating-specific templates when the user query is dating-related
- Company-name extraction trims noisy title suffixes around separators so UI candidates are shorter and easier to review

### Source Search (search_sources)
- Two-pass search strategy: pass 1 uses include_domains for official domain + aliases; pass 2 falls back to general web search
- Add _PRODUCT_DOMAIN_ALIASES mapping for Windsurf, Cursor, Trae, Codeium, Devin and others
- Use search_depth="advanced" on all Tavily queries

### Source Classifier
- windsurf.readthedocs.io and other third-party hosting domains (readthedocs.io, gitbook.io, github.io, etc.) no longer classified as official_website
- _infer_source_confidence now excludes third-party hosting platforms from high-confidence official sources

### Tavily Provider
- Extend SearchProvider protocol and TavilySearchProvider with search_depth, topic, include_domains, exclude_domains, exact_match parameters

### Tests
- TestDiscoverCompetitorsM162: known AI products score high, article paths <= 30, listicle titles <= 15, min score 60 enforced, brand negative terms, windsurf.ai not penalized, github.com/openearth/windsurf low score
- Cross-category discovery regressions cover ecommerce, local_services, social, and general false positives plus positive homepage controls
- TestSourceClassifierM162: readthedocs.io root not official_website, github.io not official_website, cursor.com is official_website, windsurf.com is official_website
- TestSourceConfidenceM162: readthedocs.io not high confidence, official domain = high confidence, review site = low confidence

### Limitation
General competitor discovery still uses heuristic search-result scoring. Only the AI SaaS path extracts known product names from listicle snippets; other categories suppress noisy publisher/listicle pages instead of mining them for product names.

---

## M16.1 — Discovery Quality Recovery (In Progress)

Real Tavily tests showed M15B competitor discovery returning false-positive candidates
such as Zapier, DigitalOcean blog pages, Gartner, DevGenius Blog, and Axify articles.

### Backend (`backend/app/services/search_service.py`)
- Added `_ARTICLE_PATH_RE`: caps relevance_score at 30 for URLs with blog/article/guide/review paths
- Added `_BLOG_DOMAIN_RE`: scores `.blog` TLD and ghost.io domains at 5
- Extended `_LISTICLE_TITLE_RE`: covers guide, complete guide, how to, I tested, full comparison
- Expanded `_DISCOVERY_BLOCKED_DOMAINS`: added gartner.com, forrester.com, hackernoon.com, dev.to, hashnode.dev, dzone.com, infoq.com, thenewstack.io
- Added `_DISCOVERY_MIN_SCORE = 40`: discover_competitors() filters candidates below threshold
- Added homepage depth bonus (+15 for root path) to reliably push product homepages above min score
- DigitalOcean/Zapier remain unblocked at domain level — only their article/blog paths are penalized

### Frontend (`frontend/app/page.tsx`)
- CompetitorDiscoveryPanel.onAdd now deduplicates by normalized domain and name against existing competitors

### Tests (`backend/tests/test_search_service.py`)
- 8 new regression tests in `TestDiscoverCompetitorsQuality`
- Covers: Gartner blocked, article path scores <= 30, product homepage >= min score, all returned candidates >= `_DISCOVERY_MIN_SCORE`, results sorted by score, DigitalOcean/Zapier not globally blocked

### Scope
Does not extract product names from listicle pages. Only prevents listicle/publisher
domains and article paths from being treated as competitor candidates.

---

## M16 — QA Severity Semantics Refactor

### Backend
- `backend/app/agents/qa_agent.py`: QA issue severity semantics tightened.
  - `high` = blocking issue; forces workflow failure.
  - `medium` = warning; deducts score but workflow can still pass.
  - `low` = advisory; no score deduction.
- `blocking_issue_count` now counts only `high` severity (previously counted high + medium). `medium_severity_count` is surfaced as the "warnings" count.

### Frontend
- `frontend/lib/types.ts`: updated typing comments to match new severity semantics.
- `frontend/components/qa/QAResultBanner.tsx`, `frontend/app/projects/[id]/report/page.tsx`, `frontend/app/projects/[id]/traces/page.tsx`, `frontend/app/projects/[id]/print/page.tsx`: banner / tab badge / PDF copy updated to render the new categories.
  - Passed example: `QA Passed · Score 95/100 · 1 warning · 2 advisories`
  - Failed example: `QA Failed · Score 55/100 · 2 blocking issues · 3 warnings`

### Tests
- `backend/tests/test_qa_trace_output.py`: regression tests updated for the new severity counting rules (blocking = high only).

---

## M15B — Competitor Discovery

Builds on M15A. Given an industry or topic, surfaces candidate competitor products for user selection — before the user knows any competitors. M15A handles per-competitor source search; M15B handles competitor discovery itself.

### Backend
- New `backend/app/schemas/discovery.py`: `CandidateCompetitor` model with provenance fields (`raw_title`, `source_url`, `domain`) and quality signals (`relevance_score` 0–100, `relevance_reason`, `role_confidence`). Suggested role defaults to `direct_competitor`.
- `backend/app/services/search_service.py`: new `discover_competitors()` method. Constants — `_DISCOVERY_BLOCKED_DOMAINS` (aggregators, listings, news sites excluded from candidate results), `_LISTICLE_TITLE_RE` (filters "Top 10…" / "Best of…" style titles), `_DISCOVERY_TEMPLATES` (per-industry templates including `ai_saas` and `social`). New helpers — `_extract_company_name()`, `_score_competitor_relevance()`.
- New endpoint `POST /api/search/competitors` (`backend/app/api/routes/search.py`): accepts `{ industry, industry_type }`, returns `list[CandidateCompetitor]`.

### Frontend
- `frontend/lib/types.ts`: added `CandidateCompetitor` interface.
- `frontend/lib/api.ts`: added `discoverCompetitors()` client.
- New `frontend/components/competitor/CompetitorDiscoveryPanel.tsx`: "Discover competitors" trigger, candidate list with relevance score badge, `source_url`, "Suggested role: Direct Competitor" label, "Add N selected" button.
- `frontend/app/page.tsx`: panel mounted in the Competitors section header alongside the "+ Add competitor" control.

### Behavior
- **Activation**: reuses M14 flags — requires `ENABLE_LIVE_SEARCH=true` and `TAVILY_API_KEY` set.
- **No DB changes**: candidates are selection input only; once accepted they enter the form as ordinary `CompetitorInput` rows.
- **Domain hygiene**: aggregators / listicles / news sites are filtered out so candidates point at actual product sites.

### Tests
- 11 new tests — 8 in `backend/tests/test_search_service.py` (service-level), 3 in `backend/tests/test_search_api.py` (API-level).

---

## M15A — Interactive Source Search

### Backend
- New `backend/app/schemas/search.py`: `CandidateSource` Pydantic model (10 fields — `candidate_id`, `competitor_name`, `url`, `title`, `snippet` [display-only], `suggested_source_type`, `discovery_query`, `provider`, `confidence`, `reason`, `selected_by_default`). `CandidateSource` is **not evidence** — it becomes a `SourceEvidence` only after the user selects a URL and `CrawlerService` crawls it.
- `backend/app/schemas/competitor.py`: `CompetitorInput` extended with `extra_urls: list[str]` for user-selected URLs to include in live collection.
- `backend/app/services/search_provider.py`: added `create_provider_from_settings()` factory.
- `backend/app/services/search_service.py`: added `search_sources()` method alongside `discover_urls()`. New constants — `_GOAL_QUERY_TEMPLATES`, `_DEFAULT_SOURCE_QUERIES`, `_SOURCE_TYPE_PRIORITY`. New helpers — `_infer_source_confidence()`, `_infer_source_reason()`.
- New `backend/app/api/routes/search.py`: `POST /api/search/sources` endpoint — interactive per-competitor candidate search; returns `list[CandidateSource]`.
- `backend/app/main.py`: registered the search router.
- `backend/app/agents/collector_agent.py`: `_collect_live()` now accepts an `extra_urls` param; trace output includes `selected_extra_urls`, `silent_search_urls`, and `rejected_extra_urls` for observability.

### Frontend
- `frontend/lib/types.ts`: added `CandidateSource` interface; extended `CompetitorInput` with optional `extra_urls?: string[]`.
- `frontend/lib/api.ts`: added `searchSources()` client.
- New `frontend/components/search/CandidateSourcePanel.tsx`: per-competitor search panel for discovering and selecting candidate URLs.
- `frontend/app/page.tsx`: integrated `CandidateSourcePanel` below each competitor row with stable key management; submits selected `extra_urls` in project payload.

### Behavior
- **Activation**: reuses M14 flags — requires `ENABLE_LIVE_SEARCH=true` **and** `TAVILY_API_KEY` set.
- **Unavailable state**: panel shows a disabled state with a clear message (not silently hidden).
- **Tavily snippets**: display-only in the candidate picker; never stored as `SourceEvidence.content`.
- **M14 silent background search**: unchanged — `_collect_live()` continues to run search alongside known-path discovery for the workflow.
- **User-selected URLs**: merged into the live collection cap with the rest of the discovered URLs.

### Tests
- Total: **332 backend tests passing** (+16 new).

---

## M14 — Search-Plus-Crawl (Tavily)

### Backend
- New `backend/app/services/search_provider.py`: `SearchResult` Pydantic model, `SearchProvider` Protocol, `TavilySearchProvider` (wraps Tavily SDK), `NullSearchProvider` (no-op), `create_search_provider()` factory. Active when `ENABLE_LIVE_SEARCH=true` and `TAVILY_API_KEY` is set; otherwise degrades to `NullSearchProvider`.
- New `backend/app/services/search_service.py`: industry-keyed web search query templates, `_is_crawlable()` URL filter (`_BLOCKED_DOMAINS` covers youtube/twitter/reddit/linkedin etc., `_UNSUPPORTED_EXTENSIONS` blocks binary/non-HTML), `_normalize_url()`, `SearchService.discover_urls()` capped at `_SEARCH_MAX_URLS=5`.
- `backend/app/schemas/source.py`: extended `data_source` `Literal` to include `"search"`. Indicates discovery channel only (not reliability) — every URL is still crawled and classified by `SourceClassifier`.
- `backend/app/core/config.py`: added `tavily_api_key: str = ""`.
- `backend/pyproject.toml`: added `tavily-python>=0.3.0` dependency.
- `.env.example`: added `TAVILY_API_KEY=`.
- `backend/app/services/source_discovery.py`: added public helper `get_industry_max_pages(industry_type)` so collector can query the industry-specific path cap.
- `backend/app/agents/collector_agent.py`: added `_normalize_url()` (strips tracking params `utm_*`, `fbclid`, `gclid` via `_TRACKING_PARAMS`), added `_deduplicate_urls()` to merge results across discovery channels, extended `_collect_live()` with `search_service` param and extended `run()` with `_search_service` injection param. Search-discovered URLs are tagged `data_source="search"`; combined per-competitor cap is `industry_max + 5`.

### Frontend
- `frontend/lib/types.ts`: added `'search'` to the `data_source` union.
- `frontend/components/source-viewer/SourcePanel.tsx`: new teal Search badge alongside Live/Demo badges.
- `frontend/app/projects/[id]/report/page.tsx`: `SourceCountChip` now also counts search-discovered sources.

### Behavior
- **Activation**: requires both `ENABLE_LIVE_SEARCH=true` **and** `TAVILY_API_KEY` set.
- **Default**: `ENABLE_LIVE_SEARCH=false` → `NullSearchProvider` → pre-M14 behavior (no regressions).
- **Demo mode**: search is never triggered.
- **Tavily errors**: caught per-query and globally; workflow continues with known-path URLs only.
- **Discovery channels**: search runs alongside `source_discovery` (path probing) as a second URL-discovery channel; both feed into `CollectorAgent._collect_live()`.

### Tests
- New `backend/tests/test_search_service.py`: 12 new tests (query templates, `_is_crawlable` filter, blocked domains/extensions, URL normalization, cap enforcement, error handling).
- Total: **316 backend tests passing** (+12 new).

---

## M13B — PM-Style Report Structure

### Backend
- New `pm_sections.py` schema: MarketTrend, MarketBackground, FeatureInsights, GtmProfile, OperationMonetization (Pydantic models)
- `report.py`: 3 new fields — market_background, feature_insights, operation_monetization (all `| None`, default graceful)
- `qa.py`: 3 new IssueType values — missing_market_background, missing_feature_insights, missing_operation_monetization
- WriterAgent: `_PM_SECTIONS_INSTRUCTION` constant appended to all user messages; `_normalize_report_payload` validates all 3 new sections with try/except
- QAAgent: advisory-only `check_pm_sections()` function (3 medium-severity checks, never affect pass/fail)

### Frontend
- New types: MarketTrend, MarketBackground, FeatureInsights, GtmProfile, OperationMonetization (in types.ts)
- `CompetitiveReport`: 3 new optional fields — market_background, feature_insights, operation_monetization
- `MarketBackground.tsx`: market overview, market_size_notes badge, trend list, drivers/challenges chip grid
- `FeatureInsights.tsx`: table-stakes chips, differentiator table (feature → competitors), gap opportunity cards, cross-competitor patterns
- `OperationMonetization.tsx`: GTM profile cards (motion badge, pricing strategy, acquisition channels, expansion), monetization patterns list, AARRR funnel table (5 stage rows × competitor columns)
- Report page: new "Market & Ops" tab at index 3 (after Features, before SWOT); purpose tab splice index updated to 6
- Print page: 3 new PrintSections — Market & Background, Feature Insights, Operations & Monetization

### Tests
- `test_pm_sections_schema.py`: 5 new schema validation tests
- `test_qa_pm_checks.py`: 5 new advisory QA check tests (including integration smoke with mocked DB)
- `test_qa_agent_integration.py`: updated _passing_report fixture to include PM sections so score=100 assertion holds



### Backend
- New `scoring.py` schema: DimensionScore, CompetitorScore, OpportunityScore with Pydantic validation (score 1-5, overall 0-100)
- `competitor.py`: CompetitorRole type + role field on CompetitorInput
- `project.py`: AnalysisPurpose type, social IndustryType, analysis_purpose + custom_dimensions fields
- `report.py`: 7 new fields — analysis_purpose, analysis_objective, competitor_selection_rationale, purpose_sections, competitor_scores, opportunity_score, custom_dimension_analysis
- `qa.py`: 2 new IssueType values — missing_custom_dimension_coverage, missing_score_rationale
- DB migrations: analysis_purpose, custom_dimensions on projects; role on competitors
- AnalystAgent: purpose/role/custom_dimensions injection into user message
- WriterAgent: scoring + purpose-specific section instructions; _normalize_report_payload handles all new fields
- QAAgent: advisory-only check_custom_dimensions() and check_scoring_rationale() (medium severity, no pass/fail impact)
- source_discovery: social industry paths added

### Frontend
- New types: AnalysisPurpose, CompetitorRole, SourceConfidence, DimensionScore, CompetitorScore, OpportunityScore, OpportunityDimension
- page.tsx: analysis purpose selector (3 radio cards), social industry card, custom dimensions input + tag chips, competitor role dropdown per row
- ScoringMatrix.tsx: choose_product competitor table with score color-coding; build_product single opportunity table
- PurposeSections.tsx: choose_product (recommendation_ranking, best_for, who_should_avoid, decision_matrix); build_product (market_gaps, features_to_learn_from, pitfalls_to_avoid, mvp_direction, differentiation_opportunities)
- Report page: dynamic purpose tab ("Build Insights" / "Decision Guide") + analysis_objective summary card
- Print page: PrintScoringSection + PrintPurposeSections added

### Tests
- test_api_projects.py: analysis_purpose + custom_dimensions + competitor role round-trip test
- test_qa_purpose_checks.py: 7 new tests for advisory QA checks
- test_scoring_schema.py: 5 new tests for scoring schema validation
- Total: 294 passing (was 280)

### Deferred
- M13B (PM-style report structure: Data & Background, Feature Insight, Op & Monetization)
- Milestone 14 (search_plus_crawl, SearchProvider, SearchService)

---

## Session 2026-06-07 — v1.5 Robustness Hardening (Milestone 12)

### Added

- **`IndustryType`** (`backend/app/schemas/project.py`): `Literal["ai_saas", "ecommerce", "local_services", "general"]`; default `"general"`. Added to `ProjectCreate` and `ProjectResponse`.
- **`industry_type` DB column** (`backend/app/db/models.py`): nullable=False, default="general". Idempotent SQLite migration in `_apply_migrations()`.
- **`_INDUSTRY_PATHS`** (`backend/app/services/source_discovery.py`): industry-keyed tuple of candidate URL paths; ordered by analysis value within each industry. ecommerce: 14 paths (seller/fees/shipping/returns first), local_services: 12 paths (merchant/dasher/delivery/membership/fees first), ai_saas: 10 paths, general: 6 paths. `CANDIDATE_PATHS` kept as backward-compat alias for ai_saas.
- **`_INDUSTRY_MAX_PAGES`** (`backend/app/services/source_discovery.py`): ecommerce/local_services=8 pages, ai_saas/general=5. `discover_pages()` now accepts `industry_type` param; uses industry default when `max_pages` not explicitly passed.
- **`industry_type` in `WorkflowState`** (`backend/app/graph/state.py`): threads industry context from project creation through to CollectorAgent.
- **`fixture_exists()`** (`backend/app/services/crawler_service.py`): side-effect-free check — returns True if a fixture file exists for the competitor name without parsing it.
- **`_CollectionResult` dataclass** (`backend/app/agents/collector_agent.py`): replaces bare 4-tuple. Fields: `sources`, `failed_urls`, `attempted_urls`, `live_source_count`, `fallback_attempted`, `fallback_used`, `fallback_available`, `fallback_source_count`.
- **`_is_adequately_covered()`** (`backend/app/agents/collector_agent.py`): coverage-quality gate for analyzed vs dropped determination. A competitor is analyzed if `coverage.score >= 40` OR `(homepage AND (pricing OR features_or_docs))`.
- **`_infer_drop_reason()`** (`backend/app/agents/collector_agent.py`): human-readable drop reasons: "No demo fallback available", "Crawl failed — no usable sources", "No demo fixture found", "Weak coverage — insufficient for analysis".
- **`attempted_urls_by_competitor`** in CollectorAgent trace output: per-competitor list of all URLs probed during discovery, for observability and debugging.
- **`sufficiently_collected_competitors`** in CollectorAgent trace output: list of competitor names that met coverage-quality threshold. Purely for `InsufficientDataView` gating — does NOT filter AnalystAgent.
- **`InsufficientDataView` component** (`frontend/components/report-viewer/InsufficientDataView.tsx`): renders when `isInsufficientData` is true. Shows: amber heading, metrics (cited sources / summary claims / QA score), per-competitor stats table, dropped competitors, QA issues (from `qaResult` directly), failed URLs (collapsible), attempted discovery URLs (collapsible), suggested next steps. Reads CollectorAgent trace for collection stats and URLs only.
- **`IndustryType` and `CompetitorCollectionStats`** (`frontend/lib/types.ts`): new TypeScript types. `ProjectCreate.industry_type?` and `ProjectResponse.industry_type?` added.
- **Industry type selector** (`frontend/app/page.tsx`): 4-option radio card group ("AI / SaaS", "E-commerce", "Local Services", "General") with same `border-2` card style as data_mode selector. Default `'general'`. Inserted between Industry field and Competitors list.

### Changed

- **`_collect_live()`** (`backend/app/agents/collector_agent.py`): calls `discover_pages(website, industry_type=industry_type)` without explicit `max_pages` so industry default applies. Uses `fixture_exists()` (side-effect-free) before conditionally calling `load_demo_fixtures()`.
- **Demo mode collection stats**: no longer include `fallback_*` fields. Only `source_count` and `demo_source_count`. Fallback fields are `live_with_fallback`-only semantics.
- **`run_workflow_background()`** (`backend/app/graph/workflow.py`): accepts `industry_type` param; passes it into `_initial_state()`.
- **`collect_sources_node()`** (`backend/app/graph/nodes.py`): forwards `state.get("industry_type", "general")` to `collector_agent.run()`.
- **Report page** (`frontend/app/projects/[id]/report/page.tsx`): reads `sufficiently_collected_competitors` from CollectorAgent trace to compute `analysedCount`; `isInsufficientData` gate replaces tabbed content when `citedSources==0 || summaryLen==0 || qaScore<30 || analysedCount<2`.
- **Print page** (`frontend/app/projects/[id]/print/page.tsx`): same `isInsufficientData` gate; renders `PrintInsufficientDataSection` (print-safe, no interactive elements) instead of full report sections.

### Tests (280 passing, +21 new)

- **`backend/tests/test_source_discovery_industry.py`** (NEW, 9 tests): industry path content, ordering, max_pages defaults, `CANDIDATE_PATHS` backward compat.
- **`backend/tests/test_collector_fallback_semantics.py`** (NEW, 8 tests): `fallback_attempted/used/available` semantics, demo mode no fallback fields, `_infer_drop_reason` outputs.
- **`backend/tests/test_api_projects.py`**: `test_industry_type_round_trips_through_create_and_get` added.
- **`backend/tests/test_graph_workflow.py`**: `fake_collector` signatures updated to accept `industry_type` kwarg.
- **`backend/tests/test_collector_agent_live.py`**: `fixture_exists` mock added; assertions updated to read per-competitor stats.

---



### Added

- **`CompetitorInProject` schema** (`backend/app/schemas/project.py`): new model `{ name, url }`;
  `ProjectResponse.competitors` field exposes every requested competitor in `GET /projects/{id}`.
- **`_to_response()` update** (`backend/app/api/routes/projects.py`): populates `competitors`
  from the SQLAlchemy ORM relationship (lazy-loaded; session is open at call time).
- **`CompetitorInProject` TypeScript type** (`frontend/lib/types.ts`): mirrors backend;
  added to `ProjectResponse.competitors?: CompetitorInProject[]`.
- **`QaStatusBanner` component** (`frontend/components/qa/QaStatusBanner.tsx`): orange warning
  banner for `qa_failed` projects; red banner for `failed` projects. Shows dropped-competitor
  count when provided.
- **`DroppedCompetitorsList` component** (`frontend/components/report-viewer/DroppedCompetitorsList.tsx`):
  renders an orange-framed list of competitors that were requested but not analysed, with a
  human-readable reason for each.
- **`computeDroppedCompetitors` + `inferDropReason` helpers** (in `report/page.tsx` and
  `print/page.tsx`): derives dropped competitors by diffing `requestedCompetitors` vs
  `report.competitor_overview`. Reason is inferred from CollectorAgent trace output fields
  (`failed_urls`, `source_coverage_by_competitor`, `data_mode`). For demo-mode projects with
  no demo fixture, reason is "No demo fixture found".

### Changed

- **Report page** (`frontend/app/projects/[id]/report/page.tsx`):
  - Added `useQuery` for `api.getProject(id)` to obtain `status` and `competitors`.
  - Shows `QaStatusBanner` when status is `qa_failed` or `failed`.
  - Header chip shows "N of M analysed (K dropped)" when any competitors were dropped.
  - QA tab shows `DroppedCompetitorsList` below `QAResultBanner` when relevant.
  - Export PDF button label changes to **"Export Partial PDF"** for `qa_failed` projects.
- **Print page** (`frontend/app/projects/[id]/print/page.tsx`):
  - Added `useQuery` for `api.getProject(id)`.
  - Warning banner rendered at the top of the printed document for `qa_failed`/`failed`.
  - "Dropped / Insufficient Competitors" `PrintSection` inserted between QA Result and References.

---

## Session 2026-06-07 — QA Display Fix + Trace Export


### Fixed

- **QA display mismatch**: QAAgent trace output now includes the full `issues` array in addition
  to scalar counts. Previously, only `issue_count` and `high_severity_count` were stored; the
  frontend `extractLatestQA()` fell back to `[]`, so UI and PDF always showed 0 issues.
  `backend/app/agents/qa_agent.py` now calls `_build_trace_output(result, issues)` which
  serialises every `QAIssue` via `model_dump(mode="json")`.

### Added

- **`_build_trace_output` helper** (`backend/app/agents/qa_agent.py`): Extracted as a
  standalone function for testability. Adds `medium_severity_count`, `low_severity_count`,
  `blocking_issue_count`, and `advisory_count` alongside the full `issues` list.
- **Advisory display**: Low-severity QA issues are now labelled "advisory" throughout the UI
  (not "blocking"). `QAResultBanner`, the QA tab badge (`report/page.tsx`), and `PrintQAResult`
  all distinguish blocking (high/medium) from advisory (low) issues.
  - Tab badge: green "ok" (no issues), amber "N adv" (advisories only), red count (blocking).
  - Banner: separate "Blocking Issues" and "Advisories" sub-headings.
  - Print/PDF: same grouping with separate headings.
- **`QATraceOutput` TypeScript interface** (`frontend/lib/types.ts`): Typed shape for the
  QAAgent trace output; `extractLatestQA()` in report and print pages now casts against it.
- **Trace export** (`frontend/app/projects/[id]/traces/page.tsx`):
  - **Export Trace JSON** — downloads `{project_id}_traces.json` with project metadata,
    `exported_at`, `trace_count`, and the full `traces` array.
  - **Export Trace Markdown** — downloads `{project_id}_traces.md` with one section per agent
    (status, latency, token usage, full fenced JSON input/output), and a QA summary section
    with per-issue/advisory sub-headings. No truncation.
  - Both use browser `Blob` download only; no new API endpoints.
- **5 new backend regression tests** (`backend/tests/test_qa_trace_output.py`):
  - `issues` array present and correct in trace output
  - `issue_count == len(issues)` consistency
  - `score < 100` implies `blocking_issue_count > 0` (invariant)
  - Advisory-only issues leave score at 100
  - Empty issues produce all-zero counts

### Changed

- **`extractLatestQA()`** in `report/page.tsx` and `print/page.tsx` updated to cast against
  `Partial<QATraceOutput>` instead of `Partial<QAResult>`.

---

## Session 2026-06-07 — Bug Fix + Handoff

### Fixed

- **CORS preflight 400**: `allow_origins` changed to `["*"]` (dev) in `backend/app/main.py`.
  Was returning 400 for OPTIONS preflight when browser origin didn't exactly match the list.
- **"Failed to fetch" on Create Project**: `NEXT_PUBLIC_API_BASE_URL` changed to
  `http://127.0.0.1:8000` in `frontend/.env.local` — Windows 11 resolves `localhost`
  to IPv6 `::1` but uvicorn binds to IPv4 `127.0.0.1` only.

### Added

- `docs/handoff_trace_export_and_qa_display.md` — handoff document for next session covering
  QA display mismatch bug, trace export feature, and architecture conventions.

---

## Phase 2 — Report Quality Polish

**Date:** 2026-06-05

### Changed

- **QA score invariant enforced**: `QAResult` now derives `score` from `issues` via
  `@model_validator`. Any manually passed score is overridden. Deduction rule:
  high = −15, medium = −5, low = 0 (advisory only). Empty issues always yield 100.
- **Feature taxonomy merges in writer**: `_build_feature_comparison()` accumulates
  features per canonical category before building the comparison string. "AI Agent" +
  "Agent Management" rows are now merged into one "AI Agents" row.
- **CATEGORY_ALIASES expanded**: Added Agent Command Center, TRAE SOLO, Agent Requests,
  Agent Management, Agent Execution → "AI Agents". Changed "Cloud Agents" / "Devin Cloud"
  → "Cloud Agents" (separate canonical, was incorrectly "AI Agents").
- **Persona fallback improved**: Replaced generic placeholder with derived description:
  `"{user_text} using {product} — {pos_hint}"` or product-centric phrasing when
  positioning is absent.

### Added

- **`IssueType.brand_mismatch`**: Low-severity advisory issue flagged when a competitor's
  source prominently mentions another brand ≥2 times in title + first 500 chars.
  Includes `_PRODUCT_BRAND_MAP` for known brand families (Windsurf → Devin/Cognition).
  Does not affect score or pass/fail.
- **15 new tests** — `test_qa_coverage.py` (+7), `test_feature_taxonomy.py` (+6),
  `test_normalization_service.py` (new, 5 tests). Total: **254 tests passing**.

---

## v1 Hardening — Source Quality Validation

**Date:** 2026-06-04

Fixes false-positive coverage scores caused by redirected/blocked pages (Discord,
Cloudflare) being classified as valid pricing or features sources. QA previously
scored 100/100 despite Windsurf's pricing/features pages all redirecting to Discord.

### Added

- **`_is_bad_page()` in `crawler_service`**: checks both title and body preview
  (first 300 chars) for Discord, Cloudflare, captcha, and access-denied patterns.
  Returns `None` from `crawl_page()` for matching pages, same as a non-200 response.
- **`_validate_by_content()` in `source_classifier`**: after URL-path classification,
  content must confirm the assigned `SourceType`. If content is non-empty but lacks
  matching keywords (e.g., pricing keywords for `pricing_page`), the source is
  downgraded to `SourceType.unknown`. If content is empty, URL path is trusted
  (backward-compatible for tests and sparse pages).
- **`IssueType.weak_source_quality`** and **`IssueType.source_type_content_mismatch`**:
  two new QA issue types for source-content mismatch.
- **`check_source_quality()` in `qa_agent`**: per-source content check, parallel to
  `check_source_coverage()`. Severity tiering:
  - `high` — content has explicit bad signals (Discord, captcha, login wall)
  - `medium` — content is non-empty but lacks keywords for the declared type
  - Normal pages that pass keyword matching: not flagged
- **`CATEGORY_ALIASES` + `normalize_feature_category()` in `normalization_service`**:
  maps LLM-emitted category variants to canonical names before storing `feature_tree`.
  Applied in both `_normalize_features()` and `writer_agent._build_feature_comparison()`
  so the report table never shows "AI Agent" and "AI Agents" as separate rows.
- **13 new tests** — `test_source_classifier.py` (+6), `test_qa_coverage.py` (+4),
  `test_feature_taxonomy.py` (new file, 4 tests). Total: **239 tests passing**.

### Behavior change

`source_classifier.classify()` no longer treats URL path as an absolute override when
content is available. A `/pricing` URL with Discord content now returns `SourceType.unknown`
instead of `pricing_page`. This causes the coverage evaluator to correctly drop the
coverage score, triggering the demo fallback for competitors like Windsurf.

---

## v1 — Live Data Collection

Adds per-project live data collection with demo fallback, source-type classification, and per-competitor coverage evaluation. Demo fixtures remain the stable default.

### Added

- **`source_discovery.py` service**: Probes well-known paths (`/pricing`, `/features`, `/docs`, `/about`, `/security`, `/privacy`) on the competitor root domain. Returns up to 5 candidate URLs per competitor.
- **`source_classifier.py` service**: URL-path-first keyword classifier mapping discovered pages to `SourceType` (new types added: `features_page`, `security`, `privacy`, `unknown`).
- **`coverage_evaluator.py` service**: Per-competitor source coverage scoring — homepage=30, pricing=30, features/docs=30, security/privacy=10. `WEAK_THRESHOLD=40`. `evaluate_per_competitor()` groups by competitor name.
- **`CrawledPage` dataclass** and **`crawl_page()`** in `crawler_service.py`: httpx + BeautifulSoup, 10s timeout, 1 retry, best-effort robots.txt via `_is_allowed_by_robots()`.
- **`CollectorAgent._collect_live()`**: Per-competitor live collection path with fallback merge when `data_mode == "live_with_fallback"`.
- **`QAAgent.check_source_coverage()`**: Per-competitor QA issues when goals require sources not present in evidence. New `IssueType` values: `missing_pricing_source`, `missing_features_source`.
- **Frontend `data_mode` selector**: Radio group on the project creation page (Demo fixtures / Live crawl with fallback).
- **Live/Demo source badges**: `SourcePanel.tsx` displays a Live/Demo badge after the reliability badge. Report viewer source count line now shows `N sources cited · M live · K demo`.
- **5 new test modules**: `test_crawler_service.py`, `test_source_discovery.py`, `test_source_classifier.py`, `test_collector_agent_live.py`, `test_qa_coverage.py`. Total: 226 tests passing.

### Schema Changes

- `SourceEvidence.data_source: Literal["live", "demo"] = "demo"` (new field)
- `SourceType`: added `features_page`, `security`, `privacy`, `unknown`
- `ProjectCreate.data_mode: Literal["demo", "live_with_fallback"] = "demo"` (new field)
- `ProjectResponse.data_mode: str = "demo"` (new field)
- `IssueType`: added `missing_pricing_source`, `missing_features_source`

### DB Migrations

- `Project.data_mode` column — idempotent `ALTER TABLE` at startup in `session.py`.
- `Source.data_source` column — same idempotent migration pattern.

### Changed

- `CollectorAgent.run()` now accepts a `data_mode` parameter; routes per-competitor between live and demo paths and merges results.

---

## [Unreleased] — PDF Export Redesign

### Added

- **`/projects/[id]/print` page**: Dedicated print/export page that renders the full structured report — executive summary, competitor overview, feature comparison, pricing comparison, user persona comparison, SWOT analysis, strategic recommendations, QA result, and references. Does not use `markdown_content`.
- **First-appearance citation numbering**: `buildCitationIndex` traverses report sections in render order and assigns `[N]` to each source ID on first use. Body citations show only `[1]`, `[2]`, etc. Raw `src_xxx` IDs appear only in the References section as `Source ID:` metadata.
- **Print CSS**: `@page { margin: 20mm 15mm; size: A4 portrait }`, `break-inside: avoid` on tables and cards, `break-before: page` on major sections (Feature Comparison, Pricing, SWOT, References).
- **Print-safe sub-components**: `PrintClaimList`, `PrintSWOTSection`, `PrintQAResult`, `CompetitorCard`, `PrintPersonaSection` — no interactive source panel, no clickable badges.
- **Print toolbar**: Fixed "Print / Save as PDF" + "← Back to Report" buttons hidden via `print:hidden`.

### Changed

- **"Export PDF" button** on `/projects/[id]/report` now opens `/projects/[id]/print` in a new tab instead of calling `window.print()` on the report page.
- **Root layout** (`app/layout.tsx`): `<header>` and `<footer>` are now `print:hidden` — no nav bar or footer appears when printing any page.

### Removed

- **`PrintView` component** and its `hidden print:block` wrapper from `report/page.tsx` — replaced entirely by the dedicated print page.

### Manual Verification

1. Open a completed project → `/projects/[id]/report` → "Export PDF" opens `/projects/[id]/print` in a new tab
2. Print page shows all sections; no nav header or footer visible
3. Citations in body render as `[1]` `[2]` — no `src_xxx` patterns in the report body
4. References section lists cited sources in number order with `Source ID:` lines; uncited sources appear under "Additional Sources"
5. Click "Print / Save as PDF" → browser print dialog → A4 layout, page breaks before major sections



### Added

- **Pages**: project creation (`/`), projects list (`/projects`), workflow execution + polling (`/projects/[id]`), report viewer (`/projects/[id]/report`), agent trace timeline (`/projects/[id]/traces`)
- **AgentDAG**: React Flow visualization with custom rework arcs; rework/pass labels are data-driven from trace output — only shown when traces confirm those paths were taken
- **FeatureComparisonTable**: parses `"Category: F1, F2 | Cat2: F3"` strings into a matrix table (competitors = columns, feature categories = rows)
- **ClaimList**: numbered `[N]` citation badges (mapped to `source_list` index) that open the source panel on click; falls back to source ID when no index available
- **MarkdownTab**: ReactMarkdown renderer with `[src_xxxxxxxx]` → `[[N]](cite:…)` pre-processing; clicking any badge opens the source panel
- **SourcePanel**: slide-in drawer; loads full source via `GET /api/sources/{id}`; shows title, URL, reliability, snippet, and collapsible full content
- **TraceTimeline + AgentRunCard**: agent execution timeline with status, latency, token usage, and expandable I/O
- **QAResultBanner**: passed/failed, score, per-issue severity + suggested action
- **SWOTView, ComparisonCards, TabsBar, AgentStatusBadge**: supporting report components
- **TanStack Query polling**: 3-second refetch on `/projects/[id]` while `status === 'running'`
- **Zustand source panel store**: shared `openSource` / `closeSource` state across all tabs and components

### Fixed

- CORS: changed from `allow_origins=["*"]` + `allow_credentials=True` (browser-rejected) to explicit origins + `allow_credentials=False`
- `writer.md` system prompt now requires `[src_xxxxxxxx]` inline citations in `markdown_content`; new workflow runs will have clickable inline citations

### Tests

- Backend: 142 tests unchanged, all passing
- Frontend automated tests deferred to v1

---

## [Unreleased] — Backend Hardening Pass

### Added

- `_build_pricing_comparison()` and `_build_pricing_markdown()` in WriterAgent — deterministic rendering from `pricing_model.plans`
- `_build_feature_comparison()` in WriterAgent — deterministic rendering from `feature_tree`
- `_typed_source_ids()` in normalization_service — routes evidence to type-appropriate sources (pricing → pricing_page, features → official_website/docs, feedback → review)
- `sources` parameter to `normalization_service.normalize()` for typed evidence routing
- User persona fallback: derive from `target_users` when LLM omits `user_personas`
- Token usage capture in AnalystAgent (cumulative across competitors) and WriterAgent
- `competitor_id` slug set on all SourceEvidence by CollectorAgent
- 15 new regression tests (pricing consistency, source competitor_id, persona fallback, evidence alignment)
- `docs/handoff_frontend_mvp.md`

### Fixed

- WriterAgent `_bind_report_fields` now always overwrites `competitor_overview` with analyst's structured knowledge — prevents QA false positives from LLM-invented prices in the report's competitor profiles
- `check_pricing_consistency` no longer fires when deterministic pricing_comparison matches pricing_model.plans
- Feature availability contradictions eliminated (Trae Builder Mode no longer shown as "none")

### Tests

- 127 → 142 tests, all passing
- Real DeepSeek workflow: status `completed`, QA passes first attempt

---

## [Unreleased] — Backend + Agents MVP

### Added

- Initial project planning.
- Defined MVP, v1, v2, and future phases.
- Added product specification.
- Added engineering specification.
- Added initial architecture documentation.
- Added Claude Code collaboration guide.
- Implemented CollectorAgent, AnalystAgent, WriterAgent, and QAAgent business agents.
- Implemented LangGraph workflow with deterministic source collection, analysis, writing, QA review, and rework routing.
- Added rule-based QA checks for required sections, evidence coverage, pricing presence, and feature trees.
- Added rework loop with upstream-first agent prioritization and bounded retry via `max_repair_loops`.
- Added prompt files for Analyst, Writer, and QA agents under `backend/app/agents/prompts/`.
- Added unit and integration tests for QA rules, routing helpers, collector, and prompt builders.

### Changed

- Clarified the distinction between Claude Code development subagents and runtime business Agents.

### Fixed

- N/A
