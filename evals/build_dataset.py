# -*- coding: utf-8 -*-
"""自动构造标注集。

TODO:
  - [ ] 输入若干 repo，输出 [{repo, file, lines, gold_pr, gold_issue}]
  - [ ] 用 git log -L <start>,<end>:<file> 拿指定行的变更历史
  - [ ] 从 commit 反查所属 PR（GitHub API 或 commit message 里的 "(#123)"）
  - [ ] 过滤：只被格式化提交碰过的样本丢掉
  - [ ] 存成 jsonl
"""
