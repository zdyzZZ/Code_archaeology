# -*- coding: utf-8 -*-
"""FastAPI 入口。脚手架已给全。"""
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import routes
from app.config import settings

WEB = Path(__file__).resolve().parent.parent / 'web'


def _warm_up_models():
    """提前加载检索模型。第一次 import torch + 加载模型在 Windows 上实测要接近 1 分钟，
    放到第一个请求里，网页会像卡死一样；所以服务一启动就在后台线程里加载，不挡启动。"""
    try:
        if settings.retrieval_mode in ('vector', 'hybrid', 'hybrid_rerank'):
            from app.rag.vector import get_model
            get_model()
        if settings.retrieval_mode == 'hybrid_rerank':
            from app.rag.rerank import get_model as get_reranker
            get_reranker()
        print('[startup] 检索模型已就绪')
    except Exception as e:   # 预热失败不影响服务，真正用到时会再加载一次并报出错误
        print('[startup] 检索模型预热失败：%s' % e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    for d in (settings.repos_dir, settings.index_dir):
        d.mkdir(parents=True, exist_ok=True)
    if not settings.fake_agent:
        threading.Thread(target=_warm_up_models, daemon=True).start()
    yield


app = FastAPI(title='Code Archaeologist', lifespan=lifespan)
app.include_router(routes.router, prefix='/api')

if WEB.exists():
    app.mount('/static', StaticFiles(directory=WEB), name='static')

    @app.get('/')
    def index():
        return FileResponse(WEB / 'index.html')


@app.get('/healthz')
def healthz():
    return {'ok': True}
