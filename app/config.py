# -*- coding: utf-8 -*-
"""配置。脚手架已给全，可直接用。"""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    # LLM
    openai_api_key: str = ''
    openai_base_url: str = ''
    llm_model: str = 'gpt-4o-mini'

    # GitHub
    github_token: str = ''

    # Langfuse
    langfuse_public_key: str = ''
    langfuse_secret_key: str = ''
    langfuse_host: str = 'https://cloud.langfuse.com'

    # 运行约束
    max_depth: int = 3
    max_tokens_per_run: int = 120_000
    cache_dir: Path = Path('./data')

    @property
    def repos_dir(self) -> Path:
        return self.cache_dir / 'repos'

    @property
    def index_dir(self) -> Path:
        return self.cache_dir / 'index'


settings = Settings()
