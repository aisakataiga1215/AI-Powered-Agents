# Engineering Spec: AI 驱动的竞品分析 Agent 协作系统

## 1. 技术目标

本项目需要实现一个端到端的多 Agent 竞品分析系统，支持：

- 公开数据采集
- 多 Agent DAG 编排
- 结构化知识抽取
- 质检反馈闭环
- 报告生成
- 信息溯源
- Agent 执行过程可观测
- 前端可视化演示

## 2. 开发语言

### 后端

- Python 3.11+

### 前端

- TypeScript
- React
- Next.js

## 3. 前端框架

推荐使用：

- Next.js
- React
- Tailwind CSS
- shadcn/ui
- React Flow：展示 Agent DAG
- Zustand：管理前端状态
- TanStack Query：请求后端接口

## 4. 后端框架

推荐使用：

- FastAPI
- Pydantic
- SQLAlchemy
- LangGraph
- LangChain integrations
- Uvicorn

## 5. 数据库

### 主数据库

推荐：

- PostgreSQL

MVP 可选：

- SQLite

### 向量数据库

MVP 可选：

- Chroma

v1 推荐：

- pgvector

## 6. Agent 编排

使用 LangGraph 构建 DAG 工作流。

核心节点：

```txt
start
  ↓
plan_task
  ↓
collect_sources
  ↓
extract_schema
  ↓
analyze_competitors
  ↓
write_report
  ↓
qa_review
  ↓
if pass: final_report
if fail: route_to_rework
  ↓
collect_sources / analyze_competitors / write_report
```

## 7. 系统设计概述

系统由以下模块组成：

```txt
Frontend UI
  ↓
FastAPI Backend
  ↓
LangGraph Agent Workflow
  ↓
Crawler / Search / Parser Services
  ↓
LLM Service
  ↓
Database / Vector Store / Trace Store
```

### 7.1 前端

前端负责：

* 创建竞品分析任务
* 展示任务状态
* 展示 Agent DAG
* 展示 Agent Trace
* 展示最终报告
* 展示引用来源
* 支持人工修正

### 7.2 后端

后端负责：

* 提供 REST API
* 管理分析任务
* 调用 Agent 工作流
* 保存结构化结果
* 保存日志和 trace
* 提供报告查询和导出

### 7.3 Agent 工作流

Agent 工作流负责：

* 根据任务生成执行计划
* 采集和解析公开信息
* 抽取结构化竞品知识
* 生成竞品分析报告
* 执行质检
* 根据质检结果决定是否返工

## 8. 核心 Agent 设计

### 8.1 CollectorAgent

职责：

* 接收产品名称和 URL
* 抓取公开网页内容
* 提取网页正文
* 识别官网、定价页、文档页、评论页
* 输出带 source_id 的原始资料

输入：

```json
{
  "task_id": "string",
  "competitors": [
    {
      "name": "string",
      "url": "string"
    }
  ],
  "research_questions": ["string"]
}
```

输出：

```json
{
  "sources": [
    {
      "source_id": "string",
      "competitor_name": "string",
      "url": "string",
      "title": "string",
      "content": "string",
      "retrieved_at": "string"
    }
  ]
}
```

### 8.2 AnalystAgent

职责：

* 基于 sources 抽取结构化竞品知识
* 构建功能树
* 总结定价模型
* 提炼用户画像
* 生成 SWOT

输出必须符合竞品知识 Schema。

### 8.3 WriterAgent

职责：

* 根据结构化分析结果生成报告
* 每条关键结论绑定引用
* 生成 Markdown 和 JSON 两种格式

### 8.4 QAAgent

职责：

* 检查 Schema 字段完整度
* 检查引用覆盖率
* 检查结论是否有来源支撑
* 检查报告结构是否完整
* 生成 QA 结果
* 决定通过或打回

QA 输出：

```json
{
  "passed": false,
  "score": 72,
  "issues": [
    {
      "severity": "high",
      "target_agent": "CollectorAgent",
      "issue_type": "missing_source",
      "message": "缺少产品 A 的定价页来源",
      "suggested_action": "重新采集产品 A 的 pricing 信息"
    }
  ]
}
```

## 9. 竞品知识 Schema

核心对象：

```json
{
  "product_profile": {
    "name": "string",
    "website": "string",
    "company": "string",
    "positioning": "string",
    "target_users": ["string"],
    "sources": ["source_id"]
  },
  "feature_tree": [
    {
      "category": "string",
      "features": [
        {
          "name": "string",
          "description": "string",
          "availability": "string",
          "sources": ["source_id"]
        }
      ]
    }
  ],
  "pricing_model": {
    "has_free_plan": "boolean",
    "plans": [
      {
        "name": "string",
        "price": "string",
        "billing_cycle": "string",
        "features": ["string"],
        "sources": ["source_id"]
      }
    ]
  },
  "user_personas": [
    {
      "name": "string",
      "description": "string",
      "needs": ["string"],
      "pain_points": ["string"],
      "sources": ["source_id"]
    }
  ],
  "swot": {
    "strengths": [
      {
        "claim": "string",
        "evidence": ["source_id"]
      }
    ],
    "weaknesses": [
      {
        "claim": "string",
        "evidence": ["source_id"]
      }
    ],
    "opportunities": [
      {
        "claim": "string",
        "evidence": ["source_id"]
      }
    ],
    "threats": [
      {
        "claim": "string",
        "evidence": ["source_id"]
      }
    ]
  }
}
```

详细 Schema 写入 [docs/schema_design.md](docs/schema_design.md)。

## 10. Project Structure

The detailed project structure is defined in [docs/architecture.md](docs/architecture.md).

The top-level structure is:

```txt
AI-Powered-Agents/
├── .claude/
├── backend/
├── frontend/
├── docs/
├── scripts/
├── product_spec.md
├── engineering_spec.md
├── CLAUDE.md
└── README.md
```

Do not duplicate the complete tree here. Keep the full structure in [docs/architecture.md](docs/architecture.md) to avoid documentation drift.

## 11. API 结构

### 11.1 创建分析任务

```http
POST /api/projects
```

请求：

```json
{
  "industry": "AI Coding Tools",
  "competitors": [
    {
      "name": "Cursor",
      "url": "https://cursor.com"
    },
    {
      "name": "Trae",
      "url": "https://www.trae.ai"
    }
  ],
  "goals": ["功能对比", "定价分析", "用户画像", "SWOT"]
}
```

响应：

```json
{
  "project_id": "string",
  "status": "created"
}
```

### 11.2 启动分析任务

```http
POST /api/projects/{project_id}/run
```

### 11.3 获取任务状态

```http
GET /api/projects/{project_id}
```

### 11.4 获取 Agent Trace

```http
GET /api/projects/{project_id}/traces
```

### 11.5 获取最终报告

```http
GET /api/projects/{project_id}/report
```

### 11.6 获取引用来源

```http
GET /api/sources/{source_id}
```

### 11.7 人工修正结构化结果

```http
PATCH /api/projects/{project_id}/knowledge
```

### 11.8 导出报告

```http
GET /api/projects/{project_id}/export?format=pdf
```

## 12. 数据库表设计

### projects

保存分析任务。

字段：

* id
* industry
* goals
* status
* created_at
* updated_at

### competitors

保存竞品信息。

字段：

* id
* project_id
* name
* url
* description

### sources

保存原始来源。

字段：

* id
* project_id
* competitor_id
* url
* title
* content
* retrieved_at

### agent_runs

保存 Agent 执行记录。

字段：

* id
* project_id
* agent_name
* input
* output
* status
* token_usage
* latency_ms
* created_at

### qa_results

保存质检结果。

字段：

* id
* project_id
* passed
* score
* issues
* created_at

### reports

保存最终报告。

字段：

* id
* project_id
* markdown_content
* json_content
* created_at

## 13. 错误处理策略

* 网页抓取失败：记录失败原因，允许重试。
* LLM 输出格式错误：使用 Pydantic 校验并要求模型重新输出。
* 缺少引用：QAAgent 打回上游 Agent。
* 超时：任务状态标记为 partial_failed，并展示已完成部分。
* Token 超限：对长文档进行分片摘要。

## 14. 幻觉抑制策略

1. 强制结构化输出。
2. 每条关键结论必须绑定 source_id。
3. QAAgent 检查 claim-evidence 对应关系。
4. 无引用结论不得进入最终报告。
5. 对推测性结论标记为 hypothesis。
6. 使用原文片段支持分析结论。

## 15. 可观测性策略

系统记录：

* Agent 名称
* Agent 输入
* Agent 输出
* Prompt 模板版本
* Token 消耗
* 执行耗时
* 错误信息
* Retry 次数
* QA 打回原因

前端展示：

* DAG 执行图
* Agent 时间线
* 每一步输入输出
* 最终报告引用来源

## 16. 部署方案

MVP 推荐本地演示：

```txt
Frontend: localhost:3000
Backend: localhost:8000
Database: SQLite / PostgreSQL local
```

v1 可使用：

```txt
Frontend: Vercel
Backend: Railway / Render / ECS
Database: Supabase PostgreSQL
```

## 17. Claude Code Development Workflow

The project uses Claude Code subagents for development workflow separation.

These subagents are not runtime business agents. They help develop the codebase.

Runtime business agents are described in:

- [docs/agent_protocol.md](docs/agent_protocol.md)
- [docs/schema_design.md](docs/schema_design.md)

Claude Code development subagents are stored in:

```txt
.claude/agents/
```

Recommended subagents:

| Subagent | Responsibility                                             |
| -------------- | -------------------------- |
| `architect`    | Architecture review, milestone planning, boundary checking |
| `backend-engineer`  | FastAPI, database, Pydantic schemas, backend services      |
| `frontend-engineer`   | Next.js UI, report viewer, trace panel, source panel       |
| `agent-workflow-engineer`| LangGraph workflow, runtime Agent logic, feedback loop     |
| `qa-observability-engineer`| Tests, trace logging, reliability, demo fallback           |
| `docs-maintainer`   | Documentation consistency, changelog, project status       |

Subagent definitions are documented in `.claude/agents/*.md`.

Do not create additional subagents unless the project has repeated tasks that are large enough to justify a separate context.
