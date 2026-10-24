from app.agent.state import ArchaeologyState
from langgraph.types import interrupt
from app.config import settings


def interrupt_llm(state:ArchaeologyState):
    approve = interrupt({
        "depth": state['depth'],
        "missing": state['missing'],
    })
    if approve:
        max_depth = state['max_depth']
        max_depth += 1
        if max_depth > settings.max_absolute_depth:
            stop_reason = '循环次数达到设定上限'
            return {'stop_reason': stop_reason,'max_depth': max_depth,'enough':True}
        else:
            return {'stop_reason': None,'max_depth': max_depth, 'enough': False}
    else:
        stop_reason = '人工停止'
        return {'stop_reason': stop_reason,'enough':True}
