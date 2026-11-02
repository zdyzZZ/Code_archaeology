# -*- coding: utf-8 -*-
"""Cross-Encoder 重排：对 RRF 后的前 20 段精挑出最相关的几段。

Bi-Encoder（vector.py）和 Cross-Encoder 的区别（面试必问）：
  - Bi-Encoder：问题、文档**分别**编码成向量再比相似度。文档向量能提前算好，所以快，能处理大量文档；
    但编码时问题和文档互相看不见，精度有限
  - Cross-Encoder：把"问题 + 文档"**拼在一起**输入模型，模型逐字对照两者后直接给出一个相关性分数。
    精度高，但每个（问题，文档）对都要完整跑一遍模型，不能提前算

所以 Cross-Encoder 只能放在第二阶段：先用便宜的方法（BM25 + 向量 + RRF）从几百段里捞出 20 段，
再用贵的方法在这 20 段里挑。全量重排几百段会慢得多。

模型：BAAI/bge-reranker-base（中英文都行，约 1.1GB）。
  cross-encoder/ms-marco-MiniLM-L-6-v2 小得多，但只懂英文，用户的中文问题它处理不了。
模型一次最多看 512 个 token，所以 chunking.py 把单块限制在 800 字以内。
"""
import threading

from app.config import settings
from app.rag.corpus import Document

_model = None
_lock = threading.Lock()


def get_model():
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                from sentence_transformers import CrossEncoder
                print('[rerank] 加载重排模型 %s ...' % settings.rerank_model)
                _model = CrossEncoder(settings.rerank_model, max_length=512)
    return _model


def rerank(query: str, docs: list[Document], top_k: int = 8) -> list[tuple[Document, float]]:
    """返回 [(文档, 相关性分数)]，从高到低。"""
    if not docs:
        return []
    scores = get_model().predict([(query, d.text) for d in docs], show_progress_bar=False)
    ranked = sorted(zip(docs, scores), key=lambda x: float(x[1]), reverse=True)
    return [(d, float(s)) for d, s in ranked[:top_k]]
