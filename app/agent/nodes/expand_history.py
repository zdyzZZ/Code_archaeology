# -*- coding: utf-8 -*-
"""git log --follow 拿完整变更链

⚠️ 实现你自己写。

职责：对关键行/关键 commit 往上追溯，拿到这段代码的完整演化链。

注意：
  - 用 --follow 跨重命名
  - 这是被 assess 循环回来的节点，必须知道"上次挖到哪了"，从 state 读
  - 每层的产出要追加而不是覆盖 → state 里这个字段需要 Reducer
"""


def expand_history(state: dict) -> dict:
    """TODO"""
    raise NotImplementedError
