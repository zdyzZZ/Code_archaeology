# -*- coding: utf-8 -*-
"""跑评测：逐条运行 evals/dataset.jsonl，算命中率，输出 markdown 表。

运行（在项目根目录）：
    python -m evals.run_eval --limit 3            # 先试 3 条
    python -m evals.run_eval                      # 全部 42 条，retrieval_mode 默认 off（基线）
    python -m evals.run_eval --mode hybrid_rerank # 换一种检索配置
    python -m evals.run_eval --summary            # 不跑，只按已有结果重新出表

结果：
    evals/results/<mode>.jsonl   每条样本一行，跑完一条立刻写入；再次运行会跳过已有的 id
    evals/results/<mode>.md      汇总表

指标：
    Top-1 / Top-3     gold_pr 是否是 key_prs 的第一个 / 在前三个里
    挖到提交          gold_sha 是否出现在 commits 里（考 blame + 深挖 + 噪声过滤）
    材料含 PR         gold_pr 是否出现在拉到的 issue/PR 里（考 link_context）
    Recall@5          检索结果前 5 段里有没有来自 gold_pr 的段（retrieval_mode=off 时不算）

没命中的样本按"卡在哪一步"分三类，用来区分检索错误和生成错误：
    没挖到提交 → 材料里没有 PR → 材料里有但没选对
"""
import argparse
import json
import time
import traceback
import uuid
from collections import defaultdict
from pathlib import Path

from langgraph.types import Command

from app.config import settings
from app.git.repo import run as git

ROOT = Path(__file__).resolve().parent
DATASET = ROOT / 'dataset.jsonl'
RESULTS_DIR = ROOT / 'results'
MODES = ['off', 'bm25', 'vector', 'hybrid', 'hybrid_rerank']


# ---------- 数据 ----------

def load_dataset(args) -> list[dict]:
    rows = [json.loads(l) for l in DATASET.read_text(encoding='utf-8').splitlines() if l.strip()]
    if args.ids:
        wanted = {int(i) for i in args.ids.split(',')}
        rows = [r for r in rows if r['id'] in wanted]
    if args.repo:
        rows = [r for r in rows if r['repo'] == args.repo]
    if args.kind:
        rows = [r for r in rows if r['kind'] == args.kind]
    if args.limit:
        rows = rows[:args.limit]
    return rows


def load_results(path: Path) -> dict[int, dict]:
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        if line.strip():
            r = json.loads(line)
            out[r['id']] = r          # 同一个 id 出现多次时，后写的覆盖先写的（重跑失败样本）
    return out


def check_heads(samples: list[dict]) -> None:
    """本地克隆的 HEAD 必须和生成样本时一致，否则行号对不上，结果没有意义。"""
    for repo, head in {(s['repo'], s['head']) for s in samples}:
        path = settings.repos_dir / repo
        if not path.exists():
            raise SystemExit('本地没有 %s 的克隆：%s' % (repo, path))
        local = git(['git', 'rev-parse', 'HEAD'], cwd=path).strip()
        if local != head:
            raise SystemExit('%s 本地 HEAD 是 %s，样本要求 %s。先 git checkout %s' % (
                repo, local[:8], head[:8], head[:8]))


def check_github() -> None:
    """link_context 遇到 401 / 403 只会打印"跳过"然后继续，评测会在没有任何 PR 的情况下跑完，
    得到一堆看似正常的 0 分。所以开跑前先确认 token 可用、额度够。"""
    import httpx
    from app.github.client import _headers
    try:
        r = httpx.get('https://api.github.com/rate_limit', headers=_headers(), timeout=20)
    except httpx.HTTPError as e:
        raise SystemExit('连不上 GitHub API（检查网络 / 代理）：%s' % e)
    if r.status_code == 401:
        raise SystemExit('GitHub token 无效（401 Bad credentials）：更新 .env 里的 GITHUB_TOKEN')
    r.raise_for_status()
    core = r.json()['resources']['core']
    print('GitHub API 剩余额度 %d/%d' % (core['remaining'], core['limit']))
    if core['limit'] <= 60:
        raise SystemExit('没有使用 token（匿名额度只有 60/小时）：在 .env 里设置 GITHUB_TOKEN')


# ---------- 跑一条 ----------

def run_one(sample: dict) -> dict:
    from app.agent.graph import GRAPH     # 延迟导入：--summary 不需要加载 graph 和模型

    config = {'configurable': {'thread_id': uuid.uuid4().hex}, 'recursion_limit': 100}
    start = time.time()
    GRAPH.invoke({'url': sample['url'], 'question': '', 'max_depth': settings.max_depth,
                  'language': 'zh'}, config=config)
    # 到深度上限还不够时会停在 interrupt_llm；评测没人点按钮，一律选"就到这里"
    interrupts = 0
    while GRAPH.get_state(config).next:
        interrupts += 1
        GRAPH.invoke(Command(resume=False), config=config)
    state = GRAPH.get_state(config).values
    seconds = time.time() - start

    gold_pr, gold_sha = sample['gold_pr'], sample['gold_sha']
    key_prs = state.get('key_prs') or []
    retrieved = state.get('retrieved') or []
    return {
        'key_prs': key_prs,
        'top1': key_prs[:1] == [gold_pr],
        'top3': gold_pr in key_prs[:3],
        'sha_found': any(c['sha'].startswith(gold_sha) or gold_sha.startswith(c['sha'])
                         for c in state.get('commits', [])),
        'pr_in_material': any(i['number'] == gold_pr for i in state.get('issues', [])),
        'recall5': (any(r.get('number') == gold_pr for r in retrieved[:5])
                    if settings.retrieval_mode != 'off' else None),
        'depth': state.get('depth', 0),
        'stop_reason': state.get('stop_reason'),
        'interrupts': interrupts,
        'commits': len(state.get('commits', [])),
        'issues': len(state.get('issues', [])),
        'skipped': len(state.get('skipped', [])),
        'seconds': round(seconds, 1),
        'report': state.get('report', ''),
    }


def failure_stage(r: dict) -> str | None:
    if r.get('error'):
        return '运行出错'
    if r['top3']:
        return None
    if not r['sha_found']:
        return '没挖到提交'
    if not r['pr_in_material']:
        return '材料里没有 PR'
    return '材料里有但没选对'


# ---------- 汇总 ----------

def _pct(hits: int, n: int) -> str:
    return '%d/%d (%.0f%%)' % (hits, n, 100 * hits / n) if n else '-'


def _row(name: str, rs: list[dict]) -> str:
    ok = [r for r in rs if not r.get('error')]
    n = len(rs)
    cells = [
        name, str(n),
        _pct(sum(r.get('top1', False) for r in rs), n),
        _pct(sum(r.get('top3', False) for r in rs), n),
        _pct(sum(r.get('sha_found', False) for r in rs), n),
        _pct(sum(r.get('pr_in_material', False) for r in rs), n),
    ]
    rec = [r['recall5'] for r in ok if r.get('recall5') is not None]
    cells.append(_pct(sum(rec), len(rec)) if rec else '-')
    cells.append('%.2f' % (sum(r['depth'] for r in ok) / len(ok)) if ok else '-')
    cells.append('%.0f' % (sum(r['seconds'] for r in ok) / len(ok)) if ok else '-')
    cells.append(str(n - len(ok)))
    return '| ' + ' | '.join(cells) + ' |'


def _brief(r: dict) -> str:
    """表格里"key_prs"那一格：出错时放错误的第一行，否则放 key_prs（可能是空列表）。"""
    if r.get('error'):
        return r['error'].splitlines()[0][:80].replace('|', '/')
    return str(r.get('key_prs'))


def summarize(mode: str, results: list[dict]) -> str:
    header = ('| 分组 | 样本 | Top-1 | Top-3 | 挖到提交 | 材料含 PR | Recall@5 | 平均深度 | 平均秒数 | 出错 |\n'
              '|---|---|---|---|---|---|---|---|---|---|')
    lines = ['# 评测结果：retrieval_mode = %s' % mode, '', header, _row('全部', results)]
    for key in ('kind', 'repo'):
        groups = defaultdict(list)
        for r in results:
            groups[r[key]].append(r)
        lines += [_row('%s=%s' % (key, k), v) for k, v in sorted(groups.items())]

    misses = [(r, failure_stage(r)) for r in results if failure_stage(r)]
    if misses:
        counts = defaultdict(int)
        for _, stage in misses:
            counts[stage] += 1
        lines += ['', '## 没命中 Top-3 的样本（%d 条）' % len(misses), '',
                  '卡在哪一步：' + '，'.join('%s %d' % kv for kv in counts.items()), '',
                  '| id | kind | 仓库 | 文件 | 标准答案 | key_prs | 卡在 |', '|---|---|---|---|---|---|---|']
        for r, stage in sorted(misses, key=lambda x: x[0]['id']):
            lines.append('| %d | %s | %s | %s#L%d-L%d | #%d %s | %s | %s |' % (
                r['id'], r['kind'], r['repo'], r['file'], r['start'], r['end'],
                r['gold_pr'], r['gold_title'][:40],
                _brief(r), stage))
    return '\n'.join(lines) + '\n'


# ---------- 入口 ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--mode', choices=MODES, default='off', help='检索配置，默认 off（v4 的截断方式，当基线）')
    ap.add_argument('--limit', type=int, help='只跑前 N 条')
    ap.add_argument('--ids', help='只跑这些 id，逗号分隔')
    ap.add_argument('--repo', help='只跑某个仓库，例如 psf/requests')
    ap.add_argument('--kind', choices=['direct', 'penetrate'])
    ap.add_argument('--rerun', action='store_true', help='已有结果的样本也重跑（默认只重跑出错的）')
    ap.add_argument('--summary', action='store_true', help='不跑，只按已有结果出表')
    args = ap.parse_args()

    settings.retrieval_mode = args.mode
    RESULTS_DIR.mkdir(exist_ok=True)
    out_jsonl = RESULTS_DIR / ('%s.jsonl' % args.mode)
    samples = load_dataset(args)
    done = load_results(out_jsonl)

    if not args.summary:
        check_heads(samples)
        check_github()
        todo = [s for s in samples
                if args.rerun or s['id'] not in done or done[s['id']].get('error')]
        print('retrieval_mode=%s，共 %d 条，已有结果 %d 条，本次跑 %d 条' % (
            args.mode, len(samples), len(samples) - len(todo), len(todo)))
        for n, sample in enumerate(todo, 1):
            print('\n' + '=' * 80)
            print('[%d/%d] id=%d %s %s#L%d-L%d  标准答案 #%d' % (
                n, len(todo), sample['id'], sample['kind'], sample['file'],
                sample['start'], sample['end'], sample['gold_pr']))
            try:
                result = run_one(sample)
            except Exception as e:     # 一条失败不影响其它样本
                traceback.print_exc()
                result = {'error': '%s: %s' % (type(e).__name__, e)}
            record = {**sample, 'mode': args.mode, **result}
            with out_jsonl.open('a', encoding='utf-8') as f:
                f.write(json.dumps(record, ensure_ascii=False) + '\n')
            done[sample['id']] = record
            print('-> key_prs=%s top1=%s top3=%s 卡在=%s' % (
                record.get('key_prs'), record.get('top1'), record.get('top3'), failure_stage(record)))

    results = [done[s['id']] for s in samples if s['id'] in done]
    if not results:
        raise SystemExit('还没有结果：%s' % out_jsonl)
    table = summarize(args.mode, results)
    (RESULTS_DIR / ('%s.md' % args.mode)).write_text(table, encoding='utf-8')
    print('\n' + table)


if __name__ == '__main__':
    main()
