# Agent Protocol

## 1. Purpose

This document defines the structured communication protocol between runtime business Agents in the AI-powered competitive analysis system.

Runtime business Agents include:

- CollectorAgent
- AnalystAgent
- WriterAgent
- QAAgent

These are application-level Agents. They are not the same as Claude Code development subagents.

For schema definitions, see [schema_design.md](schema_design.md).  
For architecture, see [architecture.md](architecture.md).

## 2. Protocol Principles

1. Agents communicate through LangGraph `WorkflowState` — a typed dictionary with Pydantic-validated fields.
2. AnalystAgent and WriterAgent use **function calling** (`with_structured_output(method="function_calling")`) as the primary structured output path, with JSON Output as fallback.
3. Agent input/output is persisted per `AgentRun` record for full trace observability.
4. Free-form natural language is never the only communication format; all outputs are validated against Pydantic v2 schemas.
5. Each important output is traceable to source evidence via `source_id`.
6. Each workflow edge also emits a structured `AgentMessage` trace event so reviewers can inspect the handoff payload independently from the natural-language report.

## 3. Communication Mechanism

**Primary: LangGraph WorkflowState**

The actual runtime communication uses LangGraph's typed state dictionary.
Each node reads from and writes to specific fields:

| Field | Writer | Reader | Type |
|-------|--------|--------|------|
| `sources` | CollectorAgent | AnalystAgent | `list[SourceEvidence]` |
| `competitor_knowledge` | AnalystAgent | WriterAgent, QAAgent | `list[CompetitorKnowledge]` |
| `report` | WriterAgent | QAAgent | `CompetitiveReport` |
| `qa_result` | QAAgent | WorkflowRouter | `QAResult` |
| `rework_hints` | WorkflowRouter | CollectorAgent, AnalystAgent, WriterAgent | `list[str]` |
| `rework_target` | WorkflowRouter | route_rework() | `str` |

**Observability: AgentRun traces**

Every agent invocation is persisted as an `AgentRun` row recording
input, output, prompt preview, parse status, token usage, cost, and errors.

**Runtime protocol audit: AgentMessage schema**

The `AgentMessage` schema (`backend/app/schemas/agent_message.py`) documents
the logical message types for each workflow edge. Runtime payloads still flow
through LangGraph state for execution, while each handoff is persisted through
`trace_service.record_agent_message()` as an `AgentRun` with
`agent_name="AgentMessage"`. This makes the protocol visible in the same Trace
timeline as prompts, model outputs, QA results, and rework routing.

```json
{
  "message_id": "string",
  "project_id": "string",
  "from_agent": "CollectorAgent",
  "to_agent": "AnalystAgent",
  "message_type": "source_collection_result",
  "payload": {},
  "created_at": "string"
}
````

## 4. Agent Names

Allowed runtime Agent names:

```txt
CollectorAgent
AnalystAgent
WriterAgent
QAAgent
System
```

## 5. Message Types

Allowed MVP message types:

```txt
source_collection_request
source_collection_result
analysis_request
analysis_result
report_write_request
report_draft
qa_review_request
qa_review_result
rework_request
final_report
error
```

## 6. Message Type Definitions

### 6.1 source_collection_request

Sent to CollectorAgent.

```json
{
  "message_type": "source_collection_request",
  "payload": {
    "competitors": [
      {
        "name": "Cursor",
        "url": "https://cursor.com"
      }
    ],
    "goals": ["pricing_analysis", "feature_comparison"]
  }
}
```

### 6.2 source_collection_result

Returned by CollectorAgent.

```json
{
  "message_type": "source_collection_result",
  "payload": {
    "sources": [
      {
        "source_id": "source_001",
        "competitor_name": "Cursor",
        "source_type": "pricing_page",
        "url": "https://cursor.com/pricing",
        "title": "Cursor Pricing",
        "snippet": "Pricing page excerpt",
        "content": "Cleaned page content",
        "retrieved_at": "string",
        "reliability": "high"
      }
    ]
  }
}
```

### 6.3 analysis_request

Sent to AnalystAgent.

```json
{
  "message_type": "analysis_request",
  "payload": {
    "sources": ["source_001", "source_002"],
    "goals": ["feature_comparison", "pricing_analysis", "swot"]
  }
}
```

### 6.4 analysis_result

Returned by AnalystAgent.

```json
{
  "message_type": "analysis_result",
  "payload": {
    "competitor_knowledge": [
      {
        "competitor_id": "string",
        "product_profile": {},
        "feature_tree": [],
        "pricing_model": {},
        "user_personas": [],
        "user_feedback_summary": {},
        "swot": {},
        "sources": ["source_001"]
      }
    ]
  }
}
```

### 6.5 report_write_request

Sent to WriterAgent.

```json
{
  "message_type": "report_write_request",
  "payload": {
    "competitor_knowledge": [],
    "report_sections": [
      "executive_summary",
      "competitor_overview",
      "feature_comparison",
      "pricing_comparison",
      "swot",
      "strategic_recommendations"
    ]
  }
}
```

### 6.6 report_draft

Returned by WriterAgent.

```json
{
  "message_type": "report_draft",
  "payload": {
    "report": {
      "report_id": "string",
      "project_id": "string",
      "title": "Competitive Analysis Report",
      "executive_summary": [],
      "competitor_overview": [],
      "feature_comparison": {},
      "pricing_comparison": {},
      "swot_comparison": {},
      "strategic_recommendations": [],
      "source_list": []
    }
  }
}
```

### 6.7 qa_review_request

Sent to QAAgent.

```json
{
  "message_type": "qa_review_request",
  "payload": {
    "report": {},
    "competitor_knowledge": [],
    "sources": []
  }
}
```

### 6.8 qa_review_result

Returned by QAAgent.

```json
{
  "message_type": "qa_review_result",
  "payload": {
    "passed": false,
    "score": 72,
    "issues": [
      {
        "severity": "high",
        "issue_type": "missing_source",
        "target_agent": "CollectorAgent",
        "message": "Pricing source is missing for Cursor.",
        "suggested_action": "Collect official pricing page."
      }
    ]
  }
}
```

### 6.9 rework_request

Sent when QAAgent rejects output.

```json
{
  "message_type": "rework_request",
  "payload": {
    "target_agent": "CollectorAgent",
    "reason": "Missing pricing source",
    "required_output": "Add pricing source evidence for Cursor",
    "previous_issues": []
  }
}
```

### 6.10 final_report

Returned when QA passes.

```json
{
  "message_type": "final_report",
  "payload": {
    "report": {},
    "qa_result": {
      "passed": true,
      "score": 90,
      "issues": []
    }
  }
}
```

### 6.11 error

Used when an Agent or workflow node fails.

```json
{
  "message_type": "error",
  "payload": {
    "agent": "CollectorAgent",
    "error_type": "crawl_failed",
    "message": "Failed to retrieve source URL",
    "recoverable": true
  }
}
```

## 7. Rework Routing Rules

QAAgent should route issues according to the table below.

| Issue Type                   | Target Agent   | Reason                                     |
| ---------------------------- | -------------- | ------------------------------------------ |
| `missing_source`             | CollectorAgent | More evidence must be collected            |
| `missing_pricing`            | CollectorAgent | Pricing page or pricing data is missing    |
| `invalid_schema`             | AnalystAgent   | Structured knowledge does not match schema |
| `weak_evidence`              | AnalystAgent   | Claim exists but evidence is insufficient  |
| `missing_report_section`     | WriterAgent    | Report section needs to be generated       |
| `missing_citation_in_report` | WriterAgent    | Report needs citation references           |

## 8. QA Pass Criteria

The QAAgent runs deterministic checks across source coverage, report structure,
citation integrity, and content quality. Each issue is classified as `high`,
`medium`, or `low` severity.

**Pass condition** (implemented in `backend/app/agents/qa_agent.py`):

```
score >= 80 AND no high-severity issues
```

**Scoring**: starts at 100, subtracts 15 per `high` issue, 5 per `medium` issue.

**Check categories**:
1. Source coverage: pricing page, features/docs page per competitor
2. Report structure: executive summary, feature comparison, pricing comparison
3. Citation integrity: reference to unknown source_id, claim without evidence
4. Content quality: weak source content, brand mismatch, price consistency

## 9. Rework Limits

```txt
max_repair_loops = 1
```

Configured in `backend/app/core/config.py`. After reaching the limit,
the workflow marks the project `qa_failed` and persists the partial report
with QA issues — no silent hiding, no infinite loops.

## 10. Trace Requirements

Every Agent message should be traceable.

Store:

* Message ID
* Project ID
* Sender
* Receiver
* Message type
* Payload
* Created time
* Related Agent run ID if available
