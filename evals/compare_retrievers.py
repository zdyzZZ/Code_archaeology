# -*- coding: utf-8 -*-
"""对比各检索模式：同一组查询，看 BM25 / 向量 / Hybrid / Hybrid+Rerank 各自找到什么。

用来亲眼看"为什么要 Hybrid"——这是路线文件 v5 第 3 步的作业，结果可以记进
docs/adr/0001-hybrid-retrieval-and-rrf.md。

不调用 LLM：只跑 parse_target → blame → filter_noise → link_context（第 0 层）收集材料，
再拉完整正文和评论建语料。GitHub 请求都有缓存，第二次运行不发请求。

运行（在项目根目录）：
    python -m evals.compare_retrievers
    python -m evals.compare_retrievers --url https://github.com/... --query "为什么要这样判断" --query "isdir"
"""
import argparse
import time

from app.agent.nodes.blame import blame
from app.agent.nodes.filter_noise import filter_noise
from app.agent.nodes.link_context import link_context
from app.agent.nodes.parse_target import parse_target
from app.agent.nodes.retrieve import _collect
from app.rag.corpus import build_documents
from app.rag.pipeline import search

DEFAULT_URL = 'https://github.com/psf/requests/blob/main/src/requests/adapters.py#L97-L105'
DEFAULT_QUERIES = [
    'isdir ca_cert_dir',                 # 精确标识符：预期 BM25 好
    '为什么并发时会变慢',                 # 中文、换了说法：预期向量好，BM25 什么都找不到
    '这个 isdir 判断能删吗',              # 混合：两路各对一部分
    'verify=False connection reuse',     # 英文自然语言
]
MODES = ['bm25', 'vector', 'hybrid', 'hybrid_rerank']


def collect_docs(url: str):
    state = {'url': url, 'question': '', 'commits': [], 'issues': [], 'skipped': []}
    for node in (parse_target, blame, filter_noise, link_context):
        state.update(node(state))
    bodies, comments = _collect(state)
    docs = build_documents(state['commits'], state['issues'], bodies, comments)
    print('\n材料：%d 个提交，%d 个 issue/PR，%d 条评论 -> %d 段\n' % (
        len(state['commits']), len(state['issues']), sum(len(c) for c in comments.values()), len(docs)))
    return docs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--url', default=DEFAULT_URL)
    ap.add_argument('--query', action='append', help='可以写多个；不写就用默认的 4 个')
    ap.add_argument('--top', type=int, default=5)
    args = ap.parse_args()

    docs = collect_docs(args.url)
    for q in args.query or DEFAULT_QUERIES:
        print('=' * 100)
        print('查询：%s' % q)
        for mode in MODES:
            t = time.time()
            results = search(q, docs, mode, top_k=args.top)
            print('\n  [%s] %.1fs' % (mode, time.time() - t))
            if not results:
                print('    （什么都没找到）')
            for i, r in enumerate(results, 1):
                text = ' '.join(r['text'].split())[:70]
                print('    %d. %-30s %s' % (i, r['source'][:30], text))
        print()


if __name__ == '__main__':
    main()
