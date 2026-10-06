# -*- coding: utf-8 -*-
"""git blame 定位每行最后的 commit

⚠️ 实现你自己写。

职责：对目标行范围跑 blame，拿到 (line, commit, author, date)。

注意：
  - 必须带穿透参数，见 ADR-0002：git blame -w -C -C -M
  - 结果要缓存（repo + commit + file 为 key），-C -C 很慢
  - 调 app.git.blame 里的封装，不要在节点里直接拼 git 命令
"""
from pathlib import Path
from app.agent.state import ArchaeologyState
from app.git.blame import blame as git_blame

def blame(state: ArchaeologyState) -> dict:
    lines = git_blame(Path(state['repo_path']), state['file_path'],
                      state['start_line'], state['end_line'])
    print('[blame] 拿到 %d 行，涉及 %d 个 commit'
          % (len(lines), len({l['sha'] for l in lines})))
    new_shas = list(dict.fromkeys(i["sha"] for i in lines))
    return {'blame_lines': lines,'new_shas':new_shas,'depth':0}
