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

from app.agent.nodes.filter_noise import filter_noise
from app.agent.state import ArchaeologyState
from langgraph.graph import StateGraph,START,END
from app.agent.nodes.parse_target import parse_target
from app.agent.nodes.expand_history import expand_history
from app.agent.nodes.blame import blame
from app.agent.nodes.link_context import link_context
from app.agent.nodes.narrate import narrate
from langgraph.graph.state import CompiledStateGraph
from app.agent.nodes.assess import assess
from langgraph.checkpoint.memory import MemorySaver
import uuid
from app.config import settings
from app.agent.nodes.ask_human import interrupt_llm

# 主路由
def router(state:ArchaeologyState):
    if state['enough']:
        return 'narrate'
    if state.get('stop_reason') == '循环次数达到上限,证据不足':
        return 'interrupt_llm'
    return 'expand_history'

# 人工停止路由
def route_after_interrupt(state: ArchaeologyState) -> str:
    if state["enough"]:
        return "narrate"
    return "expand_history"

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
    graph.add_node('filter_noise', filter_noise)
    graph.add_node('interrupt_llm', interrupt_llm)
    graph.add_edge(START,'parse_target')
    graph.add_edge('parse_target', 'blame')
    graph.add_edge('blame', 'filter_noise')
    graph.add_edge('filter_noise', 'link_context')
    graph.add_edge('link_context', 'assess')
    graph.add_conditional_edges('assess',router, ['narrate', 'expand_history','interrupt_llm'])
    graph.add_edge('expand_history', 'filter_noise')
    graph.add_conditional_edges('interrupt_llm',route_after_interrupt, ['narrate', 'expand_history'])
    graph.add_edge('narrate',END)

    return graph.compile(checkpointer=MemorySaver())


def run( url: str, question: str | None = None) -> dict:
    """同步跑一次考古。TODO"""
    thread_id = uuid.uuid4().hex
    config = {"configurable": {"thread_id": thread_id}}
    return GRAPH.invoke({'url': url, 'question': question or '','max_depth':settings.max_depth},config=config)


async def astream( url: str, question: str | None = None,thread_id: str | None = None):
    """流式跑一次，逐步 yield 给 SSE。TODO"""
    config = {"configurable": {"thread_id": thread_id}}
    async  for chunk in GRAPH.astream(input={'url': url, 'question': question or '','max_depth':settings.max_depth},
                                      config=config,
                                      stream_mode="updates",):
        yield chunk

async def aresume(thread_id: str, approve: bool):
    """从人工中断处恢复执行"""
    config = {"configurable": {"thread_id": thread_id}}

    async for chunk in GRAPH.astream(
        Command(resume=approve),
        config=config,
        stream_mode="updates",
    ):
        yield chunk

GRAPH = build_graph()
if __name__ == '__main__':

    res = run('https://github.com/psf/requests/blob/main/src/requests/utils.py#L50-L60')