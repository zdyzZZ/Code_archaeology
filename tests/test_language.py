# -*- coding: utf-8 -*-
"""报告语言：网页选的 lang 要一路传到 narrate / assess 的系统提示词里。不调真实的 LLM。"""
import pytest
from fastapi.testclient import TestClient

from app.agent import fake_stream
from app.agent.llm import LANGUAGE_RULES, language_rule
from app.agent.nodes import narrate as narrate_node
from app.config import settings
from app.main import app


def test_默认中文():
    assert language_rule(None) == LANGUAGE_RULES['zh']
    assert language_rule('xx') == LANGUAGE_RULES['zh']
    assert language_rule('en') == LANGUAGE_RULES['en']


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, 'fake_agent', True)
    monkeypatch.setattr(fake_stream, 'STEP_DELAY', 0)
    with TestClient(app) as c:
        yield c


def test_lang参数传到astream(client, monkeypatch):
    seen = {}

    async def spy(url, question, thread_id, language='zh'):
        seen['language'] = language
        yield {'narrate': {'report': 'ok'}}

    monkeypatch.setattr(fake_stream, 'astream', spy)
    url = 'https://github.com/psf/requests/blob/main/src/requests/adapters.py#L97-L105'
    with client.stream('GET', '/api/excavate/stream', params={'url': url, 'lang': 'en'}) as r:
        list(r.iter_lines())
    assert seen['language'] == 'en'


def test_不支持的语言返回422(client):
    r = client.get('/api/excavate/stream', params={'url': 'x', 'lang': 'fr'})
    assert r.status_code == 422


def test_narrate把语言要求放进系统提示词(monkeypatch):
    captured = {}

    class FakeLLM:
        def with_structured_output(self, schema):
            return self

        def invoke(self, messages):
            captured['system'] = messages[0][1]
            return narrate_node.NarrateResult(report='report', key_prs=[12, 12, 5, 7, 9])

    monkeypatch.setattr(narrate_node, 'get_llm', lambda: FakeLLM())
    monkeypatch.setattr(narrate_node, 'build_material', lambda state: 'material')
    out = narrate_node.narrate({'issues': [], 'language': 'en'})
    assert captured['system'].endswith(LANGUAGE_RULES['en'])
    assert out == {'report': 'report', 'key_prs': [12, 5, 7]}   # 去重、最多 3 个
