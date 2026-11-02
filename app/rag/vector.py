# -*- coding: utf-8 -*-
"""向量检索：擅长"意思相近但用词不同"，以及跨语言（中文问题找英文讨论）。

原理（面试要能讲）：
  - embedding 模型把一段文字变成一个向量（这里是 384 维），意思相近的文字，向量方向也相近
  - 相似度用余弦相似度；向量先归一化（长度变成 1），余弦相似度就等于点积
  - 这是 Bi-Encoder：问题和文档**分别**编码，文档向量可以提前算好，所以快；
    代价是问题和文档在编码时"互相看不见"，精度不如 Cross-Encoder（见 rerank.py）

为什么不用 Chroma：
  每次考古的语料只有几十到几百段，numpy 一次矩阵乘法就算完了，向量库反而多一层复杂度。
  几百万条、需要持久化和近似最近邻（ANN）时才需要向量库。
  如果以后要换 Chroma，注意两个已验证的坑：集合名不能带 '/'；不传 embeddings 时它会偷偷用自带的英文模型。

模型：intfloat/multilingual-e5-small（多语言、约 470MB）。
  ⚠️ e5 系列要求问题前加 "query: "、文档前加 "passage: "，不加效果会明显变差。
"""
import threading

import numpy as np

from app.config import settings
from app.rag.corpus import Document

_model = None
_lock = threading.Lock()


def get_model():
    """模型加载要好几秒，全进程只加载一次。加锁是因为 FastAPI 下可能有多个请求同时第一次用到它。"""
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                from sentence_transformers import SentenceTransformer   # 导入本身就要几秒，用到时再导入
                print('[vector] 加载 embedding 模型 %s ...' % settings.embedding_model)
                _model = SentenceTransformer(settings.embedding_model)
    return _model


def _prefixes() -> tuple[str, str]:
    if 'e5' in settings.embedding_model.lower():
        return 'query: ', 'passage: '
    return '', ''


def embed(texts: list[str], is_query: bool) -> np.ndarray:
    q_prefix, p_prefix = _prefixes()
    prefix = q_prefix if is_query else p_prefix
    return get_model().encode([prefix + t for t in texts], normalize_embeddings=True,
                              batch_size=32, show_progress_bar=False)


class VectorIndex:
    def __init__(self, docs: list[Document]):
        self.docs = docs
        # 文档向量建索引时一次算好，形状 (文档数, 384)
        self.matrix = embed([d.text for d in docs], is_query=False) if docs else None

    def search(self, query: str, top_k: int = 20) -> list[str]:
        if self.matrix is None or not query.strip():
            return []
        q = embed([query], is_query=True)[0]          # (384,)
        scores = self.matrix @ q                       # 归一化之后，点积就是余弦相似度
        order = np.argsort(-scores)[:top_k]
        return [self.docs[i].id for i in order]
