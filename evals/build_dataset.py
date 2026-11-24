# -*- coding: utf-8 -*-
"""自动构造评测集。

标准答案怎么来的
----------------
挑的仓库都在根目录维护了 `.git-blame-ignore-revs`：维护者自己列出的格式化提交（black / isort 等）。
`git blame --ignore-revs-file` 跳过这些提交后，每行指向的提交就是"引入这几行当前逻辑"的提交，
它所属的 PR 就是标准答案。

提交 -> PR 用两个独立来源交叉核对，一致才保留（见 PrFinder 和 verify_pr）：
  - 本地 git：squash 合并看标题末尾的 (#N)；普通合并找真正把它带进来的 "Merge pull request #N"
  - GitHub：GET /repos/{o}/{r}/commits/{sha}/pulls 里已合并的 PR
只用本地 git 时，42 条里有 6 条答案是错的：老提交根本没有 PR、rebase 合并、标题里的编号其实是 issue。

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
import hashlib
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
    r'\b(move|moved|rename|renamed|relocate|reorganiz|restructur|reorder\w*|vendor'  # 搬代码、改名
    r'|format|black|isort|ruff|flake8|pyupgrade|pre-commit|lint|style|whitespace|backslash|f-strings?'
    r'|comprehensions?|clean ?up|typo|pep ?8\w*'  # 机械改写
    r'|type hints?|typing|annotat\w*|inline types|mypy'                       # 类型标注
    r'|docs?|docstrings?|documentation|document|clarify'                      # 文档
    r'|chore)\b', re.I)

OUT = Path(__file__).resolve().parent / 'dataset.jsonl'


def excluded_lines(source: str) -> set[int]:
    """不适合出题的行号（从 1 开始）：docstring 和 import 语句。解析失败时返回空集。

    import 语句整段排除，包括多行 import 括号里的名字：格式化前这些名字挤在同一行，
    是不同 PR 陆续加进去的，blame 却全算给最后一个改这一行的 PR，答案有歧义。
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    lines = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            lines.update(range(node.lineno, node.end_lineno + 1))
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, 'body', [])
            if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], 'value', None), ast.Constant) \
                    and isinstance(body[0].value.value, str):
                lines.update(range(body[0].lineno, body[0].end_lineno + 1))
    return lines


def git(repo: Path, *args: str) -> str:
    return run(['git', *args], cwd=repo, timeout=300)


def blame_shas(repo: Path, path: str, ignore: bool) -> list[tuple[str, str, int, str]]:
    """HEAD 上整个文件的 blame，返回 [(sha, 代码, 原始行号, 原始路径), ...]，下标 i 对应第 i+1 行。

    原始行号 / 原始路径：这一行在 sha 那个版本里是哪个文件的第几行
    （porcelain 头部 "<sha> <原始行号> <当前行号>"，随后的 "filename <路径>"；文件搬过家时路径不同）。
    """
    args = ['blame', '-w', '--porcelain']
    if ignore:
        args += ['--ignore-revs-file', IGNORE_FILE]
    out = git(repo, *args, 'HEAD', '--', path)
    rows, current, orig, orig_path = [], None, 0, path
    for line in out.splitlines():
        if line.startswith('\t'):
            rows.append((current, line[1:], orig, orig_path))
        elif line.startswith('filename '):
            orig_path = line[len('filename '):]
        elif re.match(r'^[0-9a-f]{40} \d+ \d+', line):
            parts = line.split()
            current, orig = parts[0], int(parts[1])
    return rows


class SplitLineChecker:
    """格式化把一行拆成多行时，答案是否还明确。

    几行对应同一个原始行号，说明格式化前它们是同一行。
      - 这一行是答案提交新写的 → 答案明确，保留
      - 这一行在答案提交之前就有、答案提交只是改了它（例如往列表里加 / 删一项）
        → 这一行是多个 PR 陆续改出来的，blame 却全算给最后一个，答案有歧义，丢掉
    用 `git log -L n,n:<当时的路径> <sha>` 看这一行的历史：只有 sha 自己 = 新写的。
    """

    def __init__(self, repo: Path):
        self.repo = repo
        self.cache: dict[tuple[str, str, int], bool] = {}

    def has_earlier_history(self, sha: str, path: str, line_no: int) -> bool:
        key = (sha, path, line_no)
        if key not in self.cache:
            try:
                out = git(self.repo, 'log', '-L', '%d,%d:%s' % (line_no, line_no, path),
                          '--format=@@COMMIT %H', sha)
                shas = re.findall(r'^@@COMMIT ([0-9a-f]{40})', out, re.M)
                self.cache[key] = len(shas) > 1
            except RuntimeError:
                self.cache[key] = True     # 查不了就当有歧义：宁可少一条样本，不要错的答案
        return self.cache[key]

    def ambiguous(self, rows: list[tuple[str, str, int, str]]) -> bool:
        origins = [(r[2], r[3]) for r in rows]
        if len(set(origins)) == len(origins):
            return False                   # 没有拆分
        shared = {o for o in origins if origins.count(o) > 1}
        return any(self.has_earlier_history(rows[0][0], p, n) for n, p in shared)


def is_code(line: str) -> bool:
    s = line.strip()
    return bool(s) and not s.startswith(('#', '"""', "'''", 'import ', 'from ', '@'))


class PrFinder:
    """提交 -> PR 编号（本地 git 的判断）。出题时再用 verify_pr 和 GitHub 交叉核对。"""

    def __init__(self, repo: Path):
        self.repo = repo
        self.cache: dict[str, tuple[int | None, str]] = {}

    def __call__(self, sha: str) -> tuple[int | None, str]:
        if sha not in self.cache:
            title = git(self.repo, 'log', '-1', '--format=%s', sha).strip()
            # squash 合并：标题末尾带 (#123)。也可能是 issue 编号（"fix foo (#7940)"），所以之后要核对
            m = re.search(r'\(#(\d+)\)\s*$', title)
            pr = int(m.group(1)) if m else self._merged_by(sha)
            self.cache[sha] = (pr, title)
        return self.cache[sha]

    def _merged_by(self, sha: str) -> int | None:
        """真正把 sha 带进来的那个 "Merge pull request #N"。

        之后出现的 merge 不一定是它带进来的：sha 可能早已在主线上（rebase 合并、维护者直接提交），
        之后的 merge 只是恰好在它的后代里。判据：merge 的第一父提交还不包含 sha，才是它带进来的。
        "包含 sha" = 是 sha 本身，或在 sha..HEAD 的 ancestry-path 上（一次 rev-list 算出全部，
        不用对每个 merge 调 merge-base）。
        """
        descendants = set(git(self.repo, 'rev-list', '--ancestry-path', '%s..HEAD' % sha).split())
        descendants.add(sha)
        merges = git(self.repo, 'log', '--merges', '--ancestry-path', '--reverse',
                     '--format=%P%x09%s', '%s..HEAD' % sha).splitlines()
        for line in merges:
            parents, subject = line.split('\t', 1)
            if parents.split()[0] not in descendants:
                m = re.match(r'Merge pull request #(\d+)', subject)
                return int(m.group(1)) if m else None    # 带进来的是普通分支合并，没有 PR
        return None


def verify_pr(owner: str, name: str, sha: str, pr: int) -> bool:
    """GitHub 记录的"包含这个提交并已合并的 PR"里有 pr，才算答案可靠。

    本地 git 和 GitHub 是两个独立来源：本地会把标题里的 issue 编号当成 PR、看不到 rebase 合并；
    GitHub 对 2012 年前的老提交常常查不到。两边一致才保留，不一致或查不到的样本丢掉。
    只对 pick 选中的候选调用，请求有落盘缓存。
    """
    from app.github.client import git_commit_pulls
    merged = [p['number'] for p in git_commit_pulls(owner, name, sha) if p.get('merged_at')]
    return pr in merged


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
    split = SplitLineChecker(repo)
    files = [f for f in git(repo, 'ls-files', src).split()
             if f.endswith('.py') and '/tests/' not in f and not f.split('/')[-1].startswith('test_')]
    print('[%s/%s] HEAD=%s，%d 个文件，%d 个格式化提交' % (owner, name, head[:8], len(files), len(ignored)))

    out = []
    for path in files:
        plain, real = blame_shas(repo, path, False), blame_shas(repo, path, True)
        if len(plain) != len(real):
            continue
        doc = excluded_lines('\n'.join(r[1] for r in real))
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
                # split.ambiguous 要跑 git log -L，比较慢，放在最后
                if (pr and not AMBIGUOUS_WORDS.search(title) and not title.startswith('Merge ')
                        and not split.ambiguous([real[k] for k in block])):
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


def stable_order(c: dict, seed: int) -> str:
    """每条候选自己的排序键，只由它自己的位置决定。

    以前用 rng.shuffle 打乱整个候选池：过滤规则一改、候选池少一条，后面所有候选的顺序都变，
    评测集几乎整套换掉（两版之间只剩 7~8 条相同），前后结果没法对比。
    按哈希排序时，删掉一条候选只会让它原来的名额由下一条补上，其余样本不变。
    不用内置 hash()：它每次启动进程都随机。
    """
    key = '%d:%s:%s:%d:%d' % (seed, c['repo'], c['file'], c['start'], c['end'])
    return hashlib.sha1(key.encode('utf-8')).hexdigest()


def pick(cands: list[dict], n: int, seed: int) -> list[dict]:
    """penetrate 和 direct 各取一半；同一个 PR、同一个文件尽量不重复；答案要通过 verify_pr。"""
    chosen, used_pr, used_file = [], set(), set()
    checked: dict[str, bool] = {}
    rejected = []

    def ok(c: dict) -> bool:
        if c['gold_sha'] not in checked:
            owner, name = c['repo'].split('/')
            checked[c['gold_sha']] = verify_pr(owner, name, c['gold_sha'], c['gold_pr'])
            if not checked[c['gold_sha']]:
                rejected.append(c)
        return checked[c['gold_sha']]

    def take(pool: list[dict], quota: int) -> None:
        taken = 0
        for c in pool:
            if taken == quota:
                break
            if c['gold_pr'] in used_pr or not ok(c):
                continue
            chosen.append(c)
            used_pr.add(c['gold_pr'])
            used_file.add(c['file'])
            taken += 1

    for kind, quota in (('penetrate', n // 2), ('direct', n - n // 2)):
        pool = sorted((c for c in cands if c['kind'] == kind), key=lambda c: stable_order(c, seed))
        pool.sort(key=lambda c: c['file'] in used_file)   # 稳定排序：没用过的文件排前面
        take(pool, quota)
    if len(chosen) < n:   # 某一类不够时，用另一类补
        rest = sorted((c for c in cands if c not in chosen), key=lambda c: stable_order(c, seed))
        take(rest, n - len(chosen))
    for c in rejected:
        print('    丢掉 %s %s：本地判断是 #%d，GitHub 不一致或查不到（%s）' % (
            c['gold_sha'][:8], c['kind'], c['gold_pr'], c['gold_title'][:50]))
    return chosen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--per-repo', type=int, default=14)
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--out', type=Path, default=OUT)
    args = ap.parse_args()

    rows = []
    for owner, name, src in REPOS:
        rows += pick(candidates(owner, name, src), args.per_repo, args.seed)
    for i, r in enumerate(rows, 1):
        r['id'] = i
    with open(args.out, 'w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    print('写入 %d 条 -> %s（penetrate %d，direct %d）' % (
        len(rows), args.out, sum(r['kind'] == 'penetrate' for r in rows), sum(r['kind'] == 'direct' for r in rows)))


if __name__ == '__main__':
    main()
