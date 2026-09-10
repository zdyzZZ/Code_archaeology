# -*- coding: utf-8 -*-
"""仓库克隆与缓存。脚手架给了大部分，TODO 标注处补完即可。"""
import subprocess
from pathlib import Path

from app.config import settings


def local_path(owner: str, repo: str) -> Path:
    return settings.repos_dir / owner / repo


def ensure_cloned(owner: str, repo: str, ref: str = 'HEAD') -> Path:
    """确保本地有该 repo。已存在则 fetch，不存在则克隆。

    TODO:
      - [ ] 部分克隆省时间：--filter=blob:none
      - [ ] 并发保护：两个请求同时克隆同一 repo 会打架，加文件锁
      - [ ] 磁盘上限：缓存要有淘汰策略，别把服务器塞满
    """
    dst = local_path(owner, repo)
    if dst.exists():
        run(['git', 'fetch', '--quiet'], cwd=dst)
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        run(['git', 'clone', '--quiet',
             'https://github.com/%s/%s.git' % (owner, repo), str(dst)])
    return dst


def run(cmd: list[str], cwd: Path | None = None, timeout: int = 120) -> str:
    """跑 git 命令。统一在这里加超时，别在各处散着写 subprocess。"""
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                       timeout=timeout, encoding='utf-8', errors='replace')
    if p.returncode != 0:
        raise RuntimeError('git 失败: %s\n%s' % (' '.join(cmd), p.stderr[:500]))
    return p.stdout
