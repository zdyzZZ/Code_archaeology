# -*- coding: utf-8 -*-
"""RRF（Reciprocal Rank Fusion）：把多路检索的排名合成一个。

⚠️ 学习计划里"必须手写"的一项，面试会让白板写。读懂之后，关掉这个文件自己重写一遍。

为什么用 RRF 而不是把两路的分数加权相加（见 docs/adr/0001-hybrid-retrieval-and-rrf.md）：
  BM25 的分数没有上界，余弦相似度在 [-1, 1]，两者量纲完全不同；
  换一个查询，分数分布又变了，权重根本没法定。RRF 只用排名、完全不看分数，天然没有这个问题。

公式：
    score(d) = Σ_i  1 / (k + rank_i(d))

  - rank 从 1 开始（第一名的 rank 是 1，不是 0）
  - 只在某一路出现的文档，另一路对它的贡献是 0
  - k 是平滑常数，通常取 60（原论文的经验值）：
    k 越大，第 1 名和第 10 名的分差越小，越看重"被几路同时找到"，而不是"在某一路排得多靠前"

参考：Cormack, Clarke & Buettcher (2009),
《Reciprocal Rank Fusion outperforms Condorcet and individual Rank Learning Methods》
"""


def rrf(rank_lists: list[list[str]], k: int = 60, top_k: int | None = None) -> list[str]:
    """把多路检索的排名列表融合成一个。

    Args:
        rank_lists: 每路一个 doc id 列表，已按相关性从高到低排好
        k: 平滑常数
        top_k: 返回前几个；None 表示全部返回

    Returns:
        融合后的 doc id 列表，从高到低
    """
    scores: dict[str, float] = {}
    for ranking in rank_lists:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    fused = sorted(scores, key=lambda d: scores[d], reverse=True)
    return fused if top_k is None else fused[:top_k]
