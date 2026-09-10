# -*- coding: utf-8 -*-
"""BM25 检索。

⚠️ 你自己写 —— "必须手写"清单里的一项。

用 rank_bm25 起步（不要先上 Elasticsearch）。

中文/代码混排的分词是个坑：
  - 纯英文 split 不够，标识符 fooBarBaz 要拆成 foo bar baz 才好召回
  - 中文需要分词（jieba 之类）
  - issue 编号、commit sha 这类要保持完整不拆

TODO:
  - [ ] tokenize()：自己定分词规则，这里决定召回质量
  - [ ] build_index() / search(query, top_k) -> [(doc_id, rank)]
  - [ ] 返回**排名**而不只是分数，RRF 要用排名
"""
