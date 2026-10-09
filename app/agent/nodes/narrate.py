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


from app.agent.state import ArchaeologyState
from pathlib import Path
from app.agent.llm import get_llm

PROMPT = (Path(__file__).parent.parent / 'prompts' / 'narrate.md').read_text(encoding='utf-8')



def build_material(state: ArchaeologyState) -> str:
    '''拼接state传入模型'''
    human_str = f"## 目标\n{state['owner']}/{state['repo']}的 {state['file_path']}第{state['start_line']}-{state['end_line']}行\n"
    blame_text = ["## 代码与 blame"]
    for blame_line in state["blame_lines"]:
        blame_text.append(
            f"L{blame_line['line']} "
            f"[{blame_line['sha'][:8]}] "
            f"{blame_line['code']}"
        )

    commit_text = ['## 改动记录（从旧到新）']
    for c in sorted(state['commits'], key=lambda c: c['date']):
        commit_text.append(f"### {c['sha'][:8]}  {c['date']}  {c['author']}")
        commit_text.append(f"提交说明：\n{c['message'][:1000]}")
        commit_text.append(f"本次改动：\n{c['diff'][:1500]}")

        related = [i for i in state['issues'] if i['from_sha'] == c['sha']]
        if not related:
            commit_text.append('关联的 issue/PR：无')
        for i in related:
            kind = 'PR' if i['is_pr'] else 'issue'
            source = f"（由 PR #{i['via_pr']} 引用）" if i['via_pr'] else ''
            commit_text.append(f"#### #{i['number']} ({kind}) {i['title']} {source}")
            commit_text.append(f"正文：{i['body'][:4000]}")
    parts = [human_str, '\n'.join(blame_text), '\n'.join(commit_text)]

    if state.get('stop_reason') in ['循环次数达到上限','无更多历史提交']:
        stop_reason = f'## 停止原因:{state["stop_reason"]}\n仍然缺少:{state.get("missing")}'
        parts.append(stop_reason)
    if state['question']:
        parts.insert(0, f"## 用户想知道\n{state['question']}")
    return '\n\n'.join(parts)


def narrate(state: ArchaeologyState) -> dict:
    print('[narrate] issue 数 =', len(state['issues']))
    llm = get_llm()
    human_material = build_material(state)
    res = llm.invoke([("system", PROMPT),("human", human_material),])
    return {'report': res.content}
