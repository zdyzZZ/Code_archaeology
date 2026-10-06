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
from app.github.client import extract_refs,get_issue,git_commit_pulls
import asyncio
import httpx
from app.git.log import commit_info,commit_diff
from pathlib import Path

def link_context(state: ArchaeologyState) -> dict:
    print('[link_context] 本层处理 %d 个 commit' % len(state['new_shas']))
    issues_list = []
    owner = state['owner']
    repo = state['repo']
    seen = set()
    repo_path = Path(state['repo_path'])
    file_path = Path(state['file_path'])
    # 1. 按 sha 去重，拿每个 commit 的完整 message
    commits = {}  # sha -> info
    # 查找历史sha
    for new_sha in state['new_shas']:
        if new_sha not in commits:
            info = commit_info(repo_path, new_sha)
            info['diff'] = commit_diff(repo_path, new_sha,file_path)
            commits[new_sha] = info
    # 2. 对每个 commit 找编号
    for sha, info in commits.items():
        numbers = extract_refs(info['message'],owner,repo)  # 改成从完整 message 里抽
        if not numbers:
            # 抽不到 → 用 git_commit_pulls 反查，取出每个 PR 的 number
            try:
                datas = git_commit_pulls(owner, repo, sha)
                numbers = [i['number'] for i in datas if i['merged_at']]
            except httpx.HTTPStatusError as e:
                print('[link_context] 反查 %s 的 PR 失败，跳过: %s' % (sha[:8], e.response.status_code))
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
                        'from_sha': sha,
                    })
                except httpx.HTTPStatusError as e:
                    print('[link_context] 拉取 #%d 失败，跳过: %s' % (number, e.response.status_code))

    return {'issues': issues_list,'commits': list(commits.values())}
