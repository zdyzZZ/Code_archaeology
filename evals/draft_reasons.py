# -*- coding: utf-8 -*-
"""起草理由标注：每条样本让 LLM 读完标准答案 PR 的全部材料，写出问题、理由和证据摘录。

起草只是草稿，**必须人工审核**（把 reviewed 改成 true）。agent 作答、评委打分用的也是同一个模型，
不经人工确认就等于自己出题、自己答、自己判。

防编造：证据摘录必须能在对应来源的原文里找到（evals.reasons.quote_found），找不到的直接丢掉并写进 note。

运行（在项目根目录）：
    python -m evals.draft_reasons --limit 3      # 先起草 3 条看看
    python -m evals.draft_reasons                # 全部；已审核的不会被覆盖，已有草稿默认跳过
    python -m evals.draft_reasons --ids 5,7 --redo   # 重新起草某几条（已审核的仍然不动）

结果写进 evals/reasons.json，每起草一条就保存一次。
"""
import argparse
import asyncio
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from app.agent.llm import get_llm
from app.config import settings
from app.git.repo import run
from app.github.client import extract_refs, get_comments, get_issue
from evals.reasons import load_reasons, quote_found, save_reasons

ROOT = Path(__file__).resolve().parent
DATASET = ROOT / 'dataset.jsonl'
PROMPT = (ROOT / 'prompts' / 'draft_reason.md').read_text(encoding='utf-8')

MAX_COMMENT = 2000      # 单条评论最多给模型看多少字
MAX_MATERIAL = 60000    # 整份材料的上限；超过时后面的评论不再加入
MAX_ISSUES = 3          # PR 引用的 issue 最多拉几个


class Evidence(BaseModel):
    source: str = Field(description='材料里方括号中的来源标签，例如 "PR #1234 正文"、"C7"')
    quote: str = Field(description='从该来源逐字复制的英文原文，40~300 个字符')


class Draft(BaseModel):
    has_reason: bool
    question: str = Field(description='中文问题，不包含答案，不提 PR / issue 编号')
    reason: str = Field(description='真正的理由，1~2 句中文')
    location: Literal['commit', 'pr_body', 'issue', 'comments']
    evidence: list[Evidence]


def target_code(sample: dict) -> str:
    repo = settings.repos_dir / sample['repo']
    lines = run(['git', 'show', 'HEAD:' + sample['file']], cwd=repo).splitlines()
    return '\n'.join('L%d  %s' % (i, lines[i - 1]) for i in range(sample['start'], sample['end'] + 1))


def collect(sample: dict) -> tuple[str, dict[str, dict]]:
    """拼给模型看的材料，同时返回 {来源标签: {url, text}}，用来核对摘录。"""
    owner, name = sample['repo'].split('/')
    repo = settings.repos_dir / sample['repo']
    sources: dict[str, dict] = {}
    parts = ['## 目标代码（%s）\n%s' % (sample['file'], target_code(sample))]

    message = run(['git', 'log', '-1', '--format=%B', sample['gold_sha']], cwd=repo).strip()
    sources['提交说明'] = {'url': '', 'text': message}
    parts.append('## [提交说明] %s\n%s' % (sample['gold_sha'][:8], message))

    pr = asyncio.run(get_issue(owner, name, sample['gold_pr']))
    body = pr.get('body') or ''
    label = 'PR #%d 正文' % sample['gold_pr']
    sources[label] = {'url': pr.get('html_url', ''), 'text': body}
    parts.append('## [%s] %s\n%s' % (label, pr.get('title', ''), body or '（空）'))

    threads = [('PR #%d' % sample['gold_pr'], get_comments(owner, name, sample['gold_pr'], True))]
    refs = [n for n in extract_refs(body + '\n' + message, owner, name) if n != sample['gold_pr']]
    for n in refs[:MAX_ISSUES]:
        try:
            issue = asyncio.run(get_issue(owner, name, n))
        except Exception as e:      # 引用的编号可能不存在或无权访问，跳过即可
            print('    拉取 #%d 失败，跳过：%s' % (n, e))
            continue
        label = 'issue #%d 正文' % n if 'pull_request' not in issue else 'PR #%d 正文' % n
        sources[label] = {'url': issue.get('html_url', ''), 'text': issue.get('body') or ''}
        parts.append('## [%s] %s\n%s' % (label, issue.get('title', ''), issue.get('body') or '（空）'))
        threads.append(('#%d' % n, get_comments(owner, name, n, 'pull_request' in issue)))

    size = sum(len(p) for p in parts)
    k = 0
    for where, comments in threads:
        for c in comments:
            k += 1
            label = 'C%d' % k
            text = c['body'][:MAX_COMMENT]
            block = '## [%s] %s 的 %s · %s%s\n%s' % (
                label, where, c['kind'], c['author'], ('（%s）' % c['path']) if c.get('path') else '', text)
            if size + len(block) > MAX_MATERIAL:
                parts.append('（后面还有评论，超出长度上限，未列出）')
                return '\n\n'.join(parts), sources
            sources[label] = {'url': c['url'], 'text': text}
            parts.append(block)
            size += len(block)
    return '\n\n'.join(parts), sources


def match_source(label: str, sources: dict[str, dict]) -> str | None:
    """模型写的来源标签常常多带一点东西（"提交说明 9a8a826f"、"[C7] PR #12 的 comment"），按前缀 / 包含兜底。"""
    label = label.strip().strip('[]').strip()
    if label in sources:
        return label
    for key in sorted(sources, key=len, reverse=True):     # 长的先比，免得 "C1" 抢走 "C12"
        if label.startswith(key) or ('[%s]' % key) in label:
            return key
    return None


def draft_one(sample: dict) -> dict:
    material, sources = collect(sample)
    llm = get_llm().with_structured_output(Draft)
    d: Draft = llm.invoke([('system', PROMPT), ('human', material)])

    evidence, dropped = [], []
    for e in d.evidence:
        key = match_source(e.source, sources)
        if key and quote_found(e.quote, sources[key]['text']):
            evidence.append({'source': key, 'url': sources[key]['url'], 'quote': e.quote})
        else:
            dropped.append(e.source)
    notes = []
    if dropped:
        notes.append('丢掉了 %d 条在原文里找不到的摘录（来源 %s）' % (len(dropped), ', '.join(dropped)))
    if d.has_reason and not evidence:
        notes.append('有理由但没有可用的证据摘录，需要人工补')
    return {
        'id': sample['id'], 'repo': sample['repo'], 'file': sample['file'],
        'start': sample['start'], 'end': sample['end'], 'gold_pr': sample['gold_pr'],
        'code': target_code(sample),
        'has_reason': d.has_reason, 'question': d.question, 'reason': d.reason,
        'location': d.location, 'evidence': evidence,
        'reviewed': False, 'note': '；'.join(notes),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int)
    ap.add_argument('--ids', help='逗号分隔')
    ap.add_argument('--redo', action='store_true', help='已有草稿也重新起草（已审核的不动）')
    args = ap.parse_args()

    samples = [json.loads(l) for l in DATASET.read_text(encoding='utf-8').splitlines() if l.strip()]
    if args.ids:
        wanted = {int(i) for i in args.ids.split(',')}
        samples = [s for s in samples if s['id'] in wanted]
    reasons = load_reasons()
    todo = [s for s in samples
            if not reasons.get(s['id'], {}).get('reviewed') and (args.redo or s['id'] not in reasons)]
    if args.limit:
        todo = todo[:args.limit]
    print('共 %d 条样本，已有标注 %d 条，本次起草 %d 条' % (len(samples), len(reasons), len(todo)))

    for n, s in enumerate(todo, 1):
        print('[%d/%d] id=%d #%d %s' % (n, len(todo), s['id'], s['gold_pr'], s['gold_title'][:50]))
        try:
            entry = draft_one(s)
        except Exception as e:
            print('    起草失败：%s: %s' % (type(e).__name__, e))
            continue
        reasons[s['id']] = entry
        save_reasons(reasons)
        print('    has_reason=%s location=%s 证据 %d 条 %s' % (
            entry['has_reason'], entry['location'], len(entry['evidence']), entry['note']))
        print('    问：%s\n    因：%s' % (entry['question'], entry['reason']))


if __name__ == '__main__':
    main()
