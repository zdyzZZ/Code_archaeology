# -*- coding: utf-8 -*-
"""剔除格式化/重命名等噪声提交

⚠️ 实现你自己写。

职责：判断 blame 拿到的 commit 是不是"没有信息量"的提交，是则标记跳过。

判据（启发式，需要拿真实仓库调）：
  - diff 去掉空白后无变化
  - 改动文件数很多但每个文件改动极少（典型的批量 lint）
  - commit message 命中 chore/style/format/lint/prettier/black 等前缀

注意：这一步是"标记"而不是"丢弃"——被跳过的 commit 要留在 state 里，
最终报告可以说明"中间有 3 次格式化提交已跳过"，这对用户是有用的信息。
"""


def filter_noise(state: dict) -> dict:
    """TODO"""
    raise NotImplementedError
