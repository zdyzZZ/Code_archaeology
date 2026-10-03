# -*- coding: utf-8 -*-
"""从 commit message 抽 issue/PR 并拉取讨论

⚠️ 实现你自己写。

职责：正则抽 #123 / GH-123 / 完整 URL，去 GitHub API 拉 issue 和 PR 的正文与评论。

注意：
  - 一个 commit 可能提到多个 issue；一个 issue 可能被多个 commit 提到，要去重
  - GitHub REST 限流很紧（有 token 才 5000/h），优先用 GraphQL 一次拿关联数据
  - 评论可能上百条，不要全塞进上下文——这里就该做初步裁剪
  - 拉到的内容要落盘缓存，同一 issue 不重复请求
"""
from app.agent.state import ArchaeologyState
from app.github.client import extract_refs,get_issue
import asyncio
import httpx

def link_context(state: ArchaeologyState) -> dict:
    print('[link_context] 拿到 blame 行数 =', len(state['blame_lines']))
    blame_lines = state['blame_lines']
    issues_list = []
    owner = state['owner']
    repo = state['repo']
    seen = set()
    for blame_line in blame_lines:
        summary = blame_line['summary']
        numbers = extract_refs(summary)
        for number in numbers:
            if number not in seen:
                seen.add(number)
                try:
                    data = asyncio.run(get_issue(owner, repo, number))
                    issues_list.append({
                        'number': number,
                        'title': data['title'],
                        'body': (data.get('body') or '')[:2000],  # body 可能是 None
                        'url': data['html_url'],
                        'is_pr': 'pull_request' in data,
                        'from_sha': blame_line['sha'],
                    })
                except httpx.HTTPStatusError as e:
                    print('[link_context] 拉取 #%d 失败，跳过: %s' % (number, e.response.status_code))


    return {'issues': issues_list}
