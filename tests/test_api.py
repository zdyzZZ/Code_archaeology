# -*- coding: utf-8 -*-
"""接口层测试：用演示模式（fake_stream）跑完整的 SSE 流程，不碰 git / GitHub / LLM。

只测接口层自己的逻辑：chunk 翻译成事件、interrupt → resume、出错时给 fail 事件。
graph 本身对不对，要用真实例子跑。

运行：python -m pytest tests/test_api.py -v
"""
import json

import pytest
from fastapi.testclient import TestClient

from app.agent import fake_stream
from app.config import settings
from app.main import app

ADAPTERS = 'https://github.com/psf/requests/blob/main/src/requests/adapters.py#L97-L105'
UTILS = 'https://github.com/psf/requests/blob/main/src/requests/utils.py#L50-L60'


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, 'fake_agent', True)
    monkeypatch.setattr(fake_stream, 'STEP_DELAY', 0)
    with TestClient(app) as c:
        yield c


def sse(client, path: str, params: dict) -> list[tuple[str, dict]]:
    """请求一个 SSE 接口，返回 [(事件名, data), ...]。"""
    events, name = [], None
    with client.stream('GET', path, params=params) as r:
        assert r.status_code == 200
        for line in r.iter_lines():
            if line.startswith('event:'):
                name = line.split(':', 1)[1].strip()
            elif line.startswith('data:') and name:
                events.append((name, json.loads(line.split(':', 1)[1].strip())))
                name = None
    return events


def names(events):
    return [n for n, _ in events]


def test_samples(client):
    data = client.get('/api/samples').json()
    assert len(data['samples']) >= 2
    assert client.get('/api/meta').json() == {'fake_agent': True}


def test_一次跑完(client):
    events = sse(client, '/api/excavate/stream', {'url': ADAPTERS})
    assert names(events)[0] == 'start'
    assert names(events)[-2:] == ['report', 'done']
    assert 'fail' not in names(events)
    steps = [d['node'] for n, d in events if n == 'step']
    assert steps == ['parse_target', 'blame', 'filter_noise', 'link_context', 'assess', 'narrate']
    report = dict(events)['report']
    assert report['depth'] == 0 and report['stop_reason'] == '模型判断证据足够'


def test_中断后继续(client):
    events = sse(client, '/api/excavate/stream', {'url': UTILS})
    assert names(events)[-2:] == ['interrupt', 'done']
    thread_id = dict(events)['start']['thread_id']
    assert dict(events)['interrupt'] == {'thread_id': thread_id, 'depth': 1,
                                         'missing': 'quote、urlparse、proxy_bypass 等导入的最初来源还没找到'}

    resumed = sse(client, '/api/resume/stream', {'thread_id': thread_id, 'approve': 'true'})
    assert names(resumed)[-2:] == ['report', 'done']
    assert '1c38e1f5' in dict(resumed)['report']['markdown']


def test_中断后停止(client):
    thread_id = dict(sse(client, '/api/excavate/stream', {'url': UTILS}))['start']['thread_id']
    resumed = sse(client, '/api/resume/stream', {'thread_id': thread_id, 'approve': 'false'})
    report = dict(resumed)['report']
    assert report['stop_reason'] == '循环次数达到上限'
    assert '还没有找到' in report['markdown']


def test_中断前跳过的提交也出现在最终报告里(client):
    thread_id = dict(sse(client, '/api/excavate/stream', {'url': UTILS}))['start']['thread_id']
    report = dict(sse(client, '/api/resume/stream', {'thread_id': thread_id, 'approve': 'true'}))['report']
    # 2a6f290b、f8bec2f7 都是在中断之前跳过的，继续之后的报告里也要有
    assert [s['sha'] for s in report['skipped']] == ['2a6f290b', 'f8bec2f7']
    assert report['depth'] == 2
    assert report['commits'] == 8   # 中断前 5 个 + 继续后 3 个


def test_找不到的thread_id给出fail而不是断开(client):
    events = sse(client, '/api/resume/stream', {'thread_id': 'nope', 'approve': 'true'})
    assert names(events) == ['fail', 'done']


def test_同步接口(client):
    data = client.post('/api/excavate', json={'url': ADAPTERS}).json()
    assert data['interrupted'] is False and '#6655' in data['report']
    data = client.post('/api/excavate', json={'url': UTILS}).json()
    assert data['interrupted'] is True and data['depth'] == 1
