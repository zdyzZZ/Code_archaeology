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
from pydantic import BaseModel, Field
from app.agent.llm import get_llm, language_rule


class NarrateResult(BaseModel):
    report: str = Field(description='完整的考古报告，markdown 格式')
    key_prs: list[int] = Field(
        description='引入这几行当前逻辑的 PR 编号（只写数字），最可能的排第一，最多 3 个。'
                    '只填材料里出现过的 PR；格式化、改类型标注、搬文件这类 PR 不算；找不到就返回空列表')


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

    # v5：检索过（retrieved 非空）时，PR / issue 正文不再整段塞进来，只留标题，
    # 相关的内容由下面的"相关讨论片段"提供。
    # 用 .get()：assess 也调用这个函数，那时还没到 retrieve 节点，没有 retrieved
    retrieved = state.get('retrieved') or []

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
            if not retrieved:
                commit_text.append(f"正文：{i['body'][:4000]}")
    parts = [human_str, '\n'.join(blame_text), '\n'.join(commit_text)]
    if retrieved:
        snippet_text = ['## 相关讨论片段（从 PR / issue 正文和评论里检索得到，按相关性从高到低）']
        for r in retrieved:
            snippet_text.append(f"[{r['source']}]\n{r['text']}")
        parts.append('\n\n'.join(snippet_text))
    if state.get('skipped'):
        skip_list = ['## 已跳过的提交(格式化等，不是原因)']
        for skip_dic in state['skipped']:
            skip_reason = (
                f'{skip_dic["sha"][:8]}  '
                f'{skip_dic["summary"]}——{skip_dic["reason"]}'
            )
            skip_list.append(skip_reason)
        parts.append('\n'.join(skip_list))
    if state.get('stop_reason') in ['无更多历史提交','循环次数达到设定上限']:
        stop_reason = f'## 停止原因:{state["stop_reason"]}\n仍然缺少:{state.get("missing")}'
        parts.append(stop_reason)
    elif state.get('stop_reason') == '人工停止':
        stop_reason = f'## 分析在第{state["depth"]}层停止\n仍然缺少:{state.get("missing")}'
        parts.append(stop_reason)
    if state['question']:
        parts.insert(0, f"## 用户想知道\n{state['question']}")
    return '\n\n'.join(parts)


def narrate(state: ArchaeologyState) -> dict:
    print('[narrate] issue 数 =', len(state['issues']))
    llm = get_llm().with_structured_output(NarrateResult)
    human_material = build_material(state)
    system = PROMPT + "\n\n" + language_rule(state.get("language"))
    res = llm.invoke([("system", system), ("human", human_material)])
    # 去重并保持顺序；模型偶尔会把同一个编号写两遍
    key_prs = list(dict.fromkeys(res.key_prs))[:3]
    print('[narrate] key_prs =', key_prs)
    return {'report': res.report, 'key_prs': key_prs}
