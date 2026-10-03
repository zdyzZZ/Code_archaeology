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

    # 涉及的 commit：来自 blame_lines，按 sha 去重
    commit_text = ['## 涉及的 commit']
    for c in state['commits']:
        commit_text.append(f"### {c['sha'][:8]}\n{c['message'][:1000]}")

    # 关联的 issue/PR：来自 issues
    issue_text = ['## 关联的 issue/PR']
    if not state['issues']:
        issue_text.append('没有找到关联的 issue/PR')
    for issue in state['issues']:
        kind = 'PR' if issue['is_pr'] else 'issue'
        issue_text.append(f"### #{issue['number']} ({kind}) {issue['title']}")
        issue_text.append(f"来源 commit: {issue['from_sha'][:8]}")
        issue_text.append(f"正文：{issue['body']}")
    return '\n\n'.join([human_str, '\n'.join(blame_text), '\n'.join(commit_text), '\n'.join(issue_text)])


def narrate(state: ArchaeologyState) -> dict:
    print('[narrate] issue 数 =', len(state['issues']))
    llm = get_llm()
    human_material = build_material(state)
    res = llm.invoke([("system", PROMPT),("human", human_material),])
    return {'report': res.content}
