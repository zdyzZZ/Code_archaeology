# -*- coding: utf-8 -*-
"""BM25：关键词检索。擅长精确的标识符：函数名、参数名、#1234、提交 sha。

原理（面试要能讲）：
  BM25 是 TF-IDF 的改进版，对每个查询词算一个分再相加：
    - IDF：这个词在多少篇文档里出现过，越少见越重要（"the" 不值钱，"ca_cert_dir" 很值钱）
    - TF：在这篇文档里出现几次，但有饱和——出现 10 次不会比出现 2 次重要 5 倍（参数 k1 控制）
    - 长度惩罚：长文档天然包含更多词，要打折（参数 b 控制）

为什么用 BM25Plus 而不是最常见的 BM25Okapi：
  我们每次的语料只有几十到几百段。语料很小时，BM25Okapi 的 IDF 会变成负数——
  实测 2 篇文档都含 proxy，查 "proxy windows"，Okapi 给两篇都是 -0.134，分不出谁更相关；
  BM25Plus 的 IDF 永远为正，同样的情况给出 1.91 和 3.008，含 windows 的那篇排在前面。
  代价：BM25Plus 会给"一个查询词都不包含"的文档也打一个基础分，所以 search() 里要先过滤掉这些文档。

分词决定召回质量，见 tokenize()。
"""
import re

from rank_bm25 import BM25Plus

from app.rag.corpus import Document

# 英文里没有区分度的词。中文问题这里匹配不上英文材料，跨语言要靠向量检索
STOPWORDS = {
    'a', 'an', 'the', 'and', 'or', 'but', 'if', 'then', 'else', 'of', 'to', 'in', 'on', 'at', 'by', 'for',
    'with', 'from', 'as', 'is', 'are', 'was', 'were', 'be', 'been', 'it', 'its', 'this', 'that', 'these',
    'those', 'we', 'you', 'i', 'he', 'she', 'they', 'not', 'no', 'so', 'do', 'does', 'did', 'can', 'will',
    'would', 'should', 'could', 'have', 'has', 'had', 'there', 'here', 'what', 'which', 'when', 'how',
    'self', 'none', 'true', 'false', 'return', 'def',
}

# 一个 token 可能是：#1234 / 提交 sha（7-40 位十六进制且含数字）/ 标识符 / 数字 / 一段中文
_TOKEN = re.compile(r'#\d+|\b(?=[0-9a-f]*\d)[0-9a-f]{7,40}\b|[A-Za-z_][A-Za-z0-9_]*|\d+|[一-鿿]+')
_CAMEL = re.compile(r'[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+')


def _split_identifier(word: str) -> list[str]:
    """proxy_bypass_environment -> proxy bypass environment；caCertDir -> ca cert dir。"""
    parts = []
    for piece in word.split('_'):
        parts += _CAMEL.findall(piece)
    return [p.lower() for p in parts if p]


def tokenize(text: str) -> list[str]:
    """分词规则：
      - 全部小写
      - 标识符既保留整体（精确匹配加分），也拆成小词（部分匹配也能召回）：
        'proxy_bypass_environment' -> ['proxy_bypass_environment', 'proxy', 'bypass', 'environment']
      - '#1234' 和 sha 保持完整
      - 中文按两个字一组切（没装 jieba 时的简单做法）
      - 去掉停用词和单个字母
    """
    tokens = []
    for raw in _TOKEN.findall(text or ''):
        if raw.startswith('#') or re.fullmatch(r'[0-9a-f]{7,40}', raw):
            tokens.append(raw.lower())
        elif re.fullmatch(r'[一-鿿]+', raw):
            tokens += [raw[i:i + 2] for i in range(max(1, len(raw) - 1))]
        else:
            low = raw.lower()
            parts = _split_identifier(raw)
            if len(parts) > 1:
                tokens.append(low)
            tokens += parts or [low]
    return [t for t in tokens if t not in STOPWORDS and len(t) > 1]


class BM25Index:
    def __init__(self, docs: list[Document]):
        self.docs = docs
        self.tokens = [tokenize(d.text) for d in docs]
        # 空语料时 rank_bm25 会除以零（ZeroDivisionError），所以不建索引
        self.bm25 = BM25Plus(self.tokens) if docs else None

    def search(self, query: str, top_k: int = 20) -> list[str]:
        """返回 doc id 列表，按相关性从高到低。RRF 只需要排名，所以不返回分数。"""
        q = tokenize(query)
        if not self.bm25 or not q:
            return []
        scores = self.bm25.get_scores(q)
        q_set = set(q)
        ranked = sorted(
            (i for i in range(len(self.docs)) if q_set & set(self.tokens[i])),   # 至少命中一个词
            key=lambda i: scores[i], reverse=True)
        return [self.docs[i].id for i in ranked[:top_k]]
