# 代码考古学家 · Code Archaeologist

> GitLens 告诉你这行是谁改的。这个告诉你——**为什么**。

给它一个 GitHub 文件链接（或 repo + 文件 + 行号），它穿过 git history、commit message、
关联 issue 与 PR 讨论，还原这段代码的来龙去脉：最初长什么样、哪个 bug 让它变成现在这样、
当时为什么选这个方案、哪些看似多余的判断其实是踩过坑的。

灵感来自 Chesterton's Fence（切斯特顿的栅栏）：**在你删掉这行之前，先知道它为什么在那。**

## 在线体验

TODO 部署后填链接。首页内置若干知名开源项目里著名的"怪代码"，一键试跑，无需注册。

## 它解决什么

接手陌生代码库时，最耗时的不是读懂代码**做什么**，而是搞清它**为什么这么做**。
而"为什么"从来不在代码里——它散落在三年前的 issue 讨论、被 squash 掉的 commit message、
和某个 PR 的 review 评论里。把它们串起来需要多跳检索与推理，这正是 Agent 该干的事。

## 架构

```
GitHub URL
    ↓
[parse_target]   解析 repo / file / lines
    ↓
[blame]          git blame 定位每行最后的 commit（穿透格式化提交）
    ↓
[filter_noise]   剔除纯空白/重命名/lint 提交
    ↓
[expand_history] git log --follow 拿完整变更链
    ↓
[link_context]   从 commit message 抽 issue/PR 编号，拉取讨论
    ↓
[assess] ───────→ 信息不足？回到 expand_history（受 loop limit 约束）
    ↓ 足够
[retrieve]       Hybrid RAG：BM25 + Vector + RRF + Rerank
    ↓
[narrate]        生成时间线叙事
    ↓
考古报告
```

HITL 中断点：深挖层数或 token 预算超限时暂停，询问是否继续。

详见 [docs/architecture.md](docs/architecture.md) 与 [docs/adr/](docs/adr/)。

## 技术栈

| 层 | 选型 |
|---|---|
| 编排 | LangGraph（State / Checkpoint / Interrupt / Streaming） |
| 工具 | MCP Server（git_blame / git_log / search_issues / get_pr ...） |
| 检索 | BM25（rank_bm25）+ 向量（Chroma）+ RRF 融合 + Cross-Encoder Rerank |
| 可观测 | Langfuse（Trace / Dataset / Experiment） |
| API | FastAPI + SSE 流式输出 |
| 前端 | 单文件 HTML（无框架） |
| 部署 | Docker Compose + Caddy（自动 HTTPS） |

## 评测

有真实 ground truth：给定一个函数的当前形态，**真实答案是引入当前逻辑的那个 PR**。
从热门 repo 可自动构造数百条标注，算 Top-1 / Top-3 命中率，并对比 Hybrid vs Vector-only。

见 [evals/README.md](evals/README.md)。

## 快速开始

```bash
cp .env.example .env      # 填 LLM API key 与 GitHub token
pip install -r requirements.txt
uvicorn app.main:app --reload
```

或者：

```bash
docker compose up -d
```

## 开发状态

骨架阶段。各模块的完成度见文件内 TODO。

## License

MIT
