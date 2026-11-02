# -*- coding: utf-8 -*-
"""配置。脚手架已给全，可直接用。"""
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent       # 项目根目录
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / '.env', extra='ignore')

    # LLM
    openai_api_key: str = ''
    openai_base_url: str = ''
    llm_model: str = ''

    # GitHub
    github_token: str = ''

    # Langfuse
    langfuse_public_key: str = ''
    langfuse_secret_key: str = ''
    langfuse_host: str = 'https://cloud.langfuse.com'

    # 运行约束
    max_depth: int = 3
    max_tokens_per_run: int = 120_000
    cache_dir: Path = ROOT / 'data'
    # 最大循环硬约束
    max_absolute_depth: int = 6
    # 检索（v5）
    # off：不检索，PR 正文按位置截断（v4 的做法，评测时当基线）
    # bm25 / vector：只用一路；hybrid：两路 + RRF；hybrid_rerank：再加 Cross-Encoder 重排
    retrieval_mode: Literal['off', 'bm25', 'vector', 'hybrid', 'hybrid_rerank'] = 'hybrid_rerank'
    retrieve_top_k: int = 8          # 最后交给 narrate 几段
    retrieve_candidates: int = 20    # 每一路召回几段、重排前留几段
    # 两个模型都要能处理中文：用户问题是中文，PR 讨论是英文
    embedding_model: str = 'intfloat/multilingual-e5-small'
    rerank_model: str = 'BAAI/bge-reranker-base'

    # 演示模式：接口改用 app/agent/fake_stream.py 的假数据，不碰 git / GitHub / LLM
    # 用于开发网页；graph.astream 写好后关掉
    fake_agent: bool = False

    @property
    def repos_dir(self) -> Path:
        return self.cache_dir / 'repos'

    @property
    def index_dir(self) -> Path:
        return self.cache_dir / 'index'

    @property
    def github_cache_dir(self) -> Path:
        return self.cache_dir / 'cache' / 'github'


settings = Settings()
