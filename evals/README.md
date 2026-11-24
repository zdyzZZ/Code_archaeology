# 评测

## 为什么这个项目的评测是真的

大部分 Agent 项目的评测集是自己造的，数字没有说服力。这个项目有**天然的 ground truth**：

> 给定一个函数的当前形态，"引入当前逻辑的那个 PR"是客观存在的事实。

所以可以从热门开源仓库自动构造标注集，规模上百条不费力。

## 构造方法

脚本：`python -m evals.build_dataset`，输出 `evals/dataset.jsonl`（固定随机种子，每次生成的一样）。

1. **挑仓库**：根目录有 `.git-blame-ignore-revs` 的项目（维护者自己列出的格式化提交）。
   目前用 psf/requests、pytest-dev/pytest、scrapy/scrapy，每个 14 条，共 42 条
2. **算标准答案**：`git blame -w --ignore-revs-file .git-blame-ignore-revs HEAD` 跳过维护者列出的格式化提交，
   连续 4-15 行都指向同一个提交时，这个提交所属的 PR 就是答案。
   PR 编号用两个独立来源交叉核对，**一致才保留**：
   - 本地 git：squash 合并看标题末尾的 `(#123)`；普通合并找**真正把它带进来的** "Merge pull request #123"
     （merge 的第一父提交还不包含它，才算是这个 merge 带进来的）
   - GitHub：`GET /repos/{o}/{r}/commits/{sha}/pulls` 里已合并的 PR
   - 只用本地 git 时，第一版 42 条里有 6 条答案是错的：4 条老提交根本没有 PR（之后第一个 merge 是无关的 PR）、
     1 条 rebase 合并（没有 merge 提交）、1 条标题里的 `(#7940)` 其实是 issue 编号
3. **为什么不用自己的 `is_noise_commit` 算答案**：那是拿被测的规则出题，自己考自己。维护者的清单和被测代码互相独立
4. **只保留答案明确的样本**，以下情况丢掉：
   - 落在 docstring 里的行（不是逻辑）
   - 落在 import 语句里的行，包括多行 import 括号里的名字：格式化前它们挤在同一行，是不同 PR 陆续加进去的，
     blame 却全算给最后改这一行的 PR
   - 更一般的同类情况：几行在答案提交里对应**同一个原始行号**（`git blame --porcelain` 给出），说明是格式化把一行拆成了多行
     （列表、元组、函数参数）。拆分本身不一定有歧义，再用 `git log -L n,n:<当时的路径> <sha>` 看那一行的历史：
     只有答案提交自己（新写的一行）就保留；更早还有提交改过它（例如往列表里加 / 删一项）就丢掉。
     第一版基线里 id 3（`__attrs__` 列表）、id 30（扩展名列表）就是这样被误判的。
     只判断"有没有拆分"会把大部分 penetrate 样本也丢掉（black 经常把一个新写的长调用拆成多行），所以要多这一步
   - 答案提交是 merge 提交（解决冲突时产生，不是逻辑的来源）
   - 答案提交的标题像搬代码（move / reorder 等）、改名、机械改写、类型标注、文档、chore（逻辑其实在它之前就有，答案有歧义）
5. **两类样本各一半**：
   - `direct`：普通 blame 就直接指向答案，考"关联 PR、正确引用"
   - `penetrate`：一半以上的行，普通 blame 指向格式化提交，要穿过去才能找到答案，考 v2 的深挖和 v3 的噪声过滤

6. **抽样要稳定**：候选按 `sha1(种子:仓库:文件:起止行)` 排序后依次取，不用 `random.shuffle`。
   改过滤规则后候选池少了几条时，只有那几条的名额由后面的补上，其余样本不变，前后两版评测结果才能对比
   （用 shuffle 时，两版之间只剩 7~8 条相同）

每条样本的字段：`id` `repo` `file` `start` `end` `head`（生成时的 HEAD）`url` `gold_pr` `gold_sha` `gold_title` `kind`。

**注意**：`url` 里带的是生成时的 HEAD。agent 是在本地克隆上 blame 的，跑评测前要确认本地仓库的 HEAD 和 `head` 一致，否则行号会对不上。

## 指标

| 指标 | 含义 |
|---|---|
| Top-1 命中率 | Agent 给出的首要关键 PR 是否正确 |
| Top-3 命中率 | 正确 PR 是否在前三 |
| 检索 Recall@K | 标准答案对应的 issue/PR 是否被召回 |
| 平均深度 | 平均挖几层收敛 |
| 平均成本 | 每次考古的 token 与耗时 |

## 对照组

- Vector-only
- BM25-only
- Hybrid + RRF
- Hybrid + RRF + Rerank

跑完把数字填进 README 和 ADR-0001。

## TODO

- [x] build_dataset.py：自动构造
- [x] run_eval.py：跑评测并出表（`python -m evals.run_eval --mode off --limit 3`）
- [ ] 5 种 retrieval_mode 各跑一遍做对照
- [ ] 失败案例分析：哪类代码考不出来（提示：squash 合并的仓库、
      commit message 只写 "fix bug" 的仓库）
