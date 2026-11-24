import re
from pathlib import Path
from app.git.repo import run


def commit_info(repo: Path, sha: str) -> dict:
    """拿某个 commit 的完整 message（标题 + 正文 + 日期 + 修改人）。"""
    out = run(['git', 'log', '-1', '--format=%ad%n%an%n%B', '--date=short', sha], cwd=repo).strip()
    date, author, message = out.split('\n', 2)
    return {'sha': sha, 'date': date, 'author': author, 'message': message}


HUNK_HEADER = re.compile(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@', re.M)


def commit_hunks(repo: Path, sha: str, path: str, lines: set[int]) -> str:
    """sha 对 path 的改动里，覆盖了 lines（sha 版本里的行号）的那几段 hunk。

    用途：git log -L 漏掉 blame 指出的提交时的兜底。-L 每经过一个提交都按 diff 映射行范围，
    经过格式化提交时范围可能偏到相邻的旧行上，于是 blame 说是 X、-L 的历史里却没有 X
    （requests cookies.py 的 96cd8e9c、scrapy resolver.py 的 e69cf415 都是这样）。
    只取相关 hunk 而不是整份 diff：老提交常常一次改几百行，整份截断后关键那段会被截掉。
    path 用 sha 那个版本里的路径（blame 的 filename），文件搬过家时和现在的不同。
    取不到时返回空字符串，由调用方写"未能获取"。
    """
    out = run(['git', 'show', '--format=', '--no-color', '-U3', sha, '--', path], cwd=repo)
    starts = [m.start() for m in HUNK_HEADER.finditer(out)]
    picked = []
    for i, pos in enumerate(starts):
        m = HUNK_HEADER.match(out, pos)
        first = int(m.group(1))
        count = int(m.group(2)) if m.group(2) is not None else 1
        if any(first <= n < first + count for n in lines):
            end = starts[i + 1] if i + 1 < len(starts) else len(out)
            picked.append(_trim_hunk(out[pos:end].rstrip('\n'), first, lines))
    return '\n'.join(picked)


def _trim_hunk(hunk: str, first: int, lines: set[int], context: int = 8) -> str:
    """hunk 太长时只留目标行前后 context 行：narrate 会把 diff 截到 1500 字，目标行在长 hunk 中间时会被截掉。"""
    header, *body = hunk.split('\n')
    if len(body) <= 2 * context + len(lines):
        return hunk
    lo, hi = min(lines) - context, max(lines) + context
    kept, new_no = [], first
    for row in body:
        if lo <= new_no <= hi:
            kept.append(row)
        if not row.startswith('-'):      # '-' 行只在旧版本里，不占新版本的行号
            new_no += 1
    return '\n'.join([header, '...', *kept, '...'])


def line_history(repo: Path, file_path:Path,start:int,end:int) -> list[dict]:
    '''追踪历史链'''
    out = run(['git','log','-L',f'{start},{end}:{file_path}','--format=@@COMMIT %H'],cwd=repo)
    history = []

    for chunk in out.split("@@COMMIT "):
        chunk = chunk.strip()
        if not chunk:
            continue

        # merge 提交在 -L 下只有 "@@COMMIT <sha>" 一行、没有 diff；跳过，
        # link_context 取不到 diff 时会写"未能获取"，而不是空字符串
        if "\n" not in chunk:
            continue
        sha, diff = chunk.split("\n", 1)

        history.append({
            "sha": sha.strip(),
            "diff": diff.strip(),
        })
    return history
