# -*- coding: utf-8 -*-
"""解析输入的 GitHub URL

⚠️ 实现你自己写。

职责：把 URL 拆成 repo / file_path / line_range，并确保本地有该 repo 的克隆。

注意：
  - URL 形态不止一种：
      https://github.com/owner/repo/blob/main/path/to/file.py#L12-L30
      https://github.com/owner/repo/blob/<sha>/path/file.py
  - 分支名可能含斜杠（feature/foo），不能简单按 / 切
  - 只需要 blame，不需要完整历史 → 可以考虑 --filter=blob:none 的部分克隆省时间
"""
import re

from app.git.repo import ensure_cloned

URL_RE = re.compile(
    r'github\.com/([^/]+)/([^/]+)/blob/([^/]+)/([^#?]+)'   # owner / repo / ref / 文件路径
    r'(?:#L(\d+)(?:C\d+)?(?:-L(\d+)(?:C\d+)?)?)?'   # #L12 / #L12-L30 / #L12C5-L30C41
)

def parse_target(state: dict) -> dict:
    """TODO"""
    m = URL_RE.search(state['url'])
    if not m:
        raise ValueError('看不懂这个链接: %s' % state['url'])

    owner, repo, ref, file_path, start, end = m.groups()
    start = int(start) if start else 1
    end = int(end) if end else start

    repo_path = ensure_cloned(owner, repo)
    print('[parse_target] %s/%s %s L%d-L%d' % (owner, repo, file_path, start, end))

    return {
        'owner': owner, 'repo': repo, 'ref': ref, 'file_path': file_path,
        'start_line': start, 'end_line': end, 'repo_path': str(repo_path),
    }

