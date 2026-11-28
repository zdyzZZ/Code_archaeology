# -*- coding: utf-8 -*-
"""离线检索实验：不调 LLM，只看"证据原文能不能进入检索结果的前 k 段"。

每条带理由标注的样本，按一次完整评测里 agent 实际收集到的材料（提交、PR / issue 编号，从结果文件存下的
material 里解析）重建语料，再用 app.rag.pipeline.search 在不同配置下检索：

    模式   bm25 / vector / hybrid / hybrid_rerank(pool=rrf) / hybrid_rerank(pool=union)
    top_k  8 / 10 / 12（取同一次检索结果的前 k 段，排序对 k 是前缀一致的）

和完整评测的差别（所以数字只用来比较配置，绝对值以完整评测为准）：
  - 查询少了 assess 写的 missing：那是 LLM 生成的，每次运行都不一样，这里只用"问题 + 目标代码"
  - 语料用的是参考结果文件那一次运行收集到的材料
  - 完整评测的"证据进材料"还包括提交说明等非检索部分，这里只看检索结果

运行（在项目根目录）：
    python -m evals.retrieval_sweep                              # 默认用 hybrid_rerank-q 的材料
    python -m evals.retrieval_sweep --ref bm25-q --ks 8,10,12,15
结果写到 evals/results/retrieval_sweep.md。
"""
import argparse
import asyncio
import json
import re
import time
from collections import defaultdict
from pathlib import Path

from app.config import settings
from app.git.repo import run
from app.github.client import get_comments, get_issue
from app.rag.corpus import build_documents
from app.rag.pipeline import search
from evals.reasons import any_quote_found, load_reasons

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / 'results'
CONFIGS = [('bm25', 'rrf'), ('vector', 'rrf'), ('hybrid', 'rrf'), ('hybrid_rerank', 'rrf'), ('hybrid_rerank', 'union')]


def config_name(mode: str, pool: str) -> str:
    return '%s(pool=%s)' % (mode, pool) if mode == 'hybrid_rerank' else mode


def rebuild_corpus(record: dict) -> list:
    """按结果文件里存下的 material 重建 retrieve 节点当时的语料。"""
    owner, name = record['repo'].split('/')
    repo = settings.repos_dir / record['repo']
    material = record['material']
    numbers = [int(n) for n in re.findall(r'^#### #(\d+) \((?:PR|issue)\)', material, re.M)]
    shas = re.findall(r'^### ([0-9a-f]{8}) ', material, re.M)
    commits = [{'sha': run(['git', 'rev-parse', s], cwd=repo).strip(),
                'message': run(['git', 'log', '-1', '--format=%B', s], cwd=repo)} for s in shas]
    issues, bodies, comments = [], {}, {}
    for n in numbers:
        d = asyncio.run(get_issue(owner, name, n))
        is_pr = 'pull_request' in d
        issues.append({'number': n, 'title': d['title'], 'is_pr': is_pr, 'url': d['html_url']})
        bodies[n] = d.get('body') or ''
        comments[n] = get_comments(owner, name, n, is_pr)
    return build_documents(commits, issues, bodies, comments)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ref', default='hybrid_rerank-q', help='用哪个结果文件里存的材料重建语料')
    ap.add_argument('--ks', default='8,10,12')
    ap.add_argument('--ids', help='逗号分隔，只跑这些样本')
    args = ap.parse_args()
    ks = sorted(int(k) for k in args.ks.split(','))

    reasons = {i: r for i, r in load_reasons().items() if r['reviewed'] and r['has_reason'] and r['evidence']}
    records = {}
    for line in (RESULTS / ('%s.jsonl' % args.ref)).read_text(encoding='utf-8').splitlines():
        r = json.loads(line)
        if r['id'] in reasons and 'material' in r and not r.get('error'):
            records[r['id']] = r
    if args.ids:
        records = {i: r for i, r in records.items() if i in {int(x) for x in args.ids.split(',')}}

    hits: dict[tuple, set[int]] = defaultdict(set)    # (配置, k) -> 命中的样本 id
    seconds: dict[str, float] = defaultdict(float)
    for n, (i, rec) in enumerate(sorted(records.items()), 1):
        ann = reasons[i]
        docs = rebuild_corpus(rec)
        code = '\n'.join(re.sub(r'^L\d+\s+', '', l) for l in ann['code'].splitlines())
        query = ann['question'] + '\n' + code
        line = []
        for mode, pool in CONFIGS:
            t = time.time()
            res = search(query, docs, mode, top_k=max(ks), candidates=settings.retrieve_candidates, pool=pool)
            seconds[config_name(mode, pool)] += time.time() - t
            for k in ks:
                if any_quote_found(ann['evidence'], '\n\n'.join(r['text'] for r in res[:k])):
                    hits[(config_name(mode, pool), k)].add(i)
            line.append('%s=%s' % (config_name(mode, pool), ''.join(
                'Y' if i in hits[(config_name(mode, pool), k)] else '.' for k in ks)))
        print('[%d/%d] id=%-2d %-8s 语料 %3d 段  %s' % (n, len(records), i, ann['location'], len(docs), '  '.join(line)))

    total = len(records)
    comments = {i for i in records if reasons[i]['location'] == 'comments'}
    out = ['# 离线检索实验：证据进入检索前 k 段', '',
           '材料来源：`%s`；查询 = 问题 + 目标代码（不含 missing）；%d 条样本，其中理由在评论里 %d 条。' % (
               args.ref, total, len(comments)), '',
           '| 配置 | ' + ' | '.join('前 %d 段' % k for k in ks) + ' | 评论类（前 %d 段） | 每条秒数 |' % ks[0],
           '|---|' + '---|' * len(ks) + '---|---|']
    for mode, pool in CONFIGS:
        name = config_name(mode, pool)
        cells = ['%d/%d (%.0f%%)' % (len(hits[(name, k)]), total, 100 * len(hits[(name, k)]) / total) for k in ks]
        c = len(hits[(name, ks[0])] & comments)
        out.append('| `%s` | %s | %d/%d | %.1f |' % (name, ' | '.join(cells), c, len(comments), seconds[name] / total))
    base, new = hits[('hybrid_rerank(pool=rrf)', ks[0])], hits[('hybrid_rerank(pool=union)', ks[0])]
    out += ['', '前 %d 段，`pool=union` 相对 `pool=rrf`：多找到 %s，少找到 %s。' % (ks[0], sorted(new - base), sorted(base - new))]
    never = sorted(set(records) - set().union(*hits.values()))
    out += ['所有配置都没进前 %d 段：%s' % (ks[-1], never)]
    text = '\n'.join(out) + '\n'
    (RESULTS / 'retrieval_sweep.md').write_text(text, encoding='utf-8')
    print('\n' + text)


if __name__ == '__main__':
    main()
