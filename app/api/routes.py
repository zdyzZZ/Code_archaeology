# -*- coding: utf-8 -*-
"""HTTP 层。薄壳，业务全在 agent 里。

和 graph 的约定见 docs/v4-接口约定.md：graph 原样 yield LangGraph 的 chunk，
这里负责把 chunk 翻译成网页能直接显示的 SSE 事件。

SSE 事件（event 名 → data）：
  start      {thread_id}
  step       {node, title, lines: [str], depth}
  interrupt  {thread_id, depth, missing}
  report     {markdown, depth, stop_reason, skipped: [...], commits, issues}
  fail       {message}    （不叫 error：浏览器 EventSource 自带的 error 事件是连接断开，会冲突）
  done       {}

TODO（v6 部署前）：
  - [ ] 限流（按 IP + 全局），防止 GitHub token 被刷爆
"""
import inspect
import json
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sse_starlette import EventSourceResponse, ServerSentEvent

from app.config import settings

router = APIRouter()


def _agent():
    """演示模式用假数据，否则用真实的 graph。用到时再导入，演示模式下不加载 graph。"""
    if settings.fake_agent:
        from app.agent import fake_stream as agent
    else:
        from app.agent import graph as agent
    return agent


# ---------- 把 LangGraph 的 chunk 翻译成网页上的一步 ----------

NODE_TITLES = {
    'parse_target': '解析链接',
    'blame': '定位每行最后的提交（git blame）',
    'filter_noise': '过滤格式化等噪声提交',
    'link_context': '拉取关联的 issue / PR',
    'assess': '判断证据够不够',
    'expand_history': '往更早的历史挖一层',
    'narrate': '生成考古报告',
}


def _short(sha: str) -> str:
    return (sha or '')[:8]


def _first_line(text: str) -> str:
    return (text or '').strip().split('\n', 1)[0]


def _describe(node: str, update: dict) -> list[str]:
    """节点返回值 -> 几行给人看的摘要。字段缺失时少显示，不报错。"""
    u = update or {}
    if node == 'parse_target':
        return ['%s/%s · %s 第 %s-%s 行' % (u.get('owner'), u.get('repo'), u.get('file_path'),
                                         u.get('start_line'), u.get('end_line'))]
    if node == 'blame':
        rows = u.get('blame_lines') or []
        shas = list(dict.fromkeys(r.get('sha') for r in rows))
        return ['%d 行代码，涉及 %d 个提交：%s' % (len(rows), len(shas), '、'.join(_short(s) for s in shas))]
    if node == 'filter_noise':
        lines = ['保留：%s' % ('、'.join(_short(s) for s in u.get('new_shas') or []) or '无')]
        for s in u.get('skipped') or []:
            lines.append('跳过 %s %s —— %s' % (_short(s.get('sha')), s.get('summary', ''), s.get('reason', '')))
        return lines
    if node == 'link_context':
        lines = ['%s %s %s' % (_short(c.get('sha')), c.get('date', ''), _first_line(c.get('message')))
                 for c in u.get('commits') or []]
        for i in u.get('issues') or []:
            kind = 'PR' if i.get('is_pr') else 'issue'
            via = '（由 PR #%s 引用）' % i['via_pr'] if i.get('via_pr') else ''
            lines.append('#%s %s：%s%s' % (i.get('number'), kind, i.get('title', ''), via))
        return lines or ['本层没有新的提交']
    if node == 'assess':
        if u.get('enough'):
            return ['够了：%s' % (u.get('stop_reason') or '证据足够')]
        return ['还不够' + ('：%s' % u['missing'] if u.get('missing') else '')]
    if node == 'expand_history':
        return ['进入第 %s 层，候选提交 %d 个' % (u.get('depth'), len(u.get('new_shas') or []))]
    if node == 'narrate':
        return ['报告已生成']
    return ['更新了：%s' % '、'.join(u.keys())] if u else []


def _interrupt_value(chunk: dict) -> dict:
    items = chunk.get('__interrupt__') or ()
    first = items[0] if items else None
    value = getattr(first, 'value', first)
    return value if isinstance(value, dict) else {'missing': str(value)}


def _event(name: str, data: dict) -> ServerSentEvent:
    return ServerSentEvent(event=name, data=json.dumps(data, ensure_ascii=False, default=str))


# thread_id -> 跨"中断前 / 继续后"两段流累计的统计。中断时保留，跑完或出错时删掉
_summaries: dict[str, dict] = {}


async def _translate(chunks: AsyncIterator[dict], thread_id: str) -> AsyncIterator[ServerSentEvent]:
    """把 chunk 流翻译成 SSE 事件流；同时记下 depth / skipped 等，最后随报告一起发出。"""
    summary = _summaries.pop(thread_id, None) or {
        'depth': 0, 'stop_reason': None, 'skipped': [], 'commits': 0, 'issues': 0}
    try:
        async for chunk in chunks:
            if '__interrupt__' in chunk:
                value = _interrupt_value(chunk)
                _summaries[thread_id] = summary   # 等用户选择后，resume 那段流接着累计
                yield _event('interrupt', {'thread_id': thread_id,
                                           'depth': value.get('depth', summary['depth']),
                                           'missing': value.get('missing', '')})
                continue
            for node, update in chunk.items():
                update = update if isinstance(update, dict) else {}
                if 'depth' in update:
                    summary['depth'] = update['depth']
                if 'stop_reason' in update:
                    summary['stop_reason'] = update['stop_reason']
                summary['skipped'] += [{'sha': _short(s.get('sha')), 'summary': s.get('summary', ''),
                                        'reason': s.get('reason', '')} for s in update.get('skipped') or []]
                summary['commits'] += len(update.get('commits') or [])
                summary['issues'] += len(update.get('issues') or [])
                yield _event('step', {'node': node, 'title': NODE_TITLES.get(node, node),
                                      'lines': _describe(node, update), 'depth': summary['depth']})
                if node == 'narrate' and update.get('report'):
                    yield _event('report', {'markdown': update['report'], **summary})
    except NotImplementedError:
        yield _event('fail', {'message': 'graph.astream / aresume 还没实现。可以先在 .env 里设置 '
                                          'FAKE_AGENT=true，用演示模式查看网页效果。'})
    except Exception as e:   # 接口层兜底：把错误显示在网页上，而不是让连接直接断掉
        yield _event('fail', {'message': '%s: %s' % (type(e).__name__, e)})
    yield _event('done', {})


# ---------- 接口 ----------

@router.get('/meta')
async def meta():
    return {'fake_agent': settings.fake_agent}


@router.get('/excavate/stream')
async def excavate_stream(url: str, question: str | None = None):
    """SSE 流式版：把 Agent 每一步推给前端。"""
    thread_id = uuid.uuid4().hex
    return EventSourceResponse(_run_stream('astream', (url, question or None, thread_id), thread_id, start=True))


@router.get('/resume/stream')
async def resume_stream(thread_id: str, approve: bool):
    """HITL：中断后用户决定要不要继续深挖，结果同样以 SSE 推回。"""
    return EventSourceResponse(_run_stream('aresume', (thread_id, approve), thread_id))


HINT_FAKE = '还没写好的话，可以先在 .env 里设置 FAKE_AGENT=true 用演示模式。'


async def _run_stream(func_name: str, args: tuple, thread_id: str, start: bool = False):
    """调用 graph 的 astream / aresume，检查它是否符合约定，再交给 _translate。

    graph 还没写好、签名不对时，用 error 事件告诉网页，而不是让 SSE 连接直接断掉
    （连接断掉时浏览器的 EventSource 会自动重连，等于把整个考古重新跑一遍）。
    """
    if start:
        yield _event('start', {'thread_id': thread_id})
    func = getattr(_agent(), func_name, None)
    if func is None:
        yield _event('fail', {'message': 'graph.py 里还没有 %s 函数。%s' % (func_name, HINT_FAKE)})
        yield _event('done', {})
        return
    try:
        chunks = func(*args)
    except TypeError as e:
        yield _event('fail', {'message': 'graph.%s 的参数和约定不一致：%s' % (func_name, e)})
        yield _event('done', {})
        return
    if not hasattr(chunks, '__aiter__'):
        if inspect.iscoroutine(chunks):
            chunks.close()   # 没 await 的协程要关掉，否则会有 RuntimeWarning
        yield _event('fail', {'message': 'graph.%s 要写成 async 生成器（函数体里用 yield 产出 chunk）。%s'
                                          % (func_name, HINT_FAKE)})
        yield _event('done', {})
        return
    async for ev in _translate(chunks, thread_id):
        yield ev


class ExcavateRequest(BaseModel):
    url: str                      # GitHub 文件链接，可带 #L12-L30
    question: str | None = None   # 可选：具体想问什么


@router.post('/excavate')
async def excavate(req: ExcavateRequest):
    """同步版：跑完一次性返回。演示模式下复用假的 astream。"""
    if settings.fake_agent:
        thread_id = uuid.uuid4().hex
        result: dict = {}
        async for chunk in _agent().astream(req.url, req.question, thread_id):
            if '__interrupt__' in chunk:
                return {'interrupted': True, 'thread_id': thread_id, **_interrupt_value(chunk)}
            for update in chunk.values():
                result.update(update)
    else:
        from app.agent.graph import run
        result = await run_in_threadpool(run, req.url, req.question)
        if '__interrupt__' in result:
            return {'interrupted': True, **_interrupt_value(result)}
    return {
        'interrupted': False,
        'report': result.get('report', ''),
        'depth': result.get('depth'),
        'stop_reason': result.get('stop_reason'),
        'skipped': [{'sha': _short(s.get('sha')), 'summary': s.get('summary', ''), 'reason': s.get('reason', '')}
                    for s in result.get('skipped') or []],
    }


SAMPLES = [
    {
        'title': 'requests：TLS 验证设置为什么要参与连接池选择',
        'repo': 'psf/requests',
        'url': 'https://github.com/psf/requests/blob/main/src/requests/adapters.py#L97-L105',
        'question': '这个 isdir 判断能删吗',
        'hint': '第 0 层就能讲清楚：一个安全修复（#6655）+ 一个性能优化（#6667）',
    },
    {
        'title': 'requests：一整段兼容层 import 的来历',
        'repo': 'psf/requests',
        'url': 'https://github.com/psf/requests/blob/main/src/requests/utils.py#L50-L60',
        'question': '',
        'hint': '大部分行被一次自动格式化（#6095）覆盖，要跳过它往更早的历史挖',
    },
    # TODO（v6）：补到 6-8 个知名项目里的"怪代码"，每个都先实际跑一遍确认效果再加进来
]


@router.get('/samples')
async def samples():
    """首页内置示例。零门槛演示的关键——访客不用自己找 repo。"""
    return {'samples': SAMPLES}
