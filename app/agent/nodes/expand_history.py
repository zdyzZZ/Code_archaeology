# -*- coding: utf-8 -*-
"""git log --follow 拿完整变更链

⚠️ 实现你自己写。

职责：对关键行/关键 commit 往上追溯，拿到这段代码的完整演化链。

注意：
  - 用 --follow 跨重命名
  - 这是被 assess 循环回来的节点，必须知道"上次挖到哪了"，从 state 读
  - 每层的产出要追加而不是覆盖 → state 里这个字段需要 Reducer
"""
from app.git.log import line_history
from pathlib import Path
from app.agent.state import ArchaeologyState

def expand_history(state: ArchaeologyState) -> dict:
    """TODO"""
    repo_path = Path(state['repo_path'])
    file_path = Path(state['file_path'])
    start_line = state['start_line']
    end_line = state['end_line']
    out = line_history(repo_path,file_path,start_line,end_line)
    seen = set(i['sha'] for i in state['commits'])
    new_shas = [h['sha'] for h in out if h['sha'] not in seen][:3]
    print('[expand_history] depth %d -> %d, new_shas=%s'
          % (state['depth'], state['depth'] + 1, [s[:8] for s in new_shas]))
    return {'new_shas':new_shas,'depth':state['depth']+1}
