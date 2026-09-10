# ADR-0001：检索用 BM25 + 向量 + RRF，而不是单路或加权融合

- 状态：已决定
- 日期：TODO

## 背景

语料异构（见 architecture.md 的对比表）。需要决定检索方案。

## 考虑过的方案

1. **只用向量**：commit message 太短，语义信号稀薄；`#1234`、`FooBar` 这类精确 token 召回差
2. **只用 BM25**：issue 讨论里"这个接口偶发超时"和"响应有时候很慢"匹配不上
3. **加权融合分数**（`a * bm25_score + b * vec_score`）：两路分数**量纲不同**，
   BM25 是无上界的 tf-idf 累加，余弦相似度在 [-1,1]。归一化方式一换，权重就得重调，
   而且不同 query 的分数分布差异很大
4. **RRF**：只用**排名**不用分数，天然免疫量纲问题

## 决定

用 RRF。公式 `score(d) = Σ 1/(k + rank_i(d))`，k 取 60（原论文的经验值）。

## 代价

- 丢掉了分数强弱的信息——排名第 1 和第 2 差距很大时，RRF 看不出来
- 引入了 k 这个超参（虽然实践中不敏感）

## 参考

Cormack, Clarke & Buettcher (2009),
*Reciprocal Rank Fusion outperforms Condorcet and individual Rank Learning Methods*

## TODO

跑完 evals 后把 Hybrid vs Vector-only vs BM25-only 的实测数字填到这里。
