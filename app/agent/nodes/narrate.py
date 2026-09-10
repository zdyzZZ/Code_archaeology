# -*- coding: utf-8 -*-
"""生成时间线叙事

⚠️ 实现你自己写。

职责：把前面所有材料组织成人能读的考古报告。

输出结构建议：
  - timeline: [{commit, date, what_happened, why, source}]
  - conclusion: 一句话——"所以这行不能删，因为 X"
  - confidence: 证据够不够硬。**证据不足时要明说，不要编**

注意：
  - 每个结论都要带 source，不能凭空说。这是防幻觉的关键
  - prompt 见 ../prompts/narrate.md
"""


def narrate(state: dict) -> dict:
    """TODO"""
    raise NotImplementedError
