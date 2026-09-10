# -*- coding: utf-8 -*-
"""git blame 定位每行最后的 commit

⚠️ 实现你自己写。

职责：对目标行范围跑 blame，拿到 (line, commit, author, date)。

注意：
  - 必须带穿透参数，见 ADR-0002：git blame -w -C -C -M
  - 结果要缓存（repo + commit + file 为 key），-C -C 很慢
  - 调 app.git.blame 里的封装，不要在节点里直接拼 git 命令
"""


def blame(state: dict) -> dict:
    """TODO"""
    raise NotImplementedError
