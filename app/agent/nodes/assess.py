# -*- coding: utf-8 -*-
"""判断信息是否足够（条件边）

⚠️ 实现你自己写。

职责：决定下一步去哪。这是整个状态机的大脑。

返回值决定路由：
  - 'retrieve'        信息足够，进入检索与叙事
  - 'expand_history'  信息不足，再往上挖一层
  - 'human'           超过 MAX_DEPTH 或 token 预算，交给用户决定

注意：
  - 这里要调 LLM 做判断，prompt 见 ../prompts/assess.md
  - 硬约束（depth / token）必须用代码判断，不要交给 LLM——LLM 会说"再挖一层吧"挖到天荒地老
  - 面试会问："凭什么判断挖到第几层就够了？" 你要能答出这里的设计
"""
from app.agent.state import ArchaeologyState
from app.config import settings
from app.agent.llm import get_llm
from pathlib import Path
from app.agent.nodes.narrate import build_material
from pydantic import BaseModel, Field

SYSTEM_PROMPT = (Path(__file__).parent.parent / 'prompts' / 'assess.md').read_text(encoding='utf-8')


# 模型返回格式
class AssessResult(BaseModel):
    enough: bool = Field(description="当前证据是否足够")
    missing: str = Field(description="判断证据是否足够的原因")

def assess(state: ArchaeologyState) -> dict:
    """TODO"""
    max_depth = settings.max_depth
    if not state['new_shas']:
        print(f'-------无更多提交历史-------')
        return {'enough': True, 'missing': '没有更早的历史了','stop_reason':'无更多历史提交'}
    if state['depth'] >= max_depth:
        print('-------循环次数达到上限-------')
        return {'enough':True,'stop_reason':'循环次数达到上限'}
    llm = get_llm()
    human_message = build_material(state)
    structured_llm = llm.with_structured_output(AssessResult)
    result = structured_llm.invoke([('system',SYSTEM_PROMPT),('human',human_message)])
    print(f'-------模型判断证据是否足够:{result.enough}，原因:{result.missing}-------')
    return {'enough':result.enough,'missing':result.missing, "stop_reason": "模型判断证据足够" if result.enough else None}
