# -*- coding: utf-8 -*-
"""自动构造评测集。

标准答案怎么来的
----------------
挑的仓库都在根目录维护了 `.git-blame-ignore-revs`：维护者自己列出的格式化提交（black / isort 等）。
`git blame --ignore-revs-file` 跳过这些提交后，每行指向的提交就是"引入这几行当前逻辑"的提交，
它所属的 PR 就是标准答案。

为什么不用我们自己的 is_noise_commit 来算答案：那等于拿被测的规则去出题，自己考自己。
用维护者的清单，答案和被测代码互相独立。

样本类型
--------
- direct：普通 blame 就直接指向答案，考"关联 PR、正确引用"
- penetrate：一半以上的行，普通 blame 指向格式化提交，要穿过去才能找到答案，考 v2 / v3

运行（在项目根目录）
--------------------
    python -m evals.build_dataset                 # 默认每个仓库 14 条，共 42 条，写到 evals/dataset.jsonl
    python -m evals.build_dataset --per-repo 12

第一次运行会克隆 pytest / scrapy，需要几分钟。
"""
import argparse
import ast
import json
import random
import re
from pathlib import Path

from app.git.repo import ensure_cloned, run

# (owner, repo, 源码目录) —— 只取库本身的代码，不取测试和文档
REPOS = [
    ('psf', 'requests', 'src/requests'),
    ('pytest-dev', 'pytest', 'src/_pytest'),
    ('scrapy', 'scrapy', 'scrapy'),
    # pydantic 也有 .git-blame-ignore-revs，但仓库太大（克隆超过 433MB、超过 2 分钟），暂不用
]

IGNORE_FILE = '.git-blame-ignore-revs'
MIN_LINES, MAX_LINES = 4, 15       # 一个样本的行数范围
MIN_CODE_LINES = 3                 # 除去空行、注释、import 后至少要有几行代码

# 标准答案提交的标题命中这些词时丢掉：这类提交会被 blame 当成"引入者"，但逻辑其实在它之前就有了，
# 答案有歧义。只保留答案明确的样本，有歧义的留给失败案例分析。
# 注意这只是出题时的过滤，和被测代码里的 is_noise_commit 互相独立。
AMBIGUOUS_WORDS = re.compile(
    r'\b(move|moved|rename|renamed|relocate|reorganiz|restructur|vendor'      # 搬代码、改名
    r'|format|black|isort|ruff|flake8|pyupgrade|pre-commit|lint|style|whitespace|backslash|f-strings?'
    r'|comprehensions?|clean ?up|typo'  # 机械改写
    r'|type hints?|typing|annotations?|inline types|mypy'                      # 类型标注
    r'|docs?|docstrings?|documentation|document|clarify'                      # 文档
    r'|chore)\b', re.I)

OUT = Path(__file__).resolve().parent / 'dataset.jsonl'


def docstring_lines(source: str) -> set[int]:
    """文件里所有 docstring 占的行号（从 1 开始）。解析失败时返回空集。"""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    lines = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, 'body', [])
            if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], 'value', None), ast.Constant) \
                    and isinstance(body[0].value.value, str):
                lines.update(range(body[0].lineno, body[0].end_lineno + 1))
    return lines


def git(repo: Path, *args: str) -> str:
    return run(['git', *args], cwd=repo, timeout=300)


def blame_shas(repo: Path, path: str, ignore: bool) -> list[tuple[str, str]]:
    """HEAD 上整个文件的 blame，返回 [(sha, 代码), ...]，下标 i 对应第 i+1 行。"""
    args = ['blame', '-w', '--porcelain']
    if ignore:
        args += ['--ignore-revs-file', IGNORE_FILE]
    out = git(repo, *args, 'HEAD', '--', path)
    rows, current = [], None
    for line in out.splitlines():
        if line.startswith('\t'):
            rows.append((current, line[1:]))
        elif re.match(r'^[0-9a-f]{40} ', line):
            current = line[:40]
    return rows


def is_code(line: str) -> bool:
    s = line.strip()
    return bool(s) and not s.startswith(('#', '"""', "'''", 'import ', 'from ', '@'))


class PrFinder:
    """提交 -> PR 编号，只用本地 git，不调 GitHub API（不占额度）。"""

    def __init__(self, repo: Path):
        self.repo = repo
        self.cache: dict[str, tuple[int | None, str]] = {}

    def __call__(self, sha: str) -> tuple[int | None, str]:
        if sha not in self.cache:
            title = git(self.repo, 'log', '-1', '--format=%s', sha).strip()
            # squash 合并：标题末尾带 (#123)
            m = re.search(r'\(#(\d+)\)\s*$', title)
            pr = int(m.group(1)) if m else None
            if pr is None:
                # 普通合并：这个提交之后第一个把它带进主分支的 merge 提交，标题是 "Merge pull request #123 ..."
                merges = git(self.repo, 'log', '--merges', '--ancestry-path', '--reverse',
                             '--format=%s', '%s..HEAD' % sha).splitlines()
                m = re.match(r'Merge pull request #(\d+)', merges[0]) if merges else None
                pr = int(m.group(1)) if m else None
            self.cache[sha] = (pr, title)
        return self.cache[sha]


def candidates(owner: str, name: str, src: str) -> list[dict]:
    repo = ensure_cloned(owner, name)
    head = git(repo, 'rev-parse', 'HEAD').strip()
    ignore_path = repo / IGNORE_FILE
    if not ignore_path.exists():
        print('[%s/%s] 没有 %s，跳过' % (owner, name, IGNORE_FILE))
        return []
    ignored = {l.split()[0] for l in ignore_path.read_text(encoding='utf-8').splitlines()
               if re.match(r'^[0-9a-f]{40}', l)}
    find_pr = PrFinder(repo)
    files = [f for f in git(repo, 'ls-files', src).split()
             if f.endswith('.py') and '/tests/' not in f and not f.split('/')[-1].startswith('test_')]
    print('[%s/%s] HEAD=%s，%d 个文件，%d 个格式化提交' % (owner, name, head[:8], len(files), len(ignored)))

    out = []
    for path in files:
        plain, real = blame_shas(repo, path, False), blame_shas(repo, path, True)
        if len(plain) != len(real):
            continue
        doc = docstring_lines('\n'.join(code for _, code in real))
        i = 0
        while i < len(real):
            j = i
            while j + 1 < len(real) and real[j + 1][0] == real[i][0]:
                j += 1
            sha = real[i][0]
            block = range(i, j + 1)
            if (MIN_LINES <= len(block) <= MAX_LINES and sha not in ignored
                    and not any(k + 1 in doc for k in block)
                    and sum(is_code(real[k][1]) for k in block) >= MIN_CODE_LINES):
                pr, title = find_pr(sha)
                # merge 提交（解决冲突时）也会被 blame 当成"引入者"，但它不是逻辑的来源
                if pr and not AMBIGUOUS_WORDS.search(title) and not title.startswith('Merge '):
                    noisy = sum(plain[k][0] in ignored for k in block)
                    out.append({
                        'repo': '%s/%s' % (owner, name),
                        'file': path,
                        'start': i + 1,
                        'end': j + 1,
                        'head': head,
                        'url': 'https://github.com/%s/%s/blob/%s/%s#L%d-L%d' % (owner, name, head, path, i + 1, j + 1),
                        'gold_pr': pr,
                        'gold_sha': sha,
                        'gold_title': title,
                        'kind': 'penetrate' if noisy * 2 >= len(block) else 'direct',
                    })
            i = j + 1
    print('[%s/%s] 候选 %d 条（penetrate %d）' % (owner, name, len(out), sum(c['kind'] == 'penetrate' for c in out)))
    return out


def pick(cands: list[dict], n: int, rng: random.Random) -> list[dict]:
    """penetrate 和 direct 各取一半；同一个 PR、同一个文件尽量不重复。"""
    chosen, used_pr, used_file = [], set(), set()
    for kind, quota in (('penetrate', n // 2), ('direct', n - n // 2)):
        pool = [c for c in cands if c['kind'] == kind]
        rng.shuffle(pool)
        pool.sort(key=lambda c: c['file'] in used_file)   # 稳定排序：没用过的文件排前面
        taken = 0
        for c in pool:
            if taken == quota:
                break
            if c['gold_pr'] in used_pr:
                continue
            chosen.append(c)
            used_pr.add(c['gold_pr'])
            used_file.add(c['file'])
            taken += 1
    if len(chosen) < n:   # 某一类不够时，用另一类补
        rest = [c for c in cands if c not in chosen and c['gold_pr'] not in used_pr]
        rng.shuffle(rest)
        chosen += rest[:n - len(chosen)]
    return chosen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--per-repo', type=int, default=14)
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--out', type=Path, default=OUT)
    args = ap.parse_args()

    rng = random.Random(args.seed)   # 固定种子：每次生成的评测集一样，前后对比才有意义
    rows = []
    for owner, name, src in REPOS:
        rows += pick(candidates(owner, name, src), args.per_repo, rng)
    for i, r in enumerate(rows, 1):
        r['id'] = i
    with open(args.out, 'w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    print('写入 %d 条 -> %s（penetrate %d，direct %d）' % (
        len(rows), args.out, sum(r['kind'] == 'penetrate' for r in rows), sum(r['kind'] == 'direct' for r in rows)))


if __name__ == '__main__':
    main()
