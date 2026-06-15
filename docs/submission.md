# 竞赛提交材料

## 填写字段说明

| 字段组 | 字段名称 | 填写说明 |
| ---- | --------------- | ----------------------------------------------------- |
| 基础信息 | 项目名称/课题 | 保持与最终提交页一致；名称应可被评委快速识别 |
| 基础信息 | 团队名称与成员名单 | 列出成员姓名、学校、专业、角色 |
| 基础信息 | 分工说明（如小队完成） | 写清每位成员负责的模块，如前端、后端、模型、数据、部署、产品设计等 |
| 功能说明 | 核心功能清单 | 建议 3-6 条，按用户路径或系统能力拆分 |
| 功能说明 | 端到端使用流程 | 用 5-8 句写清用户从进入系统到拿到结果的完整流程 |
| 交付材料 | 在线 Demo 链接 | 提供可访问链接；若需登录，请提供体验账号或录屏替代（如无在线 Demo，可通过录屏或者演示视频替代） |
| 交付材料 | 演示视频链接 | 建议 3-8 分钟，展示核心场景、关键功能、亮点与结果；优先公开视频链接 |
| 交付材料 | 源代码仓库链接 | GitHub / GitLab 均可；建议提供主仓库链接、分支说明与最后提交记录 |
| 交付材料 | README / 运行说明 | 至少包含项目简介、依赖环境、启动步骤、目录结构、配置说明 |
| 技术说明 | 系统架构图 | 建议展示前端、后端、模型层、数据层、外部服务与调用关系 |
| 技术说明 | 核心技术栈 | 分别说明前端、后端、数据库、中间件、部署环境、云资源等 |
| 技术说明 | 大模型 / AI 能力使用说明 | 写清使用了哪些模型、API、Agent / RAG / 向量库 / Prompt 方案，以及在系统中的位置 |
| 技术说明 | 关键工程难点与解决方案 | 至少写 2-3 个，如并发、延迟、数据清洗、上下文管理、前后端联调、部署问题等 |
| 技术说明 | 部署与访问说明 | 说明项目部署在哪里、如何访问、评委如何快速体验 |
| 结果说明 | 项目完成度 | 标注当前是 MVP、可用 Demo、已部署可体验版本，还是接近生产级版本 |
| 结果说明 | 项目亮点 / 创新点 | 建议 3 条以内，突出与同类方案相比的差异化 |

## 基础信息

### 项目名称 / 课题

AI-Powered-Agents：AI 驱动的竞品分析 Agent 协作系统

### 团队名称与成员名单

| 姓名 | 学校 | 专业 | 角色 |
| --- | --- | --- | --- |
| 姜振宇 | 上海交通大学 | 信息工程 | 独立开发者 / 项目负责人 |

### 分工说明

本项目为单人独立完成，覆盖产品设计、前端、后端、Agent 工作流、数据采集、测试、部署和文档。

- 产品设计：定义竞品分析业务流程、分析目的、分析目标、报告结构、QA 反馈和人工修正流程。
- 前端开发：实现项目创建、竞品发现、来源选择、报告查看、Trace、Metrics、打印/PDF 等页面。
- 后端开发：实现项目、报告、来源、Trace、搜索、工作流图、指标等 API。
- Agent 工作流：实现 CollectorAgent、AnalystAgent、WriterAgent、QAAgent，并用 LangGraph 编排。
- 数据与质量：实现 Live crawl、Tavily 搜索、Demo fallback、来源覆盖评分、句级引用、PII 脱敏和 QA 检查。
- 部署与文档：完成 Hugging Face Space 后端、Vercel 前端、Docker 镜像、README 和提交材料。

## 功能说明

### 核心功能清单

- 多 Agent 竞品分析：CollectorAgent 采集公开网页和研究输入，AnalystAgent 抽取结构化知识，WriterAgent 生成报告，QAAgent 负责质量审核和返工。
- 目的驱动报告：根据“做类似产品 / 选择产品 / 了解行业 / 分析增长运营商业化”切换默认框架、报告页签、评分模型和打印/PDF 内容。
- 可追溯报告：每条关键结论绑定 `source_id`，支持句级引用、Sources tab、SourcePanel 原文回溯和公开链接展示。
- QA 闭环与可观测：QA 未通过时按目标 Agent 返工；Trace 展示 AgentRun、AgentMessage、输入输出、token、成本、QA 问题和返工前后对比。
- 评分与建议：选择产品场景输出加权评分矩阵、推荐排序、适合/不适合人群；做类似产品场景输出 OpportunityScore、市场空白和 MVP 建议。
- 人工修正与版本记录：报告页支持用表单化方式修改摘要、画像、功能、定价、SWOT、建议等字段，并记录 HumanReviewer Trace。

### 端到端使用流程

1. 用户进入前端，填写分析主题、行业类型、分析目的、分析目标、分析框架、目标产品和竞品。
2. 用户可以通过竞品发现补充候选竞品，也可以为每个竞品搜索并选择额外公开来源 URL。
3. 用户提交项目后，后端启动 LangGraph 工作流，CollectorAgent 抓取网页和人工研究输入并生成 SourceEvidence。
4. AnalystAgent 按竞品抽取产品概况、功能、定价、用户画像、用户评价、SWOT/3C/AARRR 和自定义维度。
5. WriterAgent 基于完整结构化知识生成带引用的报告、评分矩阵、建议页签和 Markdown 内容。
6. QAAgent 检查引用、来源覆盖、弱来源、价格一致性、目的匹配和结构完整性；不通过则自动打回对应 Agent。
7. 用户在报告页查看摘要、功能对比、定价、评分、建议、Sources 和 QA 结果，可打开 SourcePanel 核验原始链接。
8. 用户可以在 Trace 页面查看完整执行链路，在 Metrics 页面查看 token 和成本，并通过打印页导出 PDF。

## 交付材料

### 在线 Demo 链接

| 入口 | 地址 |
| --- | --- |
| 前端（Vercel） | https://ai-powered-agents.vercel.app/ |
| 后端（Hugging Face Space） | https://aisakamai-ai-powered-agents.hf.space |
| 后端 API 文档 | https://aisakamai-ai-powered-agents.hf.space/docs |
| 后端健康检查 | https://aisakamai-ai-powered-agents.hf.space/api/health |

Hugging Face Space 免费版可能休眠，首次访问如遇冷启动，请等待 30-60 秒后刷新。

### 演示视频链接

待填写。建议录制 3-8 分钟视频，覆盖项目创建、来源选择、Agent 工作流、报告、Sources、Trace、QA、人工修正和 PDF 导出。

### 源代码仓库链接

- 主仓库：https://github.com/aisakataiga1215/AI-Powered-Agents
- 提交分支：`main`
- 后端部署仓库：https://huggingface.co/spaces/AisakaMai/AI-Powered-Agents

### README / 运行说明

项目根目录 `README.md` 已包含项目简介、依赖环境、启动步骤、环境变量、数据模式、目录结构和部署说明。

本地运行摘要：

```bash
cp .env.example .env

cd backend
python -m pip install -e .
python -m uvicorn app.main:app --reload --port 8000

cd frontend
npm install
npm run dev
```

默认访问地址：

- 前端：`http://localhost:3000`
- 后端 API 文档：`http://localhost:8000/docs`

## 技术说明

### 系统架构图

```text
Next.js 前端
  -> FastAPI 后端
  -> LangGraph 工作流：CollectorAgent -> AnalystAgent -> WriterAgent -> QAAgent
  -> QA 未通过时按 target_agent 路由返工
  -> SQLite / Tavily Search / OpenAI-compatible LLM
```

前端工作流图由后端 `/api/graph` 输出节点和边，确保 UI 展示与真实 LangGraph 编排一致。

### 核心技术栈

| 层级 | 技术选型 |
| --- | --- |
| 前端 | Next.js 16、React 19、TypeScript、Tailwind CSS 4、TanStack Query、Zustand |
| 后端 | Python 3.11、FastAPI、Pydantic v2、SQLAlchemy、Uvicorn |
| Agent 编排 | LangGraph DAG，支持 QA 条件分支和返工循环 |
| 大模型 | Volcengine Doubao OpenAI-compatible endpoint，可切换其他 OpenAI 兼容模型 |
| 搜索与爬取 | Tavily Python SDK、httpx、BeautifulSoup |
| 数据库 | SQLite |
| 部署 | Docker、Hugging Face Space、Vercel |
| 可观测 | AgentRun、QAResult、TraceService、Metrics API |
| 测试 | pytest、pytest-asyncio、ESLint、Next build |

### 大模型 / AI 能力使用说明

- AnalystAgent 和 WriterAgent 优先使用 function/tool calling 生成结构化 Pydantic 对象，失败时回退到 JSON output + Pydantic 校验。
- CollectorAgent 可使用 LLM 对采集来源做相关性预检，剔除明显无关内容后再传给 AnalystAgent。
- QAAgent 使用确定性规则控制 pass/fail，同时可调用 LLM 生成低严重度 advisory 复核意见。
- Prompt 按 Agent 拆分维护，运行时注入分析目的、分析框架、分析目标、自定义维度、竞品角色和来源索引。
- 系统没有使用向量库；当前 RAG 形态是基于实时网页抓取和 SourceEvidence 的显式引用式上下文注入。

### 关键工程难点与解决方案

| 难点 | 解决方案 |
| --- | --- |
| Agent 输出不稳定 | 使用 Pydantic schema、function calling、JSON fallback 和后端 normalize/validate 保证结构完整 |
| Live 网页质量不可控 | 通过 Tavily 搜索、官网路径探测、坏页过滤、来源类型分类、覆盖评分和 Demo fallback 降低失败率 |
| 报告可信度不足 | 所有关键 claim 绑定 `source_id`，QA 检查缺失/未知引用，前端 Sources tab 和 SourcePanel 支持回溯 |
| QA 返工不透明 | Trace 记录 QA 问题、返工目标、返工前后评分、问题数、引用覆盖率和 claim 数 |
| 上下文管理复杂 | Analyst 按竞品分组抽取，Writer 接收结构化知识对象，避免单纯自然语言长上下文拼接 |
| 前后端报告结构同步 | 后端 schema 作为事实来源，前端类型与组件按报告区块拆分渲染，打印页复用同一结构化数据 |

### 部署与访问说明

项目已完成线上部署：

- 前端部署在 Vercel，可直接访问 https://ai-powered-agents.vercel.app/
- 后端部署在 Hugging Face Space，API 文档见 https://aisakamai-ai-powered-agents.hf.space/docs
- 后端使用 Docker 镜像构建，容器监听 `7860` 端口。
- 评委无需登录即可体验；如果 Hugging Face Space 冷启动，请等待后刷新。

## 结果说明

### 项目完成度

当前状态：已部署可体验版本。

系统已完成端到端流程，包括项目创建、Live/Demo 数据采集、竞品发现、来源选择、多 Agent 工作流、结构化报告、Sources、QA、Trace、Metrics、人工修正和打印/PDF。当前版本更接近可演示产品原型，已具备完整闭环和可观测能力，但仍保留单用户、SQLite、本地任务队列等轻量化实现。

### 项目亮点 / 创新点

1. 目的驱动的报告生成：同一套 Agent 工作流可根据分析目的切换框架、页签、评分和 QA 检查。
2. 全链路可追溯：句级引用、Sources tab、SourcePanel、TraceTimeline 和 AgentMessage 共同支撑报告可信度。
3. 真实 QA 闭环：QAAgent 不只检查格式，还检查引用、来源覆盖、目的匹配和弱来源，并能自动打回上游 Agent 返工。
