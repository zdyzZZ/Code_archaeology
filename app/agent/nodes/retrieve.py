# -*- coding: utf-8 -*-
"""Hybrid 检索相关语料

⚠️ 实现你自己写。

职责：把 issue/PR/commit 语料建索引并检索，给 narrate 提供依据。

注意：
  - 调 app.rag 里的组件，节点本身不实现检索逻辑
  - 索引要按 repo 缓存复用
  - 检索结果要带出处（哪个 issue 的哪条评论），narrate 阶段要引用
"""


def retrieve(state: dict) -> dict:
    """TODO"""
    raise NotImplementedError
