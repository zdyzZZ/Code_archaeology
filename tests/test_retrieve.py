# -*- coding: utf-8 -*-
"""检索流水线和接入 graph 部分的测试，不访问网络、不调 LLM。

向量和重排的用例要用真实模型；模型没下载时自动跳过。
"""
import os

import pytest

os.environ.setdefault('HF_HUB_OFFLINE', '1')   # 测试时不去 Hugging Face 检查更新

from app.agent.nodes import retrieve as retrieve_node
from app.agent.nodes.narrate import build_material
from app.config import settings
from app.rag.corpus import Document
from app.rag.pipeline import search

TEXTS = [
    'Use ca_cert_dir when verify points to a directory, otherwise ca_certs',
    'Calling load_verify_locations on every request is very slow when many threads send requests at the same time',
    'proxy bypass on Windows without DNS lookups',
    'Add support for SOCKS proxies',
    'Fix cookie handling when Host header is set',
    'Deprecate the old session API',
    'Improve error message for invalid URL',
    'Retry on connection reset',
    'Document the timeout parameter',
    'Fixed in #6655',
]
DOCS = [Document(id='d%d' % i, kind='comment', text=t, source='s%d' % i, meta={'number': 1}) for i, t in enumerate(TEXTS)]


def _model_available(name: str) -> bool:
    try:
        from huggingface_hub import snapshot_download
        snapshot_download(name, local_files_only=True)
        return True
    except Exception:
        return False


needs_embedding = pytest.mark.skipif(not _model_available(settings.embedding_model), reason='embedding 模型没下载')
needs_reranker = pytest.mark.skipif(not _model_available(settings.rerank_model), reason='重排模型没下载')


def test_off模式不检索():
    assert search('anything', DOCS, 'off') == []


def test_bm25模式带出处和found_by():
    r = search('ca_cert_dir', DOCS, 'bm25', top_k=3)
    assert r[0]['id'] == 'd0'
    assert r[0]['source'] == 's0'
    assert r[0]['found_by'] == {'bm25': 1}


def test_空语料不报错():
    assert search('anything', [], 'hybrid_rerank') == []


@needs_embedding
def test_中文问题能找到英文讨论():
    # BM25 跨不了语言，这是本项目必须用向量检索的理由
    assert search('为什么并发时会变慢', DOCS, 'bm25') == []
    assert search('为什么并发时会变慢', DOCS, 'vector', top_k=1)[0]['id'] == 'd1'


@needs_embedding
@needs_reranker
def test_重排纠正向量检索的错误():
    # 实测：vector 把这句排到了不相关的 cookie 那段，重排后 ca_cert_dir 那段排第一
    assert search('这个 isdir 判断能删吗', DOCS, 'hybrid_rerank', top_k=1)[0]['id'] == 'd0'


def _state(**extra):
    base = {
        'owner': 'psf', 'repo': 'requests', 'file_path': 'a.py', 'start_line': 1, 'end_line': 2, 'question': '',
        'blame_lines': [{'line': 1, 'sha': 'a' * 40, 'code': 'x'}],
        'commits': [{'sha': 'a' * 40, 'date': '2024-01-01', 'author': 'u', 'message': 'msg', 'diff': 'd'}],
        'issues': [{'number': 6655, 'title': 'Use TLS', 'is_pr': True, 'from_sha': 'a' * 40,
                    'via_pr': None, 'body': 'FULL BODY TEXT', 'url': ''}],
    }
    return {**base, **extra}


def test_没检索时narrate材料和v4一样():
    m = build_material(_state())
    assert '正文：FULL BODY TEXT' in m
    assert '相关讨论片段' not in m


def test_检索后正文换成讨论片段():
    retrieved = [{'source': '#6655 评论 · bob', 'text': 'Because connections were reused'}]
    m = build_material(_state(retrieved=retrieved))
    assert 'FULL BODY TEXT' not in m                     # 正文不再整段塞进去
    assert '#### #6655 (PR) Use TLS' in m                # 标题还在
    assert '[#6655 评论 · bob]\nBecause connections were reused' in m


def test_retrieve节点off模式(monkeypatch):
    monkeypatch.setattr(settings, 'retrieval_mode', 'off')
    assert retrieve_node.retrieve(_state()) == {'retrieved': [], 'retrieval_stats': {'mode': 'off'}}


def test_retrieve节点不联网(monkeypatch):
    # 把拉正文和评论的部分换成假的，只测节点自己的逻辑
    monkeypatch.setattr(settings, 'retrieval_mode', 'bm25')
    monkeypatch.setattr(retrieve_node, '_collect', lambda state: (
        {6655: 'Previously verify=False could reuse an unverified connection'},
        {6655: [{'kind': 'comment', 'author': 'bob', 'body': 'This leaks unverified TLS connections across requests',
                 'url': '', 'path': ''}]}))
    out = retrieve_node.retrieve(_state(question='verify connection'))
    assert out['retrieval_stats']['mode'] == 'bm25'
    assert out['retrieval_stats']['comments'] == 1
    assert out['retrieved'] and all('source' in r for r in out['retrieved'])
