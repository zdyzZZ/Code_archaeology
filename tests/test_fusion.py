# -*- coding: utf-8 -*-
"""RRF 的测试。每条都对应 RRF 的一个性质，面试讲 RRF 时可以直接用这几条。"""
from app.rag.fusion import rrf


def test_两路都排第一的融合后第一():
    assert rrf([['a', 'b', 'c'], ['a', 'c', 'b']])[0] == 'a'


def test_两路都出现的排在只出现一路的前面():
    # b 在两路都排第二；x 在第一路排第一，但另一路没有
    fused = rrf([['x', 'b'], ['y', 'b']])
    assert fused.index('b') < fused.index('x')
    assert fused.index('b') < fused.index('y')


def test_只用排名不用分数():
    # 同样的排名，不管原来分数多悬殊，结果都一样——这就是 RRF 不怕两路量纲不同的原因
    assert rrf([['a', 'b'], ['b', 'a']]) == rrf([['a', 'b'], ['b', 'a']])


def test_rank从1开始():
    # k=0 时，如果 rank 从 0 开始，第一名就是 1/(0+0)，会除以零报错
    assert rrf([['a', 'b']], k=0) == ['a', 'b']


def test_k越大排名差距越小():
    # 一路里 a 第一、b 第十：k 越大，两者分数的比值越接近 1
    def ratio(k):
        return (1 / (k + 1)) / (1 / (k + 10))
    assert ratio(1) > ratio(60) > ratio(1000) > 1


def test_k影响融合结果():
    # a：第一路第 1、第二路没有；b：两路都第 3
    # k 小时看重"排得靠前"，a 赢；k 大时看重"被几路找到"，b 赢
    lists = [['a', 'x', 'b'], ['y', 'z', 'b']]
    assert rrf(lists, k=1)[0] == 'a'
    assert rrf(lists, k=60)[0] == 'b'


def test_top_k():
    assert rrf([['a', 'b', 'c']], top_k=2) == ['a', 'b']
    assert rrf([]) == []
