# Schema Design

## 1. Purpose

This document defines the structured knowledge schema used by the AI-powered competitive analysis multi-agent system.

The schema ensures that all runtime business Agents produce consistent, traceable, and machine-checkable outputs.

Runtime business Agents include:

- CollectorAgent
- AnalystAgent
- WriterAgent
- QAAgent

For Agent communication rules, see [agent_protocol.md](agent_protocol.md).  
For system architecture, see [architecture.md](architecture.md).  
For technical implementation details, see [../engineering_spec.md](../engineering_spec.md).

## 2. Design Principles

The schema follows these principles:

1. Structured first  
   Agent outputs should be valid structured objects, not free-form text.

2. Source-grounded  
   Every important claim should include evidence.

3. Validation-friendly  
   Backend services should validate outputs using Pydantic.

4. Report-ready  
   The schema should support both JSON output and human-readable report generation.

5. MVP-friendly  
   The schema should be simple enough to implement in the MVP, then extend in later versions.

## 3. Core Objects

The MVP schema contains the following objects:

- Project
- Competitor
- SourceEvidence
- Claim
- ProductProfile
- FeatureCategory
- FeatureItem
- PricingModel
- PricingPlan
- UserPersona
- UserFeedbackSummary
- SWOTAnalysis
- CompetitorKnowledge
- CompetitiveReport
- AgentMessage
- QAResult

## 4. Project

A Project represents one competitive analysis task.

```json
{
  "project_id": "string",
  "industry": "AI Coding Tools",
  "competitors": [
    {
      "name": "Cursor",
      "url": "https://cursor.com"
    }
  ],
  "goals": ["feature_comparison", "pricing_analysis", "swot"],
  "status": "created | running | qa_failed | completed | failed",
  "created_at": "string",
  "updated_at": "string"
}
````

## 5. Competitor

A Competitor represents a product or company being analyzed.

```json
{
  "competitor_id": "string",
  "name": "Cursor",
  "website": "https://cursor.com",
  "description": "AI coding assistant",
  "metadata": {}
}
```

## 6. SourceEvidence

SourceEvidence stores the original information collected from public sources.

```json
{
  "source_id": "string",
  "project_id": "string",
  "competitor_id": "string",
  "competitor_name": "Cursor",
  "source_type": "official_website | pricing_page | docs | blog | review | news | manual_input",
  "url": "https://cursor.com/pricing",
  "title": "Cursor Pricing",
  "snippet": "Short source excerpt used as evidence.",
  "content": "Full or cleaned page content.",
  "retrieved_at": "string",
  "reliability": "high | medium | low"
}
```

### Source Type Rules

* `official_website`: official product website
* `pricing_page`: official pricing page
* `docs`: documentation page
* `blog`: official or third-party blog
* `review`: public user review
* `news`: news article
* `manual_input`: manually provided content, interview, or survey result

### Reliability Rules

Default reliability:

| Source Type      | Reliability |
| ---------------- | ----------- |
| official_website | high        |
| pricing_page     | high        |
| docs             | high        |
| news             | medium      |
| blog             | medium      |
| review           | medium      |
| manual_input     | medium      |

## 7. Claim

A Claim is a single analytical statement that may appear in the final report.

```json
{
  "claim_id": "string",
  "text": "Cursor provides AI-assisted code completion and codebase-aware chat.",
  "confidence": "high | medium | low",
  "evidence": ["source_id_1", "source_id_2"],
  "is_hypothesis": false,
  "created_by": "AnalystAgent"
}
```

### Claim Rules

A claim can enter the final report only if:

1. It has at least one valid `source_id`, or
2. It is explicitly marked as `is_hypothesis: true`.

Claims without evidence and without hypothesis marking must be rejected by QAAgent.

## 8. ProductProfile

ProductProfile contains basic information about a competitor.

```json
{
  "name": "Cursor",
  "website": "https://cursor.com",
  "company": "Anysphere",
  "positioning": {
    "claim_id": "claim_001",
    "text": "Cursor is positioned as an AI code editor.",
    "confidence": "high",
    "evidence": ["source_001"],
    "is_hypothesis": false,
    "created_by": "AnalystAgent"
  },
  "target_users": [
    {
      "claim_id": "claim_002",
      "text": "The product targets software developers and engineering teams.",
      "confidence": "medium",
      "evidence": ["source_001"],
      "is_hypothesis": false,
      "created_by": "AnalystAgent"
    }
  ]
}
```

## 9. Feature Tree

The feature tree describes product capabilities in a structured way.

```json
{
  "feature_tree": [
    {
      "category": "AI Coding Assistance",
      "features": [
        {
          "name": "Code completion",
          "description": "AI-powered code completion inside the editor.",
          "availability": "available | limited | unknown",
          "evidence": ["source_001"]
        }
      ]
    }
  ]
}
```

### FeatureCategory

```json
{
  "category": "AI Coding Assistance",
  "features": []
}
```

### FeatureItem

```json
{
  "name": "Code completion",
  "description": "AI-powered code completion inside the editor.",
  "availability": "available | limited | unknown",
  "evidence": ["source_id"]
}
```

## 10. PricingModel

PricingModel describes a product's pricing structure.

```json
{
  "has_free_plan": true,
  "pricing_url": "https://cursor.com/pricing",
  "plans": [
    {
      "name": "Pro",
      "price": "$20",
      "currency": "USD",
      "billing_cycle": "monthly",
      "features": ["More completions", "Advanced models"],
      "evidence": ["source_002"]
    }
  ],
  "summary": {
    "claim_id": "claim_010",
    "text": "Cursor uses a freemium pricing model with paid monthly plans.",
    "confidence": "high",
    "evidence": ["source_002"],
    "is_hypothesis": false,
    "created_by": "AnalystAgent"
  }
}
```

### PricingPlan

```json
{
  "name": "Pro",
  "price": "$20",
  "currency": "USD",
  "billing_cycle": "monthly | annual | usage_based | unknown",
  "features": ["string"],
  "evidence": ["source_id"]
}
```

## 11. UserPersona

UserPersona describes target user groups.

```json
{
  "name": "Professional Developer",
  "description": "Developers who need AI-assisted coding in daily work.",
  "needs": [
    "Faster code completion",
    "Codebase understanding",
    "Debugging help"
  ],
  "pain_points": [
    "Context switching",
    "Repetitive coding tasks"
  ],
  "evidence": ["source_001", "source_003"]
}
```

## 12. UserFeedbackSummary

UserFeedbackSummary summarizes public user feedback.

```json
{
  "positive_points": [
    {
      "claim_id": "claim_020",
      "text": "Users appreciate fast AI-assisted code editing.",
      "confidence": "medium",
      "evidence": ["source_005"],
      "is_hypothesis": false,
      "created_by": "AnalystAgent"
    }
  ],
  "negative_points": [
    {
      "claim_id": "claim_021",
      "text": "Some users complain about pricing or usage limits.",
      "confidence": "medium",
      "evidence": ["source_006"],
      "is_hypothesis": false,
      "created_by": "AnalystAgent"
    }
  ],
  "summary": "Users generally value productivity improvements but may care about price, reliability, and model quality."
}
```

## 13. SWOTAnalysis

SWOTAnalysis contains strengths, weaknesses, opportunities, and threats.

```json
{
  "strengths": [
    {
      "claim_id": "claim_030",
      "text": "Cursor has strong positioning as an AI-native code editor.",
      "confidence": "medium",
      "evidence": ["source_001"],
      "is_hypothesis": false,
      "created_by": "AnalystAgent"
    }
  ],
  "weaknesses": [
    {
      "claim_id": "claim_031",
      "text": "Pricing may be a barrier for some individual developers.",
      "confidence": "medium",
      "evidence": ["source_002", "source_006"],
      "is_hypothesis": false,
      "created_by": "AnalystAgent"
    }
  ],
  "opportunities": [
    {
      "claim_id": "claim_032",
      "text": "Enterprise team collaboration features could become a growth opportunity.",
      "confidence": "low",
      "evidence": [],
      "is_hypothesis": true,
      "created_by": "AnalystAgent"
    }
  ],
  "threats": [
    {
      "claim_id": "claim_033",
      "text": "Competition from integrated AI coding features in existing IDEs may increase.",
      "confidence": "low",
      "evidence": [],
      "is_hypothesis": true,
      "created_by": "AnalystAgent"
    }
  ]
}
```

## 14. CompetitorKnowledge

CompetitorKnowledge is the structured knowledge object for one competitor.

```json
{
  "competitor_id": "string",
  "product_profile": {},
  "feature_tree": [],
  "pricing_model": {},
  "user_personas": [],
  "user_feedback_summary": {},
  "swot": {},
  "sources": ["source_id_1", "source_id_2"]
}
```

## 15. CompetitiveReport

CompetitiveReport is the final report object.

```json
{
  "report_id": "string",
  "project_id": "string",
  "title": "Competitive Analysis Report: AI Coding Tools",
  "executive_summary": [
    {
      "claim_id": "claim_100",
      "text": "The AI coding tools market is increasingly centered on codebase-aware assistance.",
      "confidence": "medium",
      "evidence": ["source_001", "source_010"],
      "is_hypothesis": false,
      "created_by": "WriterAgent"
    }
  ],
  "competitor_overview": [],
  "feature_comparison": {},
  "pricing_comparison": {},
  "user_persona_comparison": {},
  "swot_comparison": {},
  "strategic_recommendations": [
    {
      "claim_id": "claim_120",
      "text": "A new entrant should differentiate through enterprise workflow integration.",
      "confidence": "low",
      "evidence": [],
      "is_hypothesis": true,
      "created_by": "WriterAgent"
    }
  ],
  "source_list": [],
  "created_at": "string"
}
```

## 16. AgentMessage

AgentMessage defines structured communication between runtime business Agents.

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
```

Detailed message types are defined in [agent_protocol.md](agent_protocol.md).

## 17. QAResult

QAResult stores the result of QAAgent validation.

```json
{
  "qa_result_id": "string",
  "project_id": "string",
  "passed": false,
  "score": 72,
  "issues": [
    {
      "issue_id": "string",
      "severity": "high | medium | low",
      "issue_type": "missing_source | missing_required_field | invalid_schema | weak_evidence | incomplete_report",
      "target_agent": "CollectorAgent | AnalystAgent | WriterAgent",
      "message": "Pricing information is missing for Cursor.",
      "suggested_action": "Collect pricing page and rerun pricing extraction."
    }
  ],
  "created_at": "string"
}
```

## 18. Required MVP Validation Rules

QAAgent must check at least:

1. Required report sections exist.
2. Competitor profiles are not empty.
3. Pricing model exists when pricing analysis is requested.
4. Feature tree contains at least one category and one feature per competitor.
5. Every non-hypothesis claim has at least one source ID.
6. SWOT items either have evidence or are marked as hypothesis.
7. Source IDs referenced by claims exist in the source list.

## 19. MVP Required Report Sections

The final report must include:

* Executive summary
* Competitor overview
* Feature comparison
* Pricing comparison
* Target users
* User feedback summary
* SWOT analysis
* Strategic recommendations
* Source list

## 20. Future Extensions

Future schema extensions may include:

* Market size
* Funding history
* Product release timeline
* Technology stack
* Enterprise readiness score
* Sentiment score
* Geographic market coverage
* Customer segment matrix

These should not be added to the MVP unless required by the demo.
