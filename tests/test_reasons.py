# -*- coding: utf-8 -*-
"""理由评测：证据匹配、score_reason、理由表。不调 LLM（评委被替换掉）。"""
import evals.judge
from evals.reasons import quote_found
from evals.run_eval import score_reason, summarize

QUOTE = 'We should not perform DNS lookups here because they are slow on Windows'


def test_原文直接包含():
    assert quote_found(QUOTE, 'Some text. ' + QUOTE + '. More text.')


def test_空白和大小写和引用符号不影响():
    text = '> we should NOT perform\n>  DNS lookups here because they are slow on windows'
    assert quote_found(QUOTE, text)


def test_截断后只剩一部分也算():
    # 材料在中间被截断，摘录只有前 60 多个字符落进来
    assert quote_found(QUOTE, 'intro ' + QUOTE[:65])


def test_只有零星几个词相同不算():
    assert not quote_found(QUOTE, 'DNS lookups are fine. We should perform them.')


REASON = {'question': '为什么不用 urllib 的 proxy_bypass？', 'reason': 'Windows 上 DNS 查询慢',
          'location': 'comments', 'reviewed': True,
          'evidence': [{'source': 'C3', 'url': '', 'quote': QUOTE}]}


def test_score_reason(monkeypatch):
    monkeypatch.setattr(evals.judge, 'judge',
                        lambda report, reason: {'reason_score': 2, 'cites_source': True, 'judge_why': 'ok'})
    record = {'mode': 'hybrid', 'report': 'r', 'material': '... ' + QUOTE,
              'retrieved5': ['unrelated', QUOTE + ' and more']}
    out = score_reason(record, REASON)
    assert out['ev_in_material'] and out['ev_recall5'] and out['reason_score'] == 2

    # off 模式没有检索，Recall@5 不算；材料里没有证据
    out = score_reason({'mode': 'off', 'report': 'r', 'material': 'nothing'}, REASON)
    assert out['ev_in_material'] is False and out['ev_recall5'] is None


def test_评委出错不影响其它指标(monkeypatch):
    def boom(report, reason):
        raise RuntimeError('timeout')
    monkeypatch.setattr(evals.judge, 'judge', boom)
    out = score_reason({'mode': 'off', 'report': 'r', 'material': QUOTE}, REASON)
    assert out['ev_in_material'] is True and out['reason_score'] is None


def test_理由表():
    base = {'repo': 'o/r', 'file': 'f.py', 'start': 1, 'end': 4, 'gold_pr': 1, 'gold_title': 't',
            'key_prs': [1], 'top1': True, 'top3': True, 'sha_found': True, 'pr_in_material': True,
            'recall5': None, 'depth': 0, 'seconds': 1.0, 'reviewed': True, 'ev_recall5': None}
    rs = [dict(base, id=1, kind='direct', location='comments', reason_score=2, cites_source=True, ev_in_material=False),
          dict(base, id=2, kind='penetrate', location='pr_body', reason_score=0, cites_source=False, ev_in_material=True)]
    table = summarize('off-q', rs)
    assert '## 理由（带问题运行）' in table
    assert '| 全部 | 2 | 1/2 (50%) | 1/2 (50%) | 0.50 | 1/2 (50%) | 1/2 (50%) | - |' in table
    assert 'location=comments' in table
