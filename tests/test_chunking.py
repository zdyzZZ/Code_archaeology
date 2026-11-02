# -*- coding: utf-8 -*-
"""分块和清洗的测试。"""
from app.rag.chunking import MAX_CHARS, chunk_comment, chunk_commit, chunk_issue_body, clean
from app.rag.corpus import build_documents


def test_去掉PR模板的注释():
    assert clean('<!-- 请填写以下内容\n多行说明 -->\n真正的内容') == '真正的内容'


def test_去掉引用回复():
    assert clean('> 上一条评论说的话\n我的回复') == '我的回复'


def test_提交说明不切():
    msg = 'Fix x\n\n' + 'detail ' * 50
    assert len(chunk_commit(msg)) == 1


def test_短段落合并():
    chunks = chunk_issue_body('LGTM\n\nThanks!\n\n' + 'a real paragraph with enough words to stand alone ' * 3)
    assert len(chunks) == 1     # 两个短段并到了后面


def test_长段落被切开且每块不超长():
    body = '\n\n'.join(['paragraph %d ' % i + 'x' * 300 for i in range(10)])
    chunks = chunk_issue_body(body)
    assert len(chunks) > 1
    assert all(len(c) <= MAX_CHARS for c in chunks)


def test_单行超长也能切():
    chunks = chunk_issue_body('y' * (MAX_CHARS * 2 + 10))
    assert all(len(c) <= MAX_CHARS for c in chunks)


def test_评论一条一块():
    text = 'Why not reuse the existing context here?'
    assert chunk_comment(text) == [text]


def test_没有信息量的短评论丢掉():
    assert chunk_comment('LGTM') == []
    assert chunk_comment(':shipit:') == []
    assert chunk_comment('> 只有引用的一大段话，清洗之后什么都不剩') == []


def test_build_documents带出处():
    docs = build_documents(
        commits=[{'sha': 'c0813a2d' + '0' * 32, 'message': 'Use TLS settings'}],
        issues=[{'number': 6655, 'title': 'Use TLS settings', 'is_pr': True, 'url': 'u'}],
        bodies={6655: 'Previously, verify=False could leak.'},
        comments={6655: [{'kind': 'review_comment', 'author': 'bob', 'body': 'Why not reuse the old context?',
                          'url': 'c', 'path': 'adapters.py'}]},
    )
    kinds = [d.kind for d in docs]
    assert kinds == ['commit', 'pr_body', 'review_comment']
    assert docs[1].text.startswith('PR #6655 Use TLS settings')   # 正文第一块带上标题
    assert docs[2].source == '#6655 代码评论 · bob（adapters.py）'
    assert len({d.id for d in docs}) == len(docs)                # id 不重复
