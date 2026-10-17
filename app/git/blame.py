# -*- coding: utf-8 -*-
"""blame 穿透。

⚠️ 核心逻辑你自己写 —— 这是本项目最有技术含量的一块，也是面试最好的谈资。

背景与决策见 docs/adr/0002-blame-penetration.md。

关键：git blame 默认给的是"最后一次修改"，
一次 black 格式化就能把整个文件的 blame 全部覆盖。必须穿透。
"""
from pathlib import Path
from app.git.repo import run

NOISE_PREFIXES = ('chore', 'style', 'format', 'lint', 'prettier', 'black', 'gofmt')


def blame(repo: Path, file_path: str, start: int, end: int) -> list[dict]:
    """对 file_path 的 [start, end] 行做 blame。

    TODO:
      - [ ] 用 --porcelain 输出，好解析
      - [ ] 带上 -w -C -C -M（见 ADR-0002）
      - [ ] 解析成 [{line, sha, author, date, summary}]
      - [ ] 结果缓存，key = (repo, HEAD sha, file_path, 行范围)
    """
    out = run(['git', 'blame', '--porcelain', '-w',
               '-L', '%d,%d' % (start, end), '--', file_path], cwd=repo)
    commits = {}  # sha -> {author, summary}，porcelain 同一个 commit 只详细输出一次
    result = []
    current = None
    for line in out.splitlines():
        if line.startswith('\t'):
            # 以 tab 开头的是代码内容本身，代表这一行结束
            info = commits[current['sha']]
            result.append({
                'line': current['line'],
                'sha': current['sha'],
                'author': info.get('author', ''),
                'summary': info.get('summary', ''),
                'code': line[1:],
            })
            continue
        parts = line.split(' ', 1)
        key = parts[0]
        value = parts[1] if len(parts) > 1 else ''

        if len(key) == 40 and all(c in '0123456789abcdef' for c in key):
            # 头行：<sha> <原行号> <现行号> [<行数>]
            current = {'sha': key, 'line': int(value.split()[1])}
            commits.setdefault(key, {})
        elif key == 'author':
            commits[current['sha']]['author'] = value
        elif key == 'summary':
            commits[current['sha']]['summary'] = value

    return result


def is_noise_commit(repo: Path, sha: str) -> str | None:
    """判断一个 commit 是不是格式化/lint 之类的噪声提交。"""
    # merge提交父提交 > 1 个直接返回 `None`
    title_out = run(['git','rev-list','--parents','-n','1',sha], cwd=repo)
    if len(title_out.split(' ')) > 2:
        return None
    # 提交的标题开头包含对应的字符串，判断为噪声跳过
    title_out = run(['git', 'log', '-1', '--format=%s',sha], cwd=repo).strip().lower()
    matched = next(
        (word for word in NOISE_PREFIXES if title_out.startswith(word.lower())),
        None
    )
    if matched is None and "formatting" in title_out:
        matched = "formatting"
    if matched:
        return f'提交说明包含{matched}'

    # 忽略空白
    title_out = run(['git','show','-w','--format=',sha], cwd=repo)
    if title_out.strip() == '':
        return '忽略空白后没有实际改动'

    # 批量lint
    title_out = run(['git', 'show', '--numstat', '--format=', sha], cwd=repo)
    file_count = 0
    total_changes = 0
    for text in title_out.splitlines():
        cols = text.split("\t", 2)
        if len(cols) != 3:
            continue
        added, deleted, file_path = cols
        # 二进制文件的增删行数可能是 "-"
        if not added.isdigit() or not deleted.isdigit():
            continue
        file_count += 1
        total_changes += int(added) + int(deleted)
    if file_count >= 15:
        avg_changes = total_changes / file_count
        if avg_changes <= 10:
            return (
                f"疑似批量机械修改："
                f"修改 {file_count} 个文件，"
                f"平均每文件改动 {avg_changes:.1f} 行"
            )
    return None





def blame_through(repo: Path, file_path: str, start: int, end: int,
                  max_hops: int = 5) -> list[dict]:
    """穿透版 blame：碰到噪声提交就用 `git blame <sha>^` 再往上一层。

    TODO:
      - [ ] 循环调 blame + is_noise_commit
      - [ ] 记录跳过了哪些 commit（要放进最终报告，对用户有用）
      - [ ] max_hops 兜底，别无限往上爬
    """
    raise NotImplementedError


# blame(repo=r'D:\Code Archaeologist\Code_archaeology',file_path=r'app\config.py',start=1,end=10)
