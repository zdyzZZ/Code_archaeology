# -*- coding: utf-8 -*-
"""LangGraph 状态定义。

⚠️ 这个文件你自己写 —— 计划里列的"必须手写"第一项就是它。

需要你想清楚的设计问题（这些正是面试会追问的点）：

1. 哪些字段需要 Reducer？
   节点会往同一个列表里追加东西（比如每层挖到的 commit），
   默认的覆盖语义会丢数据。哪些字段该用 add 语义？

2. 深度怎么记？
   depth 是单个计数器，还是每条追溯链各自的深度？
   如果 blame 出 5 行代码指向 5 个不同 commit，它们的深挖是并行的还是串行的？

3. token 预算放哪？
   放 state 里由节点自己累加，还是用 Langfuse 的回调统计？
   放 state 的好处是 assess 节点能直接读到并决定停不停。

4. HITL 中断时要保留什么？
   恢复时需要能接着挖，所以"挖到哪了"必须在 state 里，不能在局部变量里。

参考：
  https://langchain-ai.github.io/langgraph/concepts/low_level/
"""
from typing import TypedDict


class ArchaeologyState(TypedDict, total=False):
    # --- 输入 ---
    # TODO: repo / file_path / line_range / question

    # --- blame 阶段 ---
    # TODO: blame 结果、被判为噪声而跳过的 commit

    # --- 历史扩展阶段 ---
    # TODO: commit 链（需要 Reducer？）

    # --- 关联上下文 ---
    # TODO: 抽到的 issue / PR 编号及其内容（需要 Reducer？）

    # --- 检索 ---
    # TODO: 检索命中的片段

    # --- 控制 ---
    # TODO: depth / tokens_used / needs_human

    # --- 输出 ---
    # TODO: 时间线、结论
    ...
