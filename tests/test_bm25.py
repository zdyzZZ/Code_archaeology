# -*- coding: utf-8 -*-
"""BM25 分词和检索的测试。分词决定召回质量，改分词规则时先跑这个。"""
from app.rag.bm25 import BM25Index, tokenize
from app.rag.corpus import Document


def test_下划线标识符既保留整体也拆开():
    t = tokenize('proxy_bypass_environment')
    assert 'proxy_bypass_environment' in t
    assert {'proxy', 'bypass', 'environment'} <= set(t)


def test_驼峰拆开():
    assert {'ca', 'cert', 'dir'} <= set(tokenize('caCertDir'))
    assert {'http', 'adapter'} <= set(tokenize('HTTPAdapter'))


def test_issue编号和sha保持完整():
    t = tokenize('fixed in #6655, see c0813a2d')
    assert '#6655' in t
    assert 'c0813a2d' in t


def test_停用词和大小写():
    t = tokenize('The Verify flag IS used')
    assert 'the' not in t and 'is' not in t
    assert 'verify' in t


def test_中文按两个字切():
    assert tokenize('证书目录') == ['证书', '书目', '目录']


def _docs():
    # 至少 10 篇：语料太小时 BM25 的分数不稳定
    texts = [
        'Use ca_cert_dir when verify points to a directory',
        'load_verify_locations is slow under concurrency',
        'proxy bypass on Windows without DNS lookups',
        'Add support for SOCKS proxies',
        'Fix cookie handling when Host header is set',
        'Deprecate the old session API',
        'Improve error message for invalid URL',
        'Add typing to the adapters module',
        'Retry on connection reset',
        'Document the timeout parameter',
        'Fixed in #6655',
    ]
    return [Document(id='d%d' % i, kind='comment', text=t, source='s') for i, t in enumerate(texts)]


def test_精确标识符排在前面():
    ids = BM25Index(_docs()).search('isdir ca_cert_dir')
    assert ids[0] == 'd0'


def test_issue编号能精确命中():
    assert BM25Index(_docs()).search('#6655')[0] == 'd10'


def test_一个词都不命中的文档不返回():
    ids = BM25Index(_docs()).search('ca_cert_dir')
    assert ids == ['d0']


def test_空语料和空查询不报错():
    assert BM25Index([]).search('anything') == []
    assert BM25Index(_docs()).search('') == []
