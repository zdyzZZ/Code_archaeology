# -*- coding: utf-8 -*-
"""异构语料的统一表示。

三种语料检索特性完全不同（见 docs/architecture.md 的对比表），
但需要一个统一的 Document 结构好做融合。

TODO:
  - [ ] 定义 Document(id, kind, text, meta)，kind ∈ {commit, issue, pr_review, code}
  - [ ] meta 里要留出处信息，narrate 阶段要引用
"""
