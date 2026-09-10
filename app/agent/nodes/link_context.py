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


def link_context(state: dict) -> dict:
    """TODO"""
    raise NotImplementedError
