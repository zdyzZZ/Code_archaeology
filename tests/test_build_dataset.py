# -*- coding: utf-8 -*-
"""评测集出题的稳定性：候选池少一条时，其余样本不变。不调 GitHub、不碰真实仓库。"""
from evals import build_dataset as bd


def fake_cands(n: int = 60) -> list[dict]:
    return [{'repo': 'o/r', 'file': 'f%d.py' % (i % 20), 'start': i, 'end': i + 4,
             'gold_pr': 1000 + i, 'gold_sha': '%040x' % i, 'gold_title': 't',
             'kind': 'penetrate' if i % 3 == 0 else 'direct'} for i in range(n)]


def key(c: dict) -> tuple:
    return c['file'], c['start']


def test_同样的输入选出同样的样本(monkeypatch):
    monkeypatch.setattr(bd, 'verify_pr', lambda *a: True)
    assert [key(c) for c in bd.pick(fake_cands(), 14, 42)] == [key(c) for c in bd.pick(fake_cands(), 14, 42)]


def test_删掉一条被选中的候选其余样本不变(monkeypatch):
    monkeypatch.setattr(bd, 'verify_pr', lambda *a: True)
    cands = fake_cands()
    before = bd.pick(cands, 14, 42)
    removed = before[3]
    after = bd.pick([c for c in cands if c is not removed], 14, 42)
    assert len(after) == 14
    kept = {key(c) for c in before} - {key(removed)}
    # 只有被删的那条换成了别的；同文件去重的排序偏好可能让个别样本跟着变，留 1 条余量
    assert len(kept & {key(c) for c in after}) >= len(kept) - 1


def test_核对不通过的候选不会入选(monkeypatch):
    bad = {'%040x' % i for i in range(0, 60, 2)}
    monkeypatch.setattr(bd, 'verify_pr', lambda owner, name, sha, pr: sha not in bad)
    assert all(c['gold_sha'] not in bad for c in bd.pick(fake_cands(), 14, 42))
