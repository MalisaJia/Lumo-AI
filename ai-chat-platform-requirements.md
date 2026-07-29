# AI Chat Platform Requirements

## English Version

### 1. Product Overview

This product is an AI chat platform similar to the ChatGPT client. The key difference is that users can connect their own API keys from OpenAI-compatible providers. The platform improves answer quality through web search, information cleaning, credibility screening, citation, knowledge retrieval, and structured reasoning.

The goal is to build a customizable AI assistant that can generate reliable, traceable, and high-quality answers while giving users full control over their model providers and API usage.

### 2. Core Value Proposition

- Users can bring their own API keys.
- The platform supports OpenAI-compatible API formats.
- Users can connect different model providers through custom base URLs and model names.
- Users can optionally enable a Model Router to automatically choose cheaper models for simple tasks and stronger, more expensive models for complex tasks.
- The system improves answer quality through web search, source cleaning, credibility evaluation, and citation.
- The assistant can distinguish verified facts, uncertain information, assumptions, and recommendations.
- The platform can support personal knowledge bases, personal knowledge graphs, document retrieval, and advanced research workflows.

### 3. Target Users

- Individual users who want a customizable AI chat client.
- Developers who use multiple OpenAI-compatible model providers.
- Researchers who need source-backed answers.
- Knowledge workers who need document-based Q&A.
- Teams that need private AI assistants with controllable API usage.
- Enterprises that need secure, auditable, and customizable AI tools.

### 4. Model Provider Integration

The platform should allow users to add, manage, and switch between different AI model providers.

Required features:

- Support OpenAI-compatible API format.
- Support custom API base URL.
- Support custom model names.
- Support multiple providers, such as OpenAI, Azure OpenAI, DeepSeek, Qwen, Moonshot, Zhipu, OpenRouter, Together, Groq, and local models.
- Allow users to test whether an API key is valid.
- Allow users to set a default provider and model.
- Allow users to switch models per conversation.
- Support model capability labels, such as text, vision, long context, reasoning, tool calling, and embeddings.
- Support custom model parameters, including temperature, top_p, max tokens, timeout, retry count, presence penalty, and frequency penalty.

Recommended features:

- Provider health check.
- Automatic fallback model when a provider fails.
- Usage tracking by provider and model.
- Cost estimation and token statistics.
- Model speed and quality comparison.

Model Router requirements:

- Users can choose whether to enable or disable the Model Router.
- When the Model Router is disabled, the platform uses the model selected by the user or the default model configured by the user.
- When the Model Router is enabled, the system automatically selects the most suitable model based on task complexity, cost, latency, context length, tool requirements, and model capability.
- Simple tasks should be routed to cheaper and faster models, such as short Q&A, rewriting, translation, summarization, classification, and formatting.
- Complex tasks should be routed to stronger and more expensive models, such as deep reasoning, multi-step research, long-context analysis, code debugging, PDF analysis, image understanding, and tool-heavy workflows.
- Users can configure routing preferences, such as cost-first, quality-first, speed-first, balanced, or custom rules.
- Users can set allowed models, excluded models, maximum cost per request, and fallback models.
- The router should explain the selected model only when transparency mode is enabled or the user asks.
- The router should log routing decisions internally for debugging, cost analysis, and quality evaluation.
- The router should avoid switching models in the middle of a response unless a planned multi-step workflow requires different models for different stages.
- The router should fall back to another suitable model when the selected model fails, times out, or lacks required capabilities.

### 5. Chat Interface

The chat interface should feel familiar, modern, and efficient.

Required features:

- Create new chat.
- Rename chat.
- Delete chat.
- Save conversation history.
- Edit user messages.
- Regenerate assistant responses.
- Continue generation.
- Stop generation.
- Copy assistant response.
- Render Markdown.
- Render code blocks with syntax highlighting.
- Render tables.
- Render mathematical formulas.
- Support file upload.
- Support image upload when the selected model supports vision.
- Search chat history.
- Organize chats by folder, tag, or project.

Recommended features:

- Conversation branching.
- Pin important chats.
- Export chat as Markdown, PDF, HTML, or JSON.
- Prompt templates.
- System prompt presets.
- Side-by-side multi-model comparison.

### 6. Web Search Tool

The platform should support web search to retrieve fresh and external information.

Required features:

- Users can enable or disable web search.
- The system can automatically decide whether web search is needed.
- Users can manually trigger web search.
- Support search providers such as Bing, Google Custom Search, Brave Search, SerpAPI, Tavily, Exa, and SearXNG.
- Search results should include title, URL, snippet, source domain, and publish date when available.
- The system should rewrite search queries to improve retrieval quality.
- The final answer should include source citations when web search is used.

Recommended features:

- Multi-query search.
- Search by language.
- Search by time range.
- Search official sources first for technical, legal, medical, or policy questions.
- Search academic sources separately.
- Search news sources separately.
- Allow trusted-domain search mode.

### 7. Information Cleaning

The platform should clean retrieved content before sending it to the model.

Required features:

- Extract the main content from web pages.
- Remove advertisements, navigation menus, cookie banners, and unrelated sidebars.
- Remove duplicated text.
- Remove low-value SEO content.
- Normalize source metadata, including title, author, domain, publish date, and update date.
- Split long pages into structured chunks.
- Preserve original source links for citation.
- Deduplicate similar search results.

Recommended features:

- Detect AI-generated spam content.
- Detect copied or syndicated content.
- Extract key claims from each source.
- Extract important numbers, dates, entities, and quoted statements.
- Separate facts from opinions.
- Generate a short summary for each source before final synthesis.

### 8. Credibility Screening

The platform should evaluate the trustworthiness of retrieved information before it is used for answer generation. Credibility scoring is an internal ranking and filtering mechanism, not a score that must be displayed in the user interface.

Required features:

- Prefer official sources, primary sources, academic papers, government websites, reputable media, and official documentation.
- Penalize anonymous, spammy, outdated, commercial-only, or citation-free pages.
- Identify source type, such as official website, documentation, media, blog, forum, paper, social media, or commercial landing page.
- Check publication date, update date, author information, publisher information, and citation availability.
- Calculate an internal weighted credibility score for each source using Source reliability, Evidence quality, Freshness, Agreement, and Citation completeness.
- Use the internal credibility score to rank, down-rank, or filter out unreliable sources before the final answer is generated.
- Do not require displaying the raw credibility score in the UI or final answer.
- Warn users when reliable evidence is weak, outdated, insufficient, or conflicting.
- Avoid presenting uncertain information as fact.

Internal scoring dimensions:

- Source reliability: evaluates whether the source is official, primary, reputable, expert-authored, transparent about authorship, and historically reliable.
- Evidence quality: evaluates whether the source provides concrete data, direct evidence, methodology, original documents, quotations, examples, or verifiable claims.
- Freshness: evaluates whether the source is recent enough for the topic and whether the content has a clear publish date or update date.
- Agreement: evaluates whether the source is consistent with other reliable independent sources and whether conflicts are detected.
- Citation completeness: evaluates whether the source cites its own evidence, links to primary materials, provides references, and supports key claims.

Recommended features:

- Configurable weighting by topic type, because medical, legal, financial, technical, news, and evergreen knowledge may require different freshness and reliability priorities.
- Cross-source verification.
- Claim-level confidence scoring.
- Conflict detection between sources.
- Domain reputation database.
- Commercial intent detection.
- Bias detection.
- Explain why a source is considered reliable or unreliable only when transparency mode is enabled or the user asks.
- Use an insufficient-evidence response mode when reliable sources cannot be found.

### 9. Answer Synthesis Engine

The platform should synthesize high-quality answers instead of simply pasting search results into the model.

Required workflow:

1. Understand the user’s intent.
2. Decide whether web search or knowledge retrieval is needed.
3. Generate optimized search queries when needed.
4. Retrieve relevant sources.
5. Clean and structure source content.
6. Rank sources by relevance and credibility.
7. Extract key facts and claims.
8. Compare conflicting information.
9. Generate a structured final answer.
10. Add citations for factual claims.
11. Mark uncertainty when evidence is insufficient.

Recommended answer modes:

- Quick answer.
- Deep research.
- Technical explanation.
- Business analysis.
- Step-by-step tutorial.
- Comparison table.
- Decision recommendation.
- Source-backed report.
- Code assistant mode.
- Writing assistant mode.

### 10. Citation System

The platform should make answers traceable.

Required features:

- Inline citations.
- Source list at the end of the answer.
- Display source title, domain, and URL.
- Connect citations to specific claims whenever possible.
- Avoid citing irrelevant or weak sources.
- Clearly state when no reliable source is found.

Recommended features:

- Quote original source text.
- Show confidence level for key claims.
- Allow users to open source previews.
- Allow users to inspect cleaned source content.

### 11. Personal Knowledge Base

The platform should allow users to upload and query their own documents.

Required features:

- Upload PDF, DOCX, TXT, Markdown, CSV, and XLSX files.
- Parse uploaded documents.
- Split documents into chunks.
- Generate embeddings for document chunks.
- Store documents in a searchable knowledge base.
- Retrieve relevant document chunks during chat.
- Cite uploaded documents in answers.
- Support project-level knowledge bases.

Recommended features:

- Folder-based document organization.
- Document permission control.
- Automatic document summary.
- Hybrid search using keyword search and vector search.
- Reranking for higher retrieval accuracy.
- Knowledge freshness detection.

Personal Knowledge Graph:

- The platform should support building a personal knowledge graph from user conversations, uploaded documents, notes, web sources, and project knowledge bases.
- The knowledge graph should extract and connect entities, concepts, people, organizations, projects, documents, events, tasks, decisions, and relationships.
- Users should be able to inspect, search, edit, merge, delete, and correct knowledge graph nodes and relationships.
- The assistant should use the knowledge graph to understand user context, reduce repeated questions, and provide more personalized answers.
- The knowledge graph should support source attribution so each node or relationship can be traced back to the original conversation, file, web source, or user input.
- Users should be able to enable, disable, or limit knowledge graph usage per workspace, project, or chat.
- The system should distinguish stable long-term facts from temporary context, assumptions, inferred relationships, and user-confirmed knowledge.
- The assistant should ask for confirmation before storing sensitive, uncertain, or high-impact personal knowledge.
- The knowledge graph should support privacy controls, export, deletion, and audit logs.

Recommended features:

- Automatic entity resolution and deduplication.
- Relationship confidence scoring.
- Timeline view for events, decisions, and project history.
- Graph-based retrieval combined with vector search and keyword search.
- Conflict detection when new information contradicts existing knowledge.
- User-controlled memory rules for what should or should not be remembered.

### 12. Prompt and Behavior Settings

Users should be able to control how the assistant behaves.

Required features:

- Global system prompt.
- Per-chat system prompt.
- Preset assistant roles.
- Custom prompt templates.
- User preference memory.
- Option to enable or disable memory.
- Option to enable or disable web search.
- Option to require citations.
- Control answer length, tone, and format.

Recommended modes:

- Strict evidence mode: answer only from verified sources.
- Creative mode: suitable for writing and brainstorming.
- Professional mode: concise and structured.
- Developer mode: optimized for coding and debugging.
- Research mode: multi-source and citation-heavy.

### 13. Tool System

The platform should support tools that expand the assistant’s capabilities.

Recommended tools:

- Web search.
- Web page reader.
- File reader.
- PDF reader.
- Image understanding.
- Code interpreter.
- Calculator.
- Data table analyzer.
- Translation tool.
- Summarization tool.
- Fact-checking tool.
- URL credibility checker.
- Document comparison tool.
- Knowledge base search.
- Vector retrieval.
- Optional browser automation.
- Optional external API calling tool.

Key tool capability requirements:

Image understanding:

- Users can upload images and ask questions about visual content.
- Support screenshot analysis, UI analysis, chart interpretation, document image reading, and general visual question answering.
- Support OCR for extracting text from images.
- Detect tables, forms, diagrams, icons, objects, and layout structures in images.
- Allow the assistant to cite image regions or describe where visual evidence appears.
- Support multi-image comparison for before-and-after analysis, product comparison, design review, and error diagnosis.
- Respect model capability limits when the selected model does not support vision.

PDF analysis:

- Users can upload PDFs for summarization, question answering, extraction, and comparison.
- Support text-based PDFs and scanned PDFs with OCR.
- Extract headings, paragraphs, tables, figures, page numbers, footnotes, and references.
- Support page-level citation in answers.
- Support long PDF chunking, semantic retrieval, and cross-page reasoning.
- Allow users to ask for summaries, key points, risk points, contract clauses, financial numbers, research conclusions, and action items.
- Support comparison between multiple PDFs.

Search capability:

- Support both manual search and automatic search triggered by user intent.
- Support general web search, academic search, news search, documentation search, and trusted-domain search.
- Rewrite and expand user queries into multiple search queries when needed.
- Merge, deduplicate, clean, and rank search results before answer generation.
- Show search process, selected sources, excluded sources, and reasons when transparency mode is enabled.
- Support citation-backed answers, source previews, and insufficient-evidence warnings.

Code execution:

- Provide a secure sandbox for running code when users ask the assistant to calculate, test, analyze data, or debug.
- Support common languages such as Python and JavaScript at minimum.
- Allow code execution for data analysis, file parsing, chart generation, algorithm testing, and reproducible calculations.
- Capture standard output, errors, generated files, charts, and execution logs.
- Apply timeout, memory, network, file system, and package installation restrictions.
- Require explicit user confirmation before running risky code or code that accesses external networks.
- Clearly separate model-generated reasoning from actual execution results.

Tool usage governance:

- The assistant can decide when to use tools, but users can enable, disable, or approve tool use.
- Show which tools were used and why they were used.
- Keep tool execution logs for debugging, auditability, and answer verification.
- Support per-tool permission settings, such as always allow, ask every time, or disabled.
- Prevent tools from exposing API keys, secrets, private files, or sensitive user data.
- Allow the assistant to combine tools in workflows, such as search, read sources, analyze PDF, run code, and synthesize an answer.
- Provide graceful fallback when a tool fails, times out, or returns low-quality results.

### 14. API Key Management and Security

Because users bring their own API keys, security is a core requirement.

Required features:

- Encrypt API keys at rest.
- Never expose raw API keys in frontend responses.
- Mask API keys in the user interface.
- Allow users to delete API keys.
- Validate API keys before saving.
- Track which provider and key are used for each request.
- Support local-only key storage for personal deployments.

Recommended features:

- Workspace-level key sharing.
- Role-based access control.
- Provider-level spending limits.
- Usage alerts.
- Secret redaction before sending content to external models.
- Audit logs for team and enterprise users.

### 15. Privacy and Data Control

The platform should give users control over their data.

Required features:

- Clear privacy policy.
- Delete all conversations.
- Export all user data.
- Disable logging.
- Disable memory.
- Private chat mode.
- No training on user data by default.
- Warn users before sending sensitive content to external tools or models.

Recommended features:

- Local deployment mode.
- Per-chat retention settings.
- Automatic sensitive information detection.
- Enterprise audit logs.
- Data residency configuration.

### 16. Hallucination Reduction

The platform should reduce unsupported or fabricated answers.

Required features:

- The assistant should avoid unsupported claims.
- The assistant should ask clarifying questions when the user’s intent is ambiguous.
- The assistant should say that evidence is insufficient when reliable information cannot be found.
- Factual claims should be supported by citations when web search or knowledge retrieval is used.
- The assistant should separate facts, assumptions, analysis, and recommendations.

Recommended features:

- Automatic answer verification pass.
- Claim extraction and validation.
- Contradiction detection.
- Confidence labels such as high, medium, and low.
- Self-check before final response.

### 17. Evaluation and Feedback

The platform should continuously evaluate the answer quality of the AI assistant to ensure that system performance does not degrade after changes to models, prompts, retrieval strategies, embeddings, rerankers, tools, or knowledge bases.

Required features:

- Like and dislike feedback.
- Regenerate response.
- Report issue.
- Track response latency.
- Track token usage.
- Track failed requests.
- Track source quality.
- Track citation coverage.

Golden Dataset:

- The system should support creating and managing standardized test question sets for evaluating AI assistant capabilities.
- Each test case should include the user question.
- Each test case should include expected answer criteria.
- Each test case should include required concepts, keywords, or must-include information.
- Each test case may include required sources.
- Each test case should include category labels for applicable scenarios.
- The system should support multiple evaluation datasets for different task types.

Recommended Golden Dataset categories:

- Technical Q&A evaluation set.
- Academic paper understanding evaluation set.
- Document retrieval evaluation set.
- Web search evaluation set.
- Writing assistance evaluation set.
- PDF analysis evaluation set.
- Image understanding evaluation set.
- Code execution and debugging evaluation set.

Automated answer evaluation:

- The system should automatically run the AI assistant against Golden Datasets.
- The system should compare answer quality across different system versions and configurations.
- Evaluation should measure answer accuracy.
- Evaluation should measure information completeness.
- Evaluation should measure factual faithfulness.
- Evaluation should measure citation correctness.
- Evaluation should measure citation completeness.
- Evaluation should measure answer relevance.
- Evaluation should measure whether required concepts are covered.
- Evaluation should measure whether required sources are used when required.

Version and configuration comparison:

- The system should record the model version used for each evaluation run.
- The system should record the prompt version used for each evaluation run.
- The system should record the retrieval strategy used for each evaluation run.
- The system should record the embedding model used for each evaluation run.
- The system should record the reranker configuration used for each evaluation run.
- The system should record tool configuration, web search settings, and knowledge base version when relevant.
- The system should support comparing how different configurations affect answer quality, cost, latency, citation quality, and failure rate.

Recommended features:

- Compare answer quality across models.
- A/B test prompts.
- Human evaluation dashboard.
- Automated factuality scoring.
- Regression alerts when evaluation scores drop below a configured threshold.
- Evaluation reports for release validation before deploying new models, prompts, retrieval strategies, or knowledge base updates.

### 18. Admin Panel

The platform should provide management capabilities for administrators.

Required features:

- User management.
- Provider configuration.
- Model list management.
- Search provider configuration.
- Tool configuration.
- Usage analytics.
- Error logs.
- Cost tracking.

Recommended features:

- Team workspace management.
- Billing management.
- Rate limit configuration.
- Abuse detection.
- System prompt management.
- Feature flags.

### 19. Recommended Technical Architecture

Frontend:

- Next.js or React.
- TypeScript.
- Tailwind CSS.
- Streaming response support.
- Markdown renderer.
- Code highlighting.
- Responsive layout.
- Light mode and dark mode.

Backend:

- Node.js with NestJS or Fastify, or Python with FastAPI.
- OpenAI-compatible provider adapter.
- Chat completion proxy.
- Tool orchestration engine.
- Web search pipeline.
- Web page extraction service.
- Source ranking service.
- Retrieval-augmented generation service.
- User authentication.
- Encrypted API key storage.
- Streaming response endpoint.
- Rate limiting.
- Logging and monitoring.

Storage:

- PostgreSQL for relational data.
- Redis for caching and queues.
- pgvector, Qdrant, Milvus, Weaviate, or Chroma for vector search.
- Object storage for uploaded files.

### 20. MVP Scope

The first version should focus on the smallest useful product.

MVP features:

- Users can add OpenAI-compatible API key, base URL, and model name.
- Users can validate API keys.
- Chat interface supports streaming responses.
- Users can switch models per chat.
- Users can optionally enable Model Router to route simple tasks to cheaper models and complex tasks to stronger models.
- Conversations are saved.
- Manual web search can be enabled.
- Search results are cleaned and summarized.
- Sources are ranked by credibility.
- Final answers include citations.
- API keys are encrypted.
- Basic token usage statistics are available.
- Basic image upload and image question answering are available when the selected model supports vision.
- PDF upload, text extraction, summarization, and page-level citation are available.
- A controlled code execution sandbox is available for calculations, data analysis, and debugging.
- Tool usage can be enabled or disabled by users, with visible execution logs.

### 21. Advanced Roadmap

Future features:

- Personal knowledge base.
- Personal knowledge graph.
- Automatic web search decision.
- Deep research mode.
- Claim-level fact checking.
- Multi-model comparison.
- Team workspace.
- Admin dashboard.
- Cost control.
- Prompt marketplace.
- Local model support.
- Browser automation.
- Enterprise security and audit features.

### 22. Suggested Product Modules

- Chat module.
- Model provider module.
- Model Router module.
- API key management module.
- Web search module.
- Information cleaning module.
- Credibility scoring module.
- Citation module.
- Knowledge base module.
- Personal knowledge graph module.
- Prompt template module.
- User memory module.
- Tool orchestration module.
- Multimodal image analysis module.
- PDF analysis module.
- Code execution sandbox module.
- Tool permission and audit module.
- Evaluation and regression testing module.
- Usage and billing module.
- Admin module.
- Security and privacy module.

### 23. Product Definition

A customizable AI chat platform that lets users connect their own OpenAI-compatible API keys and generate reliable, source-backed answers through web search, information cleaning, credibility scoring, citation, and knowledge retrieval.

---

## 中文版本

### 1. 产品概述

本产品是一个类似 ChatGPT 客户端的 AI 聊天平台。它的核心差异是允许用户接入自己的 OpenAI 兼容格式 API Key。平台通过联网搜索、信息清理、可信度筛查、引用标注、知识库检索和结构化推理来提升回答质量。

产品目标是打造一个可自定义的 AI 助手，让用户能够掌控自己的模型供应商和 API 使用方式，同时获得更可靠、可追溯、更高质量的回答。

### 2. 核心价值

- 用户可以接入自己的 API Key。
- 平台支持 OpenAI 兼容 API 格式。
- 用户可以通过自定义 base URL 和模型名称接入不同模型供应商。
- 用户可以选择是否启用 Model Router，让系统自动为简单任务选择便宜模型，为复杂任务选择能力更强但更贵的模型。
- 系统通过联网搜索、信息清理、可信度评估和引用标注提升回答质量。
- 助手可以区分已验证事实、不确定信息、假设和建议。
- 平台可支持个人知识库、个人知识图谱、文档检索和高级研究工作流。

### 3. 目标用户

- 希望拥有可自定义 AI 聊天客户端的个人用户。
- 使用多个 OpenAI 兼容模型供应商的开发者。
- 需要有来源支撑答案的研究人员。
- 需要基于文档进行问答的知识工作者。
- 需要私有 AI 助手和可控 API 使用的团队。
- 需要安全、可审计、可定制 AI 工具的企业。

### 4. 模型供应商接入

平台应允许用户添加、管理和切换不同 AI 模型供应商。

必需功能：

- 支持 OpenAI 兼容 API 格式。
- 支持自定义 API base URL。
- 支持自定义模型名称。
- 支持多个供应商，例如 OpenAI、Azure OpenAI、DeepSeek、Qwen、Moonshot、Zhipu、OpenRouter、Together、Groq 和本地模型。
- 允许用户测试 API Key 是否有效。
- 允许用户设置默认供应商和模型。
- 允许用户按会话切换模型。
- 支持模型能力标签，例如文本、视觉、长上下文、推理、工具调用和嵌入。
- 支持自定义模型参数，包括 temperature、top_p、max tokens、timeout、retry count、presence penalty 和 frequency penalty。

推荐功能：

- 供应商健康检查。
- 当某个供应商失败时自动切换备用模型。
- 按供应商和模型统计用量。
- 成本估算和 token 统计。
- 模型速度和质量对比。

Model Router 需求：

- 用户可以自行选择启用或关闭 Model Router。
- 当 Model Router 关闭时，平台使用用户手动选择的模型或用户配置的默认模型。
- 当 Model Router 启用时，系统根据任务复杂度、成本、延迟、上下文长度、工具需求和模型能力自动选择最合适的模型。
- 简单任务应路由到更便宜、更快的模型，例如短问答、改写、翻译、摘要、分类和格式整理。
- 复杂任务应路由到能力更强但更贵的模型，例如深度推理、多步研究、长上下文分析、代码调试、PDF 分析、图片理解和大量工具调用工作流。
- 用户可以配置路由偏好，例如成本优先、质量优先、速度优先、平衡模式或自定义规则。
- 用户可以设置允许使用的模型、排除的模型、单次请求最高成本和备用模型。
- 仅在透明模式开启或用户询问时，解释本次为什么选择某个模型。
- Router 应在内部记录路由决策，用于调试、成本分析和质量评估。
- 除非计划中的多步骤工作流需要不同阶段使用不同模型，否则 Router 不应在单次回答中途随意切换模型。
- 当被选中的模型失败、超时或缺少所需能力时，Router 应自动切换到另一个合适模型。

### 5. 聊天界面

聊天界面应熟悉、现代且高效。

必需功能：

- 新建聊天。
- 重命名聊天。
- 删除聊天。
- 保存会话历史。
- 编辑用户消息。
- 重新生成助手回复。
- 继续生成。
- 停止生成。
- 复制助手回复。
- 渲染 Markdown。
- 渲染带语法高亮的代码块。
- 渲染表格。
- 渲染数学公式。
- 支持文件上传。
- 当所选模型支持视觉能力时支持图片上传。
- 搜索聊天历史。
- 按文件夹、标签或项目组织聊天。

推荐功能：

- 会话分支。
- 置顶重要聊天。
- 导出聊天为 Markdown、PDF、HTML 或 JSON。
- 提示词模板。
- 系统提示词预设。
- 多模型并排对比。

### 6. 联网搜索工具

平台应支持联网搜索，以获取实时和外部信息。

必需功能：

- 用户可以启用或关闭联网搜索。
- 系统可以自动判断是否需要联网搜索。
- 用户可以手动触发联网搜索。
- 支持 Bing、Google Custom Search、Brave Search、SerpAPI、Tavily、Exa 和 SearXNG 等搜索供应商。
- 搜索结果应包含标题、URL、摘要、来源域名，以及可用时的发布日期。
- 系统应重写搜索查询，以提升检索质量。
- 使用联网搜索时，最终答案应包含来源引用。

推荐功能：

- 多查询搜索。
- 按语言搜索。
- 按时间范围搜索。
- 对技术、法律、医疗或政策问题优先搜索官方来源。
- 单独搜索学术来源。
- 单独搜索新闻来源。
- 支持可信域名搜索模式。

### 7. 信息清理

平台应在将检索内容发送给模型前进行清理。

必需功能：

- 从网页中提取正文内容。
- 移除广告、导航菜单、Cookie 横幅和无关侧边栏。
- 移除重复文本。
- 移除低价值 SEO 内容。
- 规范化来源元数据，包括标题、作者、域名、发布日期和更新日期。
- 将长页面拆分为结构化片段。
- 保留原始来源链接用于引用。
- 对相似搜索结果去重。

推荐功能：

- 检测 AI 生成的垃圾内容。
- 检测复制或转载内容。
- 从每个来源中抽取关键主张。
- 抽取重要数字、日期、实体和引用语句。
- 区分事实与观点。
- 在最终综合回答前为每个来源生成简短摘要。

### 8. 可信度筛查

平台应在信息被用于生成答案前评估其可信度。可信度评分是内部排序和过滤机制，不是必须展示在用户界面中的分数。

必需功能：

- 优先采用官方来源、一手来源、学术论文、政府网站、权威媒体和官方文档。
- 降低匿名、垃圾、过时、纯商业导向或无引用页面的权重。
- 识别来源类型，例如官方网站、文档、媒体、博客、论坛、论文、社交媒体或商业落地页。
- 检查发布日期、更新日期、作者信息、发布方信息和引用可用性。
- 使用 Source reliability、Evidence quality、Freshness、Agreement 和 Citation completeness 为每个来源计算内部加权可信度评分。
- 使用内部可信度评分在生成最终答案前对来源进行排序、降权或过滤掉不可信来源。
- 不要求在 UI 或最终答案中展示原始可信度评分。
- 当可靠证据较弱、过时、不足或互相冲突时提醒用户。
- 避免将不确定信息表述为事实。

内部评分维度：

- Source reliability：评估来源是否官方、一手、权威、由专家撰写、作者信息透明，以及历史可靠性。
- Evidence quality：评估来源是否提供具体数据、直接证据、方法论、原始文件、引用语句、示例或可验证主张。
- Freshness：评估来源对当前主题是否足够新，以及内容是否有明确发布日期或更新日期。
- Agreement：评估该来源是否与其他可靠且独立的来源一致，以及是否存在冲突信息。
- Citation completeness：评估来源本身是否引用证据、链接一手材料、提供参考文献，并支撑关键主张。

推荐功能：

- 支持按主题类型配置权重，因为医疗、法律、金融、技术、新闻和长期知识对新鲜度与可靠性的要求不同。
- 多来源交叉验证。
- 主张级置信度评分。
- 来源之间的冲突检测。
- 域名信誉数据库。
- 商业意图检测。
- 偏见检测。
- 仅在透明模式开启或用户询问时，解释为什么某个来源可靠或不可靠。
- 当无法找到可靠来源时，使用“证据不足”回答模式。

### 9. 答案综合引擎

平台不应只是把搜索结果直接交给模型，而应综合生成高质量答案。

必需工作流：

1. 理解用户意图。
2. 判断是否需要联网搜索或知识库检索。
3. 在需要时生成优化后的搜索查询。
4. 检索相关来源。
5. 清理和结构化来源内容。
6. 根据相关性和可信度对来源排序。
7. 抽取关键事实和主张。
8. 比较冲突信息。
9. 生成结构化最终答案。
10. 为事实性主张添加引用。
11. 当证据不足时标注不确定性。

推荐回答模式：

- 快速回答。
- 深度研究。
- 技术解释。
- 商业分析。
- 分步教程。
- 对比表格。
- 决策建议。
- 有来源支撑的报告。
- 代码助手模式。
- 写作助手模式。

### 10. 引用系统

平台应让答案具备可追溯性。

必需功能：

- 行内引用。
- 在答案末尾列出来源清单。
- 显示来源标题、域名和 URL。
- 尽可能将引用对应到具体主张。
- 避免引用无关或低可信来源。
- 当找不到可靠来源时明确说明。

推荐功能：

- 引用原始来源文本。
- 为关键主张显示置信度。
- 允许用户打开来源预览。
- 允许用户查看清理后的来源内容。

### 11. 个人知识库

平台应允许用户上传并查询自己的文档。

必需功能：

- 上传 PDF、DOCX、TXT、Markdown、CSV 和 XLSX 文件。
- 解析上传文档。
- 将文档切分为片段。
- 为文档片段生成嵌入向量。
- 将文档存储到可搜索知识库中。
- 在聊天过程中检索相关文档片段。
- 在答案中引用上传文档。
- 支持项目级知识库。

推荐功能：

- 基于文件夹的文档组织。
- 文档权限控制。
- 自动文档摘要。
- 结合关键词搜索和向量搜索的混合搜索。
- 用重排序提升检索准确率。
- 知识新鲜度检测。

个人知识图谱（Personal Knowledge Graph）：

- 平台应支持从用户会话、上传文档、笔记、网页来源和项目知识库中构建个人知识图谱。
- 知识图谱应抽取并连接实体、概念、人物、组织、项目、文档、事件、任务、决策和关系。
- 用户应能够查看、搜索、编辑、合并、删除和纠正知识图谱节点与关系。
- 助手应使用知识图谱理解用户上下文，减少重复提问，并提供更个性化的回答。
- 知识图谱应支持来源归因，使每个节点或关系都可以追溯到原始会话、文件、网页来源或用户输入。
- 用户应能够按工作区、项目或聊天启用、关闭或限制知识图谱使用。
- 系统应区分稳定的长期事实、临时上下文、假设、推断关系和用户确认过的知识。
- 在存储敏感、不确定或高影响个人知识前，助手应请求用户确认。
- 知识图谱应支持隐私控制、导出、删除和审计日志。

推荐功能：

- 自动实体消歧和去重。
- 关系置信度评分。
- 用于事件、决策和项目历史的时间线视图。
- 将图谱检索与向量搜索、关键词搜索结合。
- 当新信息与既有知识矛盾时进行冲突检测。
- 用户可控制哪些内容应该或不应该被记忆。

### 12. 提示词与行为设置

用户应能够控制助手的行为方式。

必需功能：

- 全局系统提示词。
- 单个聊天的系统提示词。
- 预设助手角色。
- 自定义提示词模板。
- 用户偏好记忆。
- 启用或关闭记忆。
- 启用或关闭联网搜索。
- 是否强制要求引用。
- 控制答案长度、语气和格式。

推荐模式：

- 严格证据模式：只基于已验证来源回答。
- 创意模式：适合写作和头脑风暴。
- 专业模式：简洁且结构化。
- 开发者模式：针对编码和调试优化。
- 研究模式：多来源且引用丰富。

### 13. 工具系统

平台应支持扩展助手能力的工具。

推荐工具：

- 联网搜索。
- 网页阅读器。
- 文件阅读器。
- PDF 阅读器。
- 图像理解。
- 代码解释器。
- 计算器。
- 数据表分析器。
- 翻译工具。
- 摘要工具。
- 事实核查工具。
- URL 可信度检查器。
- 文档对比工具。
- 知识库搜索。
- 向量检索。
- 可选浏览器自动化。
- 可选外部 API 调用工具。

关键工具能力需求：

图片理解：

- 用户可以上传图片，并围绕图片内容提问。
- 支持截图分析、界面分析、图表解读、文档图片阅读和通用视觉问答。
- 支持 OCR，从图片中提取文字。
- 识别图片中的表格、表单、图示、图标、物体和版式结构。
- 允许助手说明视觉证据出现在图片的哪个区域。
- 支持多图对比，用于前后变化分析、产品对比、设计评审和错误诊断。
- 当所选模型不支持视觉能力时，应明确提示能力限制。

PDF 分析：

- 用户可以上传 PDF，用于摘要、问答、信息抽取和文档对比。
- 支持文本型 PDF 和需要 OCR 的扫描型 PDF。
- 提取标题、段落、表格、图片、页码、脚注和参考文献。
- 在答案中支持页码级引用。
- 支持长 PDF 切分、语义检索和跨页面推理。
- 用户可以要求提炼摘要、关键点、风险点、合同条款、财务数字、研究结论和行动项。
- 支持多个 PDF 之间的对比分析。

搜索能力：

- 支持用户手动搜索，也支持根据用户意图自动触发搜索。
- 支持通用网页搜索、学术搜索、新闻搜索、文档搜索和可信域名搜索。
- 在需要时将用户问题改写和扩展为多个搜索查询。
- 在生成答案前对搜索结果进行合并、去重、清理和排序。
- 开启透明模式时，展示搜索过程、采用的来源、排除的来源及原因。
- 支持带引用的答案、来源预览和证据不足提醒。

代码运行：

- 当用户要求计算、测试、分析数据或调试时，提供安全沙箱运行代码。
- 至少支持 Python 和 JavaScript 等常用语言。
- 可用于数据分析、文件解析、图表生成、算法测试和可复现实验计算。
- 捕获标准输出、错误信息、生成文件、图表和执行日志。
- 对运行时间、内存、网络、文件系统和依赖安装进行限制。
- 在运行高风险代码或访问外部网络前，必须获得用户明确确认。
- 清晰区分模型生成的推理内容和真实代码执行结果。

工具使用治理：

- 助手可以判断何时使用工具，但用户可以启用、关闭或审批工具使用。
- 展示使用了哪些工具以及为什么使用这些工具。
- 保留工具执行日志，用于调试、审计和答案验证。
- 支持按工具设置权限，例如始终允许、每次询问或禁用。
- 防止工具暴露 API Key、密钥、私有文件或敏感用户数据。
- 允许助手组合多个工具形成工作流，例如搜索、阅读来源、分析 PDF、运行代码并综合答案。
- 当工具失败、超时或返回低质量结果时，应提供可理解的降级方案。

### 14. API Key 管理与安全

由于用户会接入自己的 API Key，安全性是核心需求。

必需功能：

- 静态加密存储 API Key。
- 永远不在前端响应中暴露原始 API Key。
- 在用户界面中遮蔽 API Key。
- 允许用户删除 API Key。
- 保存前验证 API Key。
- 记录每次请求使用的供应商和 Key。
- 支持个人部署中的本地-only Key 存储。

推荐功能：

- 工作区级 Key 共享。
- 基于角色的访问控制。
- 供应商级消费限制。
- 用量提醒。
- 在向外部模型发送内容前进行敏感信息脱敏。
- 面向团队和企业用户的审计日志。

### 15. 隐私与数据控制

平台应让用户掌控自己的数据。

必需功能：

- 清晰的隐私政策。
- 删除所有会话。
- 导出所有用户数据。
- 关闭日志记录。
- 关闭记忆。
- 私密聊天模式。
- 默认不使用用户数据进行训练。
- 在向外部工具或模型发送敏感内容前提醒用户。

推荐功能：

- 本地部署模式。
- 按聊天设置数据保留周期。
- 自动检测敏感信息。
- 企业审计日志。
- 数据驻留配置。

### 16. 幻觉降低

平台应减少无依据或编造的回答。

必需功能：

- 助手应避免无依据的主张。
- 当用户意图不明确时，助手应提出澄清问题。
- 当无法找到可靠信息时，助手应说明证据不足。
- 使用联网搜索或知识库检索时，事实性主张应有引用支撑。
- 助手应区分事实、假设、分析和建议。

推荐功能：

- 自动答案验证流程。
- 主张抽取与验证。
- 矛盾检测。
- 高、中、低等置信度标签。
- 最终回答前自检。

### 17. 评估与反馈

平台应具备持续评估 AI 助手回答质量的能力，确保模型、Prompt、检索策略、Embedding、Reranker、工具或知识库更新后，系统性能不会下降。

必需功能：

- 点赞和点踩反馈。
- 重新生成回答。
- 问题上报。
- 记录响应延迟。
- 记录 token 使用量。
- 记录失败请求。
- 跟踪来源质量。
- 跟踪引用覆盖率。

质量测试集（Golden Dataset）：

- 系统应支持创建和管理标准测试问题集，用于评估 AI 助手能力。
- 每条测试样例应包含用户问题（Question）。
- 每条测试样例应包含预期回答要点（Expected Answer Criteria）。
- 每条测试样例应包含关键关键词或必须包含的信息（Required Concepts）。
- 每条测试样例可包含参考来源（Required Sources）。
- 每条测试样例应包含适用场景标签（Category）。
- 系统应支持针对不同任务建立多个测试集合。

推荐测试集类型：

- 技术问答测试集。
- 学术论文理解测试集。
- 文档检索测试集。
- 联网搜索测试集。
- 写作辅助测试集。
- PDF 分析测试集。
- 图片理解测试集。
- 代码运行与调试测试集。

自动化回答评估：

- 系统应支持使用 Golden Dataset 自动运行 AI 助手。
- 系统应支持比较不同系统版本和配置之间的回答质量。
- 评估内容应包括回答准确性（Accuracy）。
- 评估内容应包括信息完整性（Completeness）。
- 评估内容应包括事实一致性（Faithfulness）。
- 评估内容应包括引用正确性（Citation Correctness）。
- 评估内容应包括引用覆盖率（Citation Completeness）。
- 评估内容应包括回答相关性（Relevance）。
- 评估内容应包括是否覆盖关键概念（Required Concepts Coverage）。
- 评估内容应包括在需要时是否使用指定参考来源（Required Sources Usage）。

版本与配置对比：

- 系统应记录每次评估使用的模型版本。
- 系统应记录每次评估使用的 Prompt 版本。
- 系统应记录每次评估使用的检索策略。
- 系统应记录每次评估使用的 Embedding 模型。
- 系统应记录每次评估使用的 Reranker 配置。
- 在相关场景下，系统应记录工具配置、联网搜索设置和知识库版本。
- 系统应支持比较不同配置对回答质量、成本、延迟、引用质量和失败率的影响。

推荐功能：

- 跨模型比较回答质量。
- 提示词 A/B 测试。
- 人工评估面板。
- 自动事实性评分。
- 当评估分数低于配置阈值时触发回归提醒。
- 在部署新模型、Prompt、检索策略或知识库更新前生成评估报告，用于发布验证。

### 18. 管理后台

平台应为管理员提供管理能力。

必需功能：

- 用户管理。
- 供应商配置。
- 模型列表管理。
- 搜索供应商配置。
- 工具配置。
- 用量分析。
- 错误日志。
- 成本统计。

推荐功能：

- 团队工作区管理。
- 计费管理。
- 速率限制配置。
- 滥用检测。
- 系统提示词管理。
- 功能开关。

### 19. 推荐技术架构

前端：

- Next.js 或 React。
- TypeScript。
- Tailwind CSS。
- 流式响应支持。
- Markdown 渲染器。
- 代码高亮。
- 响应式布局。
- 明亮模式和深色模式。

后端：

- Node.js 搭配 NestJS 或 Fastify，或 Python 搭配 FastAPI。
- OpenAI 兼容供应商适配器。
- 聊天补全代理。
- 工具编排引擎。
- 联网搜索管线。
- 网页内容提取服务。
- 来源排序服务。
- 检索增强生成服务。
- 用户认证。
- 加密 API Key 存储。
- 流式响应接口。
- 速率限制。
- 日志和监控。

存储：

- PostgreSQL 用于关系型数据。
- Redis 用于缓存和队列。
- pgvector、Qdrant、Milvus、Weaviate 或 Chroma 用于向量搜索。
- 对象存储用于上传文件。

### 20. MVP 范围

第一版应聚焦最小可用产品。

MVP 功能：

- 用户可以添加 OpenAI 兼容 API Key、base URL 和模型名称。
- 用户可以验证 API Key。
- 聊天界面支持流式响应。
- 用户可以按聊天切换模型。
- 用户可以选择启用 Model Router，将简单任务路由到便宜模型，将复杂任务路由到更强模型。
- 保存会话。
- 可手动启用联网搜索。
- 清理和摘要搜索结果。
- 按可信度对来源排序。
- 最终答案包含引用。
- API Key 加密存储。
- 提供基础 token 用量统计。
- 当所选模型支持视觉能力时，支持基础图片上传和图片问答。
- 支持 PDF 上传、文本提取、摘要和页码级引用。
- 提供受控代码执行沙箱，用于计算、数据分析和调试。
- 用户可以启用或关闭工具使用，并查看工具执行日志。

### 21. 高级路线图

未来功能：

- 个人知识库。
- 个人知识图谱。
- 自动判断是否需要联网搜索。
- 深度研究模式。
- 主张级事实核查。
- 多模型对比。
- 团队工作区。
- 管理后台。
- 成本控制。
- 提示词市场。
- 本地模型支持。
- 浏览器自动化。
- 企业安全和审计功能。

### 22. 建议产品模块

- 聊天模块。
- 模型供应商模块。
- Model Router 模块。
- API Key 管理模块。
- 联网搜索模块。
- 信息清理模块。
- 可信度评分模块。
- 引用模块。
- 知识库模块。
- 个人知识图谱模块。
- 提示词模板模块。
- 用户记忆模块。
- 工具编排模块。
- 多模态图片分析模块。
- PDF 分析模块。
- 代码执行沙箱模块。
- 工具权限与审计模块。
- 评估与回归测试模块。
- 用量和计费模块。
- 管理后台模块。
- 安全与隐私模块。

### 23. 产品定义

一个可自定义的 AI 聊天平台，允许用户接入自己的 OpenAI 兼容 API Key，并通过联网搜索、信息清理、可信度评分、引用标注和知识库检索生成可靠、有来源支撑的高质量答案。
