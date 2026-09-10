# -*- coding: utf-8 -*-
"""FastAPI 入口。脚手架已给全。"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import routes
from app.config import settings

WEB = Path(__file__).resolve().parent.parent / 'web'


@asynccontextmanager
async def lifespan(app: FastAPI):
    for d in (settings.repos_dir, settings.index_dir):
        d.mkdir(parents=True, exist_ok=True)
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
