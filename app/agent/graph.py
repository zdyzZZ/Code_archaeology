# -*- coding: utf-8 -*-
"""LangGraph 编排。

⚠️ 这个文件你自己写 —— "必须手写"第二项。

骨架意图（节点实现见 nodes/）：

    parse_target → blame → filter_noise → expand_history → link_context → assess
                                              ↑                              │
                                              └──── 信息不足且未超深度 ───────┘
                                                                             │ 足够
                                                              retrieve → narrate → END

要点：
  - assess 是条件边（add_conditional_edges），返回下一个节点名
  - 必须有 loop limit，否则会一直往上爬。LangGraph 的 recursion_limit 是兜底，
    业务上的 MAX_DEPTH 判断要自己写在 assess 里
  - Checkpointer 用于 HITL 恢复；先用 MemorySaver 跑通，再换持久化的
  - interrupt 打在 assess 之后、expand_history 之前

参考：
  https://langchain-ai.github.io/langgraph/concepts/low_level/
  https://langchain-ai.github.io/langgraph/concepts/human_in_the_loop/
"""
from langgraph.types import Command

from app.agent.state import ArchaeologyState
from langgraph.graph import StateGraph,START,END
from app.agent.nodes.parse_target import parse_target
from app.agent.nodes.expand_history import expand_history
from app.agent.nodes.blame import blame
from app.agent.nodes.link_context import link_context
from app.agent.nodes.narrate import narrate
from langgraph.graph.state import CompiledStateGraph
from app.agent.nodes.assess import assess



def router(state:ArchaeologyState):
    if state['enough']:
        return 'narrate'
    return 'expand_history'


def build_graph() -> CompiledStateGraph:
    """构建并编译状态机。

    TODO:
      - [ ] StateGraph(ArchaeologyState)
      - [ ] add_node × 8
      - [ ] add_conditional_edges('assess', route_fn)
      - [ ] compile(checkpointer=..., interrupt_before=[...])
    """
    graph = StateGraph(state_schema=ArchaeologyState)
    graph.add_node('parse_target', parse_target)
    graph.add_node('blame', blame)
    graph.add_node('link_context', link_context)
    graph.add_node('narrate', narrate)
    graph.add_node('expand_history', expand_history)
    graph.add_node('assess', assess)
    graph.add_edge(START,'parse_target')
    graph.add_edge('parse_target', 'blame')
    graph.add_edge('blame', 'link_context')
    graph.add_edge('link_context', 'assess')
    graph.add_conditional_edges('assess',router, ['narrate', 'expand_history'])
    graph.add_edge('expand_history', 'link_context')
    graph.add_edge('narrate',END)

    return graph.compile()


def run(url: str, question: str | None = None) -> dict:
    """同步跑一次考古。TODO"""
    graph = build_graph()
    return graph.invoke({'url': url, 'question': question or ''})


async def astream(url: str, question: str | None = None):
    """流式跑一次，逐步 yield 给 SSE。TODO"""
    raise NotImplementedError

if __name__ == '__main__':
    res = run('')