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


def assess(state: dict) -> dict:
    """TODO"""
    raise NotImplementedError
