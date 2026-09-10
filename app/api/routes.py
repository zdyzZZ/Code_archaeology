# -*- coding: utf-8 -*-
"""HTTP 层。薄壳，业务全在 agent 里。

TODO:
  - [ ] SSE 流式输出接上 LangGraph 的 astream
  - [ ] HITL：/resume 接口把用户决定写回 checkpoint
  - [ ] 限流（按 IP + 全局），防止 GitHub token 被刷爆
"""
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class ExcavateRequest(BaseModel):
    url: str                      # GitHub 文件链接，可带 #L12-L30
    question: str | None = None   # 可选：具体想问什么


class ExcavateResponse(BaseModel):
    run_id: str
    report: dict


@router.post('/excavate', response_model=ExcavateResponse)
async def excavate(req: ExcavateRequest):
    """同步版考古。先把这个跑通，再做流式。"""
    raise NotImplementedError('TODO: 调 app.agent.graph.run()')


@router.get('/excavate/stream')
async def excavate_stream(url: str):
    """SSE 流式版：把 Agent 每一步推给前端，让访客看见它在想什么。

    TODO: 用 sse_starlette.EventSourceResponse 包 graph.astream()
    """
    raise NotImplementedError


@router.post('/resume')
async def resume(run_id: str, approve: bool):
    """HITL：中断后用户决定要不要继续深挖。

    TODO: 用 checkpointer 恢复到中断点，注入决定后继续
    """
    raise NotImplementedError


@router.get('/samples')
async def samples():
    """首页内置示例。零门槛演示的关键——访客不用自己找 repo。

    TODO: 挑 6-8 个知名开源项目里著名的"怪代码"
          （那些带 // don't remove this, see #1234 注释的片段）
    """
    return {'samples': []}
