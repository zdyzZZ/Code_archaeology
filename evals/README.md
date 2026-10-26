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
   PR 编号只用本地 git 得到：squash 合并看标题末尾的 `(#123)`，普通合并找之后第一个 "Merge pull request #123"
3. **为什么不用自己的 `is_noise_commit` 算答案**：那是拿被测的规则出题，自己考自己。维护者的清单和被测代码互相独立
4. **只保留答案明确的样本**，以下情况丢掉：
   - 落在 docstring 里的行（不是逻辑）
   - 答案提交是 merge 提交（解决冲突时产生，不是逻辑的来源）
   - 答案提交的标题像搬代码、改名、机械改写、类型标注、文档、chore（逻辑其实在它之前就有，答案有歧义）
5. **两类样本各一半**：
   - `direct`：普通 blame 就直接指向答案，考"关联 PR、正确引用"
   - `penetrate`：一半以上的行，普通 blame 指向格式化提交，要穿过去才能找到答案，考 v2 的深挖和 v3 的噪声过滤

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

- [ ] build_dataset.py：自动构造
- [ ] run_eval.py：跑对照并出表
- [ ] 失败案例分析：哪类代码考不出来（提示：squash 合并的仓库、
      commit message 只写 "fix bug" 的仓库）
