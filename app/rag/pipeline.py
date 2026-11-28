# -*- coding: utf-8 -*-
"""把四个阶段按 retrieval_mode 串起来。

    全部材料 ─①召回─> 各自 Top-20 ─②融合─> Top-20 ─③重排─> Top-8
             BM25 + 向量              RRF          Cross-Encoder

各模式：
    bm25 / vector    只用一路召回，取前 top_k
    hybrid           两路召回 + RRF，取前 top_k
    hybrid_rerank    两路召回 + 重排，取前 top_k。重排看哪些候选由 pool 决定：
                       rrf    RRF 融合后的前 candidates 段（默认）
                       union  两路各自前 candidates 段的并集（最多 2 × candidates 段）
                     union 的理由：只在一路里排得靠前的段，RRF 会把它排到两路都中等的段后面，
                     截掉之后重排根本看不到它（评测 id 30：向量第 18、BM25 第 48，进不了 RRF 前 20）。
                     既然重排会重新打分，就不必先用 RRF 砍候选

返回的每一条带 found_by，记录它在每一路里排第几——评测时分析"谁找到的"就靠它。
"""
from app.rag.bm25 import BM25Index
from app.rag.corpus import Document
from app.rag.fusion import rrf


def search(query: str, docs: list[Document], mode: str, top_k: int = 8, candidates: int = 20,
           pool: str = 'rrf') -> list[dict]:
    if not docs or not query.strip() or mode == 'off':
        return []
    by_id = {d.id: d for d in docs}
    found_by: dict[str, dict] = {d.id: {} for d in docs}

    lists = []
    if mode in ('bm25', 'hybrid', 'hybrid_rerank'):
        bm25_ids = BM25Index(docs).search(query, candidates)
        lists.append(bm25_ids)
        for rank, i in enumerate(bm25_ids, 1):
            found_by[i]['bm25'] = rank
    if mode in ('vector', 'hybrid', 'hybrid_rerank'):
        from app.rag.vector import VectorIndex      # 用到时再导入，bm25 模式不加载 torch
        vec_ids = VectorIndex(docs).search(query, candidates)
        lists.append(vec_ids)
        for rank, i in enumerate(vec_ids, 1):
            found_by[i]['vector'] = rank

    if len(lists) == 1:
        ids = lists[0]
    elif mode == 'hybrid_rerank' and pool == 'union':
        ids = rrf(lists)                     # 并集；按 RRF 排序只是为了顺序稳定，重排会重新打分
    else:
        ids = rrf(lists, top_k=candidates)

    scores: dict[str, float] = {}
    if mode == 'hybrid_rerank':
        from app.rag.rerank import rerank
        ranked = rerank(query, [by_id[i] for i in ids], top_k)
        ids = [d.id for d, _ in ranked]
        scores = {d.id: s for d, s in ranked}

    out = []
    for i in ids[:top_k]:
        d = by_id[i]
        out.append({'id': d.id, 'kind': d.kind, 'source': d.source, 'text': d.text,
                    'number': d.meta.get('number'), 'url': d.meta.get('url', ''),
                    'found_by': found_by[i], 'rerank_score': scores.get(i)})
    return out
