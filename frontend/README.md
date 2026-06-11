# Frontend · Competitive Analysis Agent Console

Next.js frontend for the AI-Powered-Agents competitive analysis system.

## What It Provides

- Project creation with competitor discovery, manual competitor entry, custom dimensions, and research notes.
- Live project execution view with backend-driven LangGraph DAG rendering.
- Report viewer with structured tabs for summary, pricing, features, SWOT, recommendations, Markdown, and QA results.
- Citation SourcePanel for one-click source inspection and original URL navigation.
- Trace timeline with prompts, inputs, outputs, token usage, QA decisions, rework hints, and structured AgentMessage events.
- Metrics page for token and cost aggregation.
- Human correction panel on the report page; saved corrections create a new report revision and a `HumanReviewer` trace event.

## Local Development

```bash
npm install
npm run dev
```

The frontend expects the backend at `http://localhost:8000` unless overridden:

```ini
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

## Verification

```bash
npm run build
npm run lint
```
