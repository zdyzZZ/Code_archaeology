# -*- coding: utf-8 -*-
"""Cross-Encoder 重排。

TODO:
  - [ ] 用 sentence-transformers 的 CrossEncoder
  - [ ] 只对 RRF 后的 Top-20 重排到 Top-5（全量重排太慢）

面试会问 Bi-Encoder 与 Cross-Encoder 的区别、为什么 Reranker 放二阶段。
一句话：Bi-Encoder 两段文本分别编码可预计算所以快但精度低；
Cross-Encoder 拼在一起过一遍模型，精度高但不能预计算，只能用在小候选集上。
"""
