# -*- coding: utf-8 -*-
"""异构语料的统一表示：提交说明、PR / issue 正文、评论，全部变成 Document。

为什么要统一：BM25、向量、RRF、重排都只认 "id + 文本"，统一之后每一路都能处理所有材料；
而 source / meta 记住了"这段话是从哪来的"，narrate 引用时要用。

每次考古只用这一次收集到的材料建一个临时的小语料（几十到几百段），不是全 GitHub 的大索引。
"""
from dataclasses import dataclass, field

from app.rag.chunking import chunk_comment, chunk_commit, chunk_issue_body


@dataclass
class Document:
    id: str                   # 唯一标识，比如 'pr6667-body-2'；RRF 按 id 合并两路结果
    kind: str                 # commit / pr_body / issue_body / comment / review_comment / review
    text: str                 # 拿去检索的文字
    source: str               # 给人看的出处，比如 '#6667 评论 · sigmavirus24'
    meta: dict = field(default_factory=dict)   # number / author / url / sha，narrate 和评测会用


def build_documents(commits: list[dict], issues: list[dict],
                    bodies: dict[int, str], comments: dict[int, list[dict]]) -> list[Document]:
    """把 state 里收集到的材料变成 Document 列表。

    commits:  state['commits']，每条有 sha / message
    issues:   state['issues']，每条有 number / title / is_pr / url
    bodies:   {编号: 完整正文}（state 里的正文被截断过，所以单独传完整的）
    comments: {编号: get_comments() 的结果}
    """
    docs: list[Document] = []

    for c in commits:
        sha = c['sha']
        for i, text in enumerate(chunk_commit(c.get('message', ''))):
            docs.append(Document(id='commit-%s-%d' % (sha[:8], i), kind='commit', text=text,
                                 source='提交 %s' % sha[:8], meta={'sha': sha}))

    for issue in issues:
        n = issue['number']
        kind_word = 'PR' if issue.get('is_pr') else 'issue'
        base_meta = {'number': n, 'url': issue.get('url', '')}

        # 正文：第一块前面加上标题，检索时能借到标题里的关键词
        body = bodies.get(n) or issue.get('body') or ''
        for i, text in enumerate(chunk_issue_body(body)):
            if i == 0:
                text = '%s #%d %s\n%s' % (kind_word, n, issue.get('title', ''), text)
            docs.append(Document(id='%s%d-body-%d' % (kind_word.lower(), n, i),
                                 kind='pr_body' if issue.get('is_pr') else 'issue_body',
                                 text=text, source='#%d 正文' % n, meta=dict(base_meta)))

        for j, cm in enumerate(comments.get(n, [])):
            label = {'comment': '评论', 'review_comment': '代码评论', 'review': 'review'}.get(cm['kind'], cm['kind'])
            source = '#%d %s · %s' % (n, label, cm.get('author', ''))
            if cm.get('path'):
                source += '（%s）' % cm['path']
            for i, text in enumerate(chunk_comment(cm.get('body', ''))):
                docs.append(Document(id='%s%d-c%d-%d' % (kind_word.lower(), n, j, i), kind=cm['kind'],
                                     text=text, source=source,
                                     meta={**base_meta, 'author': cm.get('author', ''), 'url': cm.get('url', '')}))
    return docs
