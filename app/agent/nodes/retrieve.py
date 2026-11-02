# -*- coding: utf-8 -*-
"""检索：在 narrate 之前，从本次收集的全部材料里挑出最相关的几段。

位置：assess 判断"够了"（或用户选"就到这里"）之后、narrate 之前，只运行一次。

为什么需要它：之前的做法是把 PR 正文按位置截断（body[:4000]），评论根本不拉。
  - PR #6667 的正文正好在关键处被截断过
  - 模型多次说"缺 PR 里的讨论"，而评论往往才是真正的理由
现在把正文、评论、提交说明都切成段，按相关性挑 top_k 段交给 narrate。

查询由三部分组成，这也是本项目必须用 Hybrid 的原因：
  - 目标代码：满是 proxy_bypass_environment、ca_cert_dir 这种标识符 → BM25 擅长
  - 用户问题、assess 的 missing：自然语言，而且常常是中文 → 向量（多语言模型）擅长
"""
import asyncio

import httpx

from app.agent.state import ArchaeologyState
from app.config import settings
from app.github.client import get_comments, get_issue
from app.rag.corpus import build_documents
from app.rag.pipeline import search


def build_query(state: ArchaeologyState) -> str:
    code = '\n'.join(l.get('code', '') for l in state.get('blame_lines', []))
    parts = [state.get('question') or '', state.get('missing') or '', code]
    return '\n'.join(p for p in parts if p.strip())


def _collect(state: ArchaeologyState) -> tuple[dict[int, str], dict[int, list[dict]]]:
    """拿每个 issue / PR 的完整正文和全部评论。都走 GitHub 缓存，第二次运行不发请求。"""
    owner, repo = state['owner'], state['repo']
    bodies, comments = {}, {}
    for issue in state.get('issues', []):
        n = issue['number']
        try:
            bodies[n] = asyncio.run(get_issue(owner, repo, n)).get('body') or ''
            comments[n] = get_comments(owner, repo, n, issue.get('is_pr', False))
        except httpx.HTTPStatusError as e:
            print('[retrieve] 拉取 #%d 的正文或评论失败，跳过: %s' % (n, e.response.status_code))
    return bodies, comments


def retrieve(state: ArchaeologyState) -> dict:
    mode = settings.retrieval_mode
    if mode == 'off':
        print('[retrieve] retrieval_mode=off，不检索，narrate 用截断后的正文')
        return {'retrieved': [], 'retrieval_stats': {'mode': mode}}

    bodies, comments = _collect(state)
    docs = build_documents(state.get('commits', []), state.get('issues', []), bodies, comments)
    query = build_query(state)
    results = search(query, docs, mode, top_k=settings.retrieve_top_k, candidates=settings.retrieve_candidates)

    stats = {'mode': mode, 'corpus': len(docs), 'comments': sum(len(c) for c in comments.values()),
             'selected': len(results)}
    print('[retrieve] 模式=%s，%d 个 issue/PR，%d 条评论 -> 语料 %d 段 -> 选出 %d 段' % (
        mode, len(bodies), stats['comments'], len(docs), len(results)))
    for r in results:
        print('    %-36s found_by=%s' % (r['source'][:36], r['found_by']))
    return {'retrieved': results, 'retrieval_stats': stats}
