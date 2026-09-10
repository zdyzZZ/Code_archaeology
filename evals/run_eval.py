# -*- coding: utf-8 -*-
"""跑评测并出对照表。

TODO:
  - [ ] 读 jsonl，逐条跑 agent
  - [ ] 算 Top-1 / Top-3 / Recall@K / 平均深度 / 平均成本
  - [ ] 四个配置各跑一遍做对照
  - [ ] 结果写 markdown 表，方便贴 README
  - [ ] 可以接 Langfuse Dataset + Experiment，把每次评测留痕
"""
