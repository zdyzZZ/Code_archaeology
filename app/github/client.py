# -*- coding: utf-8 -*-
"""GitHub API 客户端。

所有 GET 请求都落盘缓存（data/cache/github/）：
  - 评测要按 5 种检索模式各跑一遍，不缓存就是 5 倍的请求
  - 已关闭的 issue / PR 内容不会再变，不用考虑过期；想强制刷新就删掉对应的 json 文件
  - 只缓存成功的响应，404 / 403 不缓存

TODO:
  - [ ] GraphQL 批量拿关联数据（省限流额度）
  - [ ] 限流处理：读 X-RateLimit-Remaining，快用完时降级或排队
  - [ ] 无 token 时也能跑（60 次/小时），但要给用户提示
"""
import asyncio
import json
import re
import time

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

# ---------- 落盘缓存 ----------

def _cache_file(path: str):
    """'/repos/psf/requests/issues/6667' -> data/cache/github/repos__psf__requests__issues__6667.json"""
    return settings.github_cache_dir / (path.strip('/').replace('/', '__') + '.json')


def _cache_load(path: str):
    f = _cache_file(path)
    if f.exists():
        return json.loads(f.read_text(encoding='utf-8'))
    return None


def _cache_save(path: str, data) -> None:
    f = _cache_file(path)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')


# ---------- 重试 ----------
# 代理不稳定时 ReadTimeout / ConnectTimeout 很常见（评测 42 条里一次就超时 4 条）。
# httpx 自带的 transport retries 只重试连接失败，不管读超时，所以自己包一层。
RETRY_STATUS = {502, 503, 504}
RETRY_WAITS = (2, 4)          # 第 1、2 次失败后各等几秒；共试 3 次


def _send(c: httpx.Client, url: str, **kw) -> httpx.Response:
    for wait in (*RETRY_WAITS, None):
        try:
            r = c.get(url, **kw)
            if r.status_code not in RETRY_STATUS or wait is None:
                return r
        except httpx.TransportError as e:
            if wait is None:
                raise
            print('[github] %s，%d 秒后重试：%s' % (type(e).__name__, wait, url))
        time.sleep(wait)


async def _asend(c: httpx.AsyncClient, url: str, **kw) -> httpx.Response:
    for wait in (*RETRY_WAITS, None):
        try:
            r = await c.get(url, **kw)
            if r.status_code not in RETRY_STATUS or wait is None:
                return r
        except httpx.TransportError as e:
            if wait is None:
                raise
            print('[github] %s，%d 秒后重试：%s' % (type(e).__name__, wait, url))
        await asyncio.sleep(wait)


def _get(path: str):
    """单个对象的 GET，带缓存。"""
    cached = _cache_load(path)
    if cached is not None:
        return cached
    with httpx.Client(timeout=20) as c:
        r = _send(c, API + path, headers=_headers())
        r.raise_for_status()
        data = r.json()
    _cache_save(path, data)
    return data


def _get_all(path: str) -> list:
    """列表类 GET：自动翻页，全部拿完再缓存。

    GitHub 每页最多 100 条，下一页的地址在响应头 Link 里，httpx 已经解析成 r.links。
    """
    cached = _cache_load(path)
    if cached is not None:
        return cached
    items, url, params = [], API + path, {'per_page': 100}
    with httpx.Client(timeout=20) as c:
        while url:
            r = _send(c, url, headers=_headers(), params=params)
            r.raise_for_status()
            items += r.json()
            url = r.links.get('next', {}).get('url')
            params = None   # 下一页的 url 里已经带了参数
    _cache_save(path, items)
    return items


# ---------- 对外的函数 ----------

def git_commit_pulls(owner: str, repo: str, sha: str) -> list[dict]:
    """包含这个提交的 PR 列表。"""
    return _get('/repos/%s/%s/commits/%s/pulls' % (owner, repo, sha))


async def get_issue(owner: str, repo: str, number: int) -> dict:
    """拿 issue/PR 正文。GitHub 的 issues 接口同时覆盖 PR。

    保持 async 签名，调用方（link_context 的 asyncio.run）不用改。
    """
    path = '/repos/%s/%s/issues/%d' % (owner, repo, number)
    cached = _cache_load(path)
    if cached is not None:
        return cached
    async with httpx.AsyncClient(timeout=20) as c:
        r = await _asend(c, API + path, headers=_headers())
        r.raise_for_status()
        data = r.json()
    _cache_save(path, data)
    return data


def _is_bot(item: dict) -> bool:
    user = item.get('user') or {}
    return user.get('type') == 'Bot' or (user.get('login') or '').endswith('[bot]')


def get_comments(owner: str, repo: str, number: int, is_pr: bool) -> list[dict]:
    """一个 issue / PR 下的全部讨论，去掉机器人和空内容。

    三种来源，含义不同：
      comment         对话区的评论（issue 和 PR 都有）
      review_comment  写在代码行上的 review 评论（只有 PR 有），带文件路径
      review          review 的总结（Approve / Request changes 时写的话，只有 PR 有）

    返回 [{kind, author, body, url, path}]，按 GitHub 返回的顺序（时间顺序）。
    """
    base = '/repos/%s/%s' % (owner, repo)
    sources = [('comment', '%s/issues/%d/comments' % (base, number))]
    if is_pr:
        sources += [('review_comment', '%s/pulls/%d/comments' % (base, number)),
                    ('review', '%s/pulls/%d/reviews' % (base, number))]
    out = []
    for kind, path in sources:
        for item in _get_all(path):
            body = (item.get('body') or '').strip()
            if not body or _is_bot(item):
                continue
            out.append({
                'kind': kind,
                'author': (item.get('user') or {}).get('login', ''),
                'body': body,
                'url': item.get('html_url', ''),
                'path': item.get('path', ''),   # 只有 review_comment 有
            })
    return out
