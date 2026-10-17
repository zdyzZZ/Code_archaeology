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
from pathlib import Path
from app.agent.state import ArchaeologyState
from app.git.blame import is_noise_commit
from app.git.log import commit_info


def filter_noise(state: ArchaeologyState) -> dict:
    """TODO"""
    new_shas = []
    repo_path = Path(state['repo_path'])
    skipped = []
    for new_sha in state['new_shas']:
        # 凑够三个非噪声提交就break
        if len(new_shas) == 3:
            print(f'-------------保留的提交shas:{[i[:8] for i in new_shas]}-------------')
            break
        print(f'-------------保留的提交shas:{[i[:8] for i in new_shas]}-------------')
        # 判断噪声提交
        out = is_noise_commit(repo_path, new_sha)
        if out:
            summary = commit_info(repo_path, new_sha)['message'].split('\n')[0]
            print(f'-------------跳过{new_sha[:8]},原因:{out},该sha的修改标题:{summary}-------------')
            skipped.append({'sha': new_sha,'summary': summary,'reason': out})
            continue
        new_shas.append(new_sha)
    return {'new_shas': new_shas, 'skipped': skipped}