---
title: AI-Powered Competitive Analysis Agents
emoji: 🤖
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
short_description: Multi-agent competitive analysis (FastAPI + LangGraph)
---

# AI-Powered-Agents · AI 驱动的竞品分析 Agent 协作系统

## 1. 项目简介

本项目是一个**多 Agent 协作的竞品分析系统**，模拟一个数字研究团队完成从信息采集、结构化分析、报告撰写到质量审核的全流程。

四个业务 Agent 通过 LangGraph DAG 协作：

- **CollectorAgent** — 采集竞品公开信息并归一化为 `SourceEvidence`
- **AnalystAgent** — 抽取结构化竞品知识（功能、定价、SWOT、机会点）
- **WriterAgent** — 生成带引用的功能对比 / 定价对比 / SWOT 矩阵与 Markdown 报告
- **QAAgent** — 校验引用完整性、证据覆盖与来源质量，不通过则按 `target_agent` 路由打回

核心特性：

- 全链路 Pydantic v2 schema 强约束 Agent 输出
- 每条结论绑定 `source_id`，前端 SourcePanel 一键回溯原始 URL
- TraceTimeline 可视化每个 AgentRun 的输入 / 输出 / 耗时 / token / QA 反馈
- QA 失败显式展示（不静默隐藏），最多 N 轮返工后输出当前最优结果
- 真实采集 / Demo 双数据模式共用同一 Agent 流程；真实采集不可用时显式回退到 Demo fixtures

### 在线 Demo

| 入口 | 地址 |
|------|------|
| 前端（Vercel） | https://ai-powered-agents.vercel.app/ |
| 后端（Hugging Face Space） | https://aisakamai-ai-powered-agents.hf.space |
| 后端 API 文档 | https://aisakamai-ai-powered-agents.hf.space/docs |
| 后端健康检查 | https://aisakamai-ai-powered-agents.hf.space/api/health |

> Hugging Face Space 免费版在约 48 小时无访问后进入睡眠，首次访问可能需要 30–60 秒唤醒。

### 架构概览

```
Next.js 前端（本地 :3000 / Vercel 生产）
  ↓
FastAPI 后端（本地 :8000 / HF Space :7860）
  ↓
LangGraph DAG：CollectorAgent → AnalystAgent → WriterAgent → QAAgent
  ↓                                                          ↑
  └────────────── QA 失败按 target_agent 路由返工 ───────────┘
  ↓
DeepSeek-V4-Flash（OpenAI 兼容 API）+ Tavily Search + SQLite
```

详细架构图：[`docs/system_architecture.svg`](docs/system_architecture.svg)

---

## 2. 依赖环境

| 工具 | 版本 |
|------|------|
| Python | ≥ 3.11 |
| Node.js | ≥ 18 |
| npm | ≥ 9 |
| Docker（可选） | ≥ 24，用于复刻线上后端镜像 |

本项目开发使用的 Python 解释器：`E:\miniforge\envs\common\python.exe`。

主要技术栈：

| 层级 | 选型 |
|------|------|
| 前端 | Next.js 16 + React 19 + TypeScript + Tailwind CSS 4 + TanStack Query + Zustand |
| 后端 | Python 3.11 + FastAPI + Pydantic v2 + SQLAlchemy + Uvicorn |
| Agent 编排 | LangGraph DAG + QA 失败循环返工 |
| 大模型 | DeepSeek-V4-Flash（默认，OpenAI 兼容 API；可切 GPT-4.1-mini / GPT-4o / DeepSeek-V4-Pro） |
| 搜索与爬取 | httpx + BeautifulSoup + Tavily Python SDK（可选） |
| 数据库 | SQLite |
| 部署 | Docker + Hugging Face Space（后端）+ Vercel（前端） |
| 测试 | pytest + pytest-asyncio |

---

## 3. 启动步骤

### 3.1 克隆并配置环境变量

```bash
git clone https://github.com/aisakataiga1215/AI-Powered-Agents.git
cd AI-Powered-Agents
cp .env.example .env
```

打开 `.env` 按需填写（详见 [环境变量](#4-环境变量)）。默认建议启用真实采集；未配置搜索 Key 或搜索不可用时，系统会回退到 Demo fixtures，保证本地开发和演示稳定。

### 3.2 启动后端

```bash
cd backend
E:\miniforge\envs\common\python.exe -m pip install -e .
E:\miniforge\envs\common\python.exe -m uvicorn app.main:app --reload --port 8000
```

- API 文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/api/health

### 3.3 启动前端

新开一个终端：

```bash
cd frontend
npm install
npm run dev
```

- 前端地址：http://localhost:3000

如需将前端连到非默认后端地址，在 `frontend/.env.local` 中设置：

```ini
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

### 3.4 Docker 一键启动（可选，复刻线上后端镜像）

```bash
docker build -t agents .
docker run -p 7860:7860 --env-file .env agents
```

容器内服务监听 `:7860`，对应 Hugging Face Space 部署配置。

### 3.5 运行测试

```bash
cd backend
E:\miniforge\envs\common\python.exe -m pytest
```

含覆盖率：

```bash
E:\miniforge\envs\common\python.exe -m pytest --cov=app --cov-report=term-missing
```

---

## 4. 环境变量

在项目根目录的 `.env` 中配置（后端会自动读取）：

| 变量 | 必填 | 说明 |
|------|------|------|
| `OPENAI_API_KEY` | 是* | LLM 调用密钥（*仅查看 Demo fixtures 或部分离线流程时可留空） |
| `OPENAI_BASE_URL` | 否 | OpenAI 兼容 API 地址，DeepSeek 填 `https://api.deepseek.com` |
| `DEFAULT_MODEL` | 否 | 默认 `deepseek-v4-flash`，可选 `gpt-4.1-mini` / `gpt-4o` / `deepseek-v4-pro` |
| `LLM_DISABLE_THINKING` | 否 | 默认开启思考的模型（如 deepseek-v4-pro）设为 `true` 关闭 |
| `DATABASE_URL` | 否 | 默认 `sqlite:///./dev.db` |
| `ENABLE_DEMO_FIXTURES` | 否 | `true` = 允许使用本地 fixtures 兜底，保证演示稳定 |
| `ENABLE_LIVE_SEARCH` | 否 | `true` = 启用真实搜索；设为 `false` 可强制关闭搜索 |
| `TAVILY_API_KEY` | 否 | `ENABLE_LIVE_SEARCH=true` 时必填 |
| `LANGSMITH_TRACING` | 否 | `true` = 上传 trace 到 LangSmith |
| `LANGSMITH_API_KEY` | 否 | LangSmith Key |
| `FRONTEND_ORIGINS` | 否 | 逗号分隔 CORS 白名单，Demo 默认 `*` |

### 数据模式

| 模式 | 配置 | 行为 |
|------|------|------|
| 真实采集 | `ENABLE_LIVE_SEARCH=true` + `TAVILY_API_KEY` | 使用 Tavily 搜索补充候选 URL，并抓取公开网页作为来源 |
| 真实采集 + Demo 兜底 | `ENABLE_LIVE_SEARCH=true`, `ENABLE_DEMO_FIXTURES=true` | 搜索或网页抓取不足时补充 fixtures，报告中会体现来源强弱 |
| Demo | `ENABLE_LIVE_SEARCH=false`, `ENABLE_DEMO_FIXTURES=true` | 读取 `scripts/demo_fixtures/*.json`，适合离线开发和稳定演示 |

---

## 5. 目录结构

```
AI-Powered-Agents/
├── backend/
│   ├── app/
│   │   ├── agents/         # CollectorAgent / AnalystAgent / WriterAgent / QAAgent 与 prompts
│   │   ├── api/            # FastAPI 路由（projects / reports / sources / traces / search / knowledge / health）
│   │   ├── core/           # 配置、日志、依赖注入
│   │   ├── db/             # SQLAlchemy 模型与 session
│   │   ├── graph/          # LangGraph DAG 节点、状态、路由
│   │   ├── schemas/        # Pydantic v2 schema（Competitor / Feature / Pricing / SWOT / QA / Trace ...）
│   │   ├── services/       # crawler / search_provider / search_service / source_discovery / qa / trace
│   │   ├── utils/          # 工具函数
│   │   └── main.py         # FastAPI 入口
│   └── tests/              # pytest 测试（schema / 路由 / QA / Agent 集成）
├── frontend/
│   ├── app/                # Next.js App Router 页面（首页 / 项目列表 / 详情 / 报告 / Trace / 打印）
│   ├── components/
│   │   ├── agent-flow/     # AgentStatusBadge 等
│   │   ├── competitor/     # CompetitorDiscoveryPanel
│   │   ├── qa/             # QAResultBanner / QaStatusBanner
│   │   ├── report-viewer/  # 功能对比 / 定价 / SWOT / Claim / InsufficientData
│   │   ├── search/         # CandidateSourcePanel
│   │   ├── source-viewer/  # SourcePanel
│   │   └── trace-panel/    # AgentRunCard / TraceTimeline
│   └── lib/                # types / api / store / 工具
├── docs/
│   ├── architecture.md
│   ├── agent_protocol.md
│   ├── schema_design.md
│   ├── competition_submission.md
│   ├── system_architecture.svg
│   ├── changelog.md
│   └── project_status.md
├── scripts/
│   ├── demo_fixtures/      # Demo 模式静态 JSON 数据
│   └── seed_demo_data.py
├── Dockerfile              # HF Space 镜像（:7860）
├── .env.example
├── product_spec.md
├── engineering_spec.md
└── README.md
```

---

## 6. 部署

| 组件 | 平台 | 备注 |
|------|------|------|
| 后端 | Hugging Face Space（Docker SDK） | 根 `Dockerfile`，端口 `7860`，SQLite 在免费版上为临时存储 |
| 前端 | Vercel | 导入仓库时把 **Root Directory** 设为 `frontend` |

### 后端 → Hugging Face Space

1. 新建 Space，**SDK = Docker**、**Template = Blank**。
2. 将 Space 添加为 git remote 并推送：

   ```bash
   git remote add space https://huggingface.co/spaces/<owner>/<name>
   git -c http.version=HTTP/1.1 push -f space main
   ```

3. 在 Space → **Settings → Variables and secrets** 配置：
   `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`DEFAULT_MODEL`、`TAVILY_API_KEY`、
   `LANGSMITH_API_KEY`、`LANGSMITH_TRACING`、`ENABLE_LIVE_SEARCH`、`ENABLE_DEMO_FIXTURES`、`FRONTEND_ORIGINS`。

### 前端 → Vercel

1. 在 https://vercel.com/new 导入 GitHub 仓库。
2. **Root Directory** 设为 `frontend`（Next.js 自动识别）。
3. 添加环境变量 `NEXT_PUBLIC_API_BASE_URL`，指向 HF Space 后端，例如
   `https://aisakamai-ai-powered-agents.hf.space`。

---

## 7. 相关文档

- [架构设计](docs/architecture.md)
- [Agent 通信协议](docs/agent_protocol.md)
- [Schema 设计](docs/schema_design.md)
- [Changelog](docs/changelog.md)
- [项目状态](docs/project_status.md)
- [竞赛提交材料](docs/competition_submission.md)
- [产品规格](product_spec.md)
- [工程规格](engineering_spec.md)
