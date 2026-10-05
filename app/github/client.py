# -*- coding: utf-8 -*-
"""GitHub API 客户端。

TODO:
  - [ ] REST 拿单个 issue/PR
  - [ ] GraphQL 批量拿关联数据（省限流额度，强烈建议）
  - [ ] 落盘缓存：同一 issue 不重复请求
  - [ ] 限流处理：读 X-RateLimit-Remaining，快用完时降级或排队
  - [ ] 无 token 时也能跑（60 次/小时），但要给用户提示
"""
import re

import httpx

from app.config import settings

API = 'https://api.github.com'
GRAPHQL = 'https://api.github.com/graphql'

# commit message 里的 issue/PR 引用
LOCAL_PATTERNS = [
    re.compile(r"#(\d+)"),
    re.compile(r"GH-(\d+)", re.IGNORECASE),
]

URL_PATTERN = re.compile(
    r"https?://github\.com/([^/\s]+)/([^/\s]+)/(?:issues|pull)/(\d+)"
)


def extract_refs(text: str,owner: str,repo: str) -> list[int]:
    """从文本中抽当前仓库的 issue / PR 编号，跨仓库引用直接忽略。"""

    text = text or ""
    out: list[int] = []

    # 1. #123 / GH-123
    # 没写仓库，默认属于当前仓库
    for p in LOCAL_PATTERNS:
        out += [int(m) for m in p.findall(text)]

    # 2. 完整 GitHub URL
    for m in URL_PATTERN.finditer(text):
        ref_owner = m.group(1)
        ref_repo = m.group(2)
        number = int(m.group(3))

        # 只保留当前仓库
        if ref_owner.lower() != owner.lower():
            continue

        if ref_repo.lower() != repo.lower():
            continue
        out.append(number)

    return sorted(set(out))


def _headers() -> dict:
    h = {'Accept': 'application/vnd.github+json'}
    if settings.github_token:
        h['Authorization'] = 'Bearer %s' % settings.github_token
    return h

def git_commit_pulls(owner: str, repo: str, sha: str) -> list[dict]:
    with httpx.Client(timeout=20) as c:
        r = c.get('%s/repos/%s/%s/commits/%s/pulls' % (API, owner, repo, sha),
                        headers=_headers())
        r.raise_for_status()
        return r.json()

async def get_issue(owner: str, repo: str, number: int) -> dict:
    """拿 issue/PR 正文。GitHub 的 issues 接口同时覆盖 PR。TODO 加缓存。"""
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get('%s/repos/%s/%s/issues/%d' % (API, owner, repo, number),
                        headers=_headers())
        r.raise_for_status()
        return r.json()


async def get_comments(owner: str, repo: str, number: int) -> list[dict]:
    """拿评论。TODO：分页、裁剪（可能上百条）、缓存。"""
    raise NotImplementedError
