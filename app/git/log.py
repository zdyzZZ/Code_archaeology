from pathlib import Path
from app.git.repo import run


def commit_message(repo: Path, sha: str) -> str:
    """拿某个 commit 的完整 message（标题 + 正文）。"""
    return run(['git', 'log', '-1', '--format=%B', sha], cwd=repo).strip()