# 项目结构说明

每个文件干什么、什么时候用到、代码该写在哪。

## 一句话看懂分层

```
用户请求 → api（收请求） → agent/graph（编排） → agent/nodes（每一步） → git / github / rag（真正干活）
```

- **上层只调用下层**：节点不直接拼 git 命令，而是调 `app/git/` 里的函数；接口不写业务逻辑，而是调 `graph.run()`。
- **`app/git`、`app/github`、`app/rag` 是普通 Python 函数，不依赖 LangGraph**，可以单独测试、单独复用（MCP Server 也复用它们）。

## 目录树

```
Code_archaeology/
│
├── README.md                    项目介绍：解决什么问题、架构图、技术栈、怎么启动
├── requirements.txt             Python 依赖。新装一个库就加一行
├── .env.example                 环境变量模板。复制成 .env 再填（.env 不进 git）
├── .gitignore                   不提交的文件：.env、克隆的仓库、索引、缓存
├── Dockerfile                   把应用打成镜像（部署阶段才用）
├── docker-compose.yml           一键起 app + Caddy（部署阶段才用）
├── Caddyfile                    Caddy 反向代理配置，自动 HTTPS（部署阶段才用）
│
├── app/                         ★ 所有后端代码
│   ├── main.py                  FastAPI 入口：启动服务、挂载接口和网页。基本不用改
│   ├── config.py                读取 .env，生成全局 settings。要加新配置项就在这里加字段
│   │
│   ├── agent/                   ★★ LangGraph 部分，项目核心
│   │   ├── state.py             整张图共享的状态（TypedDict）。
│   │   │                          → 任何节点要往"全局"里存东西，先在这里加字段
│   │   ├── graph.py             把节点连成图：add_node / add_edge / 条件边 / compile。
│   │   │                          对外提供 run()（同步）和 astream()（流式）
│   │   │                          → 加节点、改流程、加循环、加 HITL 中断都改这里
│   │   │
│   │   ├── nodes/               每个节点一个文件。统一写法：读 state → 调下层函数 → 返回要更新的字段
│   │   │   ├── parse_target.py    ① 解析 GitHub 链接 → owner/repo/文件/行号，并确保仓库已克隆
│   │   │   ├── blame.py           ② 对目标行跑 git blame，得到每行对应的 commit
│   │   │   ├── filter_noise.py    ③ 标记格式化/lint/重命名这类没信息量的 commit（标记，不删）
│   │   │   ├── expand_history.py  ④ git log --follow 往更早挖，补全变更链（会被循环执行）
│   │   │   ├── link_context.py    ⑤ 从 commit message 抽 #123，去 GitHub 拉 issue/PR 讨论
│   │   │   ├── assess.py          ⑥ 判断信息够不够 → 决定去 retrieve 还是回到 ④ 还是问用户
│   │   │   ├── retrieve.py        ⑦ 把收集到的材料建索引，检索出最相关的片段
│   │   │   └── narrate.py         ⑧ 调 LLM 生成考古报告（时间线 + 结论 + 出处）
│   │   │
│   │   └── prompts/             给 LLM 的提示词，和代码分开放，方便单独改
│   │       ├── assess.md          assess 节点用：判断"信息够不够"
│   │       └── narrate.md         narrate 节点用：生成报告的要求和正反例
│   │
│   ├── git/                     ★ 所有本地 git 操作
│   │   ├── repo.py              克隆/更新仓库（ensure_cloned）、统一执行 git 命令（run）
│   │   │                          → 任何地方要跑 git 命令，都用这里的 run()，别自己写 subprocess
│   │   └── blame.py             blame()：普通 blame 并解析输出
│   │                            is_noise_commit()：判断一个 commit 是不是格式化提交
│   │                            blame_through()：遇到格式化提交就继续往上 blame（穿透）
│   │
│   ├── github/                  ★ 所有 GitHub API 调用
│   │   └── client.py            extract_refs()：从文本抽 issue 编号
│   │                            get_issue() / get_comments()：拉 issue/PR 正文和评论
│   │                              → 以后加缓存、限流处理、GraphQL 都写在这里
│   │
│   ├── rag/                     ★ 检索（v5 才用到，第一版不碰）
│   │   ├── corpus.py            定义统一的 Document 结构（commit / issue / PR 评论 / 代码）
│   │   ├── chunking.py          把长文本切块：commit 不切、issue 按评论切、代码按函数切
│   │   ├── bm25.py              关键词检索（擅长 #1234、函数名这种精确匹配）
│   │   ├── vector.py            向量检索（擅长"意思相近但用词不同"）
│   │   ├── fusion.py            RRF：把 bm25 和 vector 两路排名合成一个
│   │   └── rerank.py            用 Cross-Encoder 对融合结果再精排
│   │
│   ├── api/
│   │   └── routes.py            HTTP 接口，薄壳，只负责收参数、调 graph、返回结果
│   │                              /excavate         同步考古
│   │                              /excavate/stream  SSE 流式，前端实时看到每一步
│   │                              /resume           HITL 中断后用户选择继续/停止
│   │                              /samples          首页示例
│   │
│   ├── mcp_server/
│   │   └── server.py            把 git/github 能力包装成 MCP 工具，供 Claude 等外部 Agent 调用。
│   │                              独立入口，和 FastAPI 无关（后期做）
│   │
│   └── observability/
│       └── langfuse_setup.py    接 Langfuse：记录每次运行的节点耗时、token、LLM 输入输出（后期做）
│
├── web/
│   └── index.html               前端单页：输入链接、展示报告（接口跑通后再做）
│
├── tests/                       单元测试（pytest）
│   ├── test_blame.py            测 blame 穿透：造一个带格式化提交的小仓库，看能否穿过去
│   └── test_fusion.py           测 RRF 排名是否符合预期
│
├── evals/                       效果评测（全部跑通后才做）
│   ├── README.md                评测思路：用"真实引入这段逻辑的 PR"当标准答案
│   ├── build_dataset.py         从开源仓库自动生成标注数据
│   └── run_eval.py              批量跑 agent，算命中率，对比不同检索方案
│
├── docs/                        设计文档
│   ├── architecture.md          为什么要用 Agent、状态机设计、为什么检索要 Hybrid
│   ├── project-structure.md     本文件
│   └── adr/                     架构决策记录（为什么选 A 不选 B）
│       ├── 0001-hybrid-retrieval-and-rrf.md
│       └── 0002-blame-penetration.md
│
└── data/                        运行时自动生成，不进 git
    ├── repos/                   克隆下来的仓库，如 data/repos/psf/requests
    └── index/                   检索索引
```

## 我要写 X，该写在哪？

| 想做的事 | 写在哪 |
|---|---|
| 加一个新配置（比如换模型、设超时） | `.env` 填值 + `app/config.py` 加字段 |
| 节点之间要传一个新数据 | `app/agent/state.py` 加字段 |
| 加一个新步骤 | `app/agent/nodes/` 新建文件 + `graph.py` 里 `add_node`、`add_edge` |
| 改执行顺序、加循环、加条件判断 | `app/agent/graph.py` |
| 跑一条新的 git 命令 | `app/git/` 里写函数，节点调用它 |
| 调一个新的 GitHub 接口 | `app/github/client.py` 写函数，节点调用它 |
| 改 LLM 的回答风格/要求 | `app/agent/prompts/*.md` |
| 创建 LLM 客户端 | 建议新建 `app/agent/llm.py`，提供 `get_llm()`，各节点共用 |
| 加一个 HTTP 接口 | `app/api/routes.py` |
| 测试某个函数对不对 | `tests/test_xxx.py` |

## 一次请求经过哪些文件（第一版）

以 `run('https://github.com/psf/requests/blob/main/src/requests/utils.py#L50-L60')` 为例：

```
graph.run()                                     agent/graph.py
 └─ graph.invoke({'url': ...})
     ├─ parse_target(state)                     agent/nodes/parse_target.py
     │   └─ ensure_cloned('psf', 'requests')    git/repo.py      → data/repos/psf/requests
     │   返回 owner / repo / file_path / start_line / end_line / repo_path
     ├─ blame(state)                            agent/nodes/blame.py
     │   └─ git_blame(repo_path, file, 50, 60)  git/blame.py
     │       └─ run(['git', 'blame', ...])      git/repo.py
     │   返回 blame_lines
     ├─ link_context(state)                     agent/nodes/link_context.py
     │   ├─ extract_refs(summary)               github/client.py
     │   └─ get_issue(owner, repo, n)           github/client.py
     │   返回 issues
     └─ narrate(state)                          agent/nodes/narrate.py
         └─ ChatOpenAI(...).invoke(prompt)      （读 config.py 里的模型配置）
         返回 report
```

## 各版本用到哪些文件

| 版本 | 新增/改动的文件 |
|---|---|
| v1 直线跑通 | `state.py` `graph.py` `parse_target` `blame` `link_context` `narrate` `git/blame.py::blame` |
| v2 加循环 | `expand_history` `assess` `prompts/assess.md`；`graph.py` 加条件边；`state.py` 加 depth 和 Reducer |
| v3 blame 穿透 | `filter_noise` `git/blame.py::is_noise_commit / blame_through` `tests/test_blame.py` |
| v4 HITL + 流式 | `graph.py` 加 checkpointer 和 interrupt；`routes.py` 的 stream 和 resume |
| v5 检索 | `rag/*` `retrieve` `tests/test_fusion.py` |
| v6 | `mcp_server/` `observability/` `evals/` `web/` |
