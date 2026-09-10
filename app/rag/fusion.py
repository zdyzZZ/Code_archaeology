# -*- coding: utf-8 -*-
"""RRF 融合。

⚠️ 你自己写 —— "必须手写"清单里的一项，而且它很短，没有理由不自己写。

为什么用 RRF 而不是加权分数，见 docs/adr/0001-hybrid-retrieval-and-rrf.md。

公式：
    score(d) = Σ_i  1 / (k + rank_i(d))

  - rank 从 1 开始
  - k 通常取 60
  - 只有排名参与计算，分数完全不用 —— 这就是它免疫量纲问题的原因

面试必问："RRF 的思路是什么？为什么比加权好？"
所以这个函数你必须能白板写出来，并解释 k 的作用。
"""


def rrf(rank_lists: list[list[str]], k: int = 60, top_k: int = 10) -> list[str]:
    """把多路检索的排名列表融合成一个。

    Args:
        rank_lists: 每路一个 doc_id 列表，已按相关性降序排好
        k: 平滑常数
        top_k: 返回前几个

    Returns:
        融合后的 doc_id 列表

    TODO 自己实现（大概 8 行）
    """
    raise NotImplementedError
