# -*- coding: utf-8 -*-
"""分块策略。

⚠️ 你自己写。要点：三种语料不能用同一套参数。

  - commit message：本身就很短，整条一块，不要切
  - issue / PR 讨论：按评论切，长评论再按段落切；要保留"谁说的"
  - 代码：按函数/类切，别按固定行数切断

TODO:
  - [ ] chunk_commit()
  - [ ] chunk_issue()
  - [ ] chunk_code()
"""
