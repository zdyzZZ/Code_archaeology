# -*- coding: utf-8 -*-
"""评委：对照人工确认过的理由，判断报告有没有答出"为什么"。

局限：评委和 agent 是同一个模型，可能偏袒自己的写法。缓解办法是标准理由经过人工审核、
判分标准写死在提示词里（0 / 1 / 2 各自什么情况），并且保存 why 方便抽查。
"""
from pathlib import Path

from pydantic import BaseModel, Field

from app.agent.llm import get_llm

PROMPT = (Path(__file__).resolve().parent / 'prompts' / 'judge_reason.md').read_text(encoding='utf-8')


class Verdict(BaseModel):
    score: int = Field(ge=0, le=2, description='2 命中 / 1 部分 / 0 没有')
    cites_source: bool
    why: str


def judge(report: str, reason: dict) -> dict:
    evidence = '\n'.join('- [%s] %s' % (e['source'], e['quote']) for e in reason['evidence'])
    human = ('## 问题\n%s\n\n## 标准理由\n%s\n\n## 原文证据\n%s\n\n## 待评的报告\n%s' % (
        reason['question'], reason['reason'], evidence or '（无）', report))
    # 不传 temperature：当前用的推理模型只接受默认值，传 0 会报 400
    v: Verdict = get_llm().with_structured_output(Verdict).invoke(
        [('system', PROMPT), ('human', human)])
    return {'reason_score': v.score, 'cites_source': v.cites_source and v.score > 0, 'judge_why': v.why}
