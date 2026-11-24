# -*- coding: utf-8 -*-
"""git log -L 漏掉 blame 指出的提交时的 diff 兜底：commit_hunks、blame 的 orig_path / orig_line、diff_for。

运行（在项目根目录）：
    python -m pytest tests/test_log.py -v
"""
from pathlib import Path

import pytest

from app.agent.nodes.link_context import MISSING_DIFF, blame_origins, diff_for
from app.git.blame import blame
from app.git.log import commit_hunks
from app.git.repo import run


def git(repo: Path, *args: str) -> str:
    return run(['git', *args], cwd=repo)


def commit(repo: Path, message: str, files: dict[str, str]) -> str:
    for name, content in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8', newline='\n')
    git(repo, 'add', '-A')
    git(repo, 'commit', '-q', '-m', message)
    return git(repo, 'rev-parse', 'HEAD').strip()


def numbered(n: int, changed: dict[int, str] | None = None) -> str:
    """第 i 行是 line_i，changed 里的行替换成指定内容。"""
    changed = changed or {}
    return ''.join(changed.get(i, 'line_%d' % i) + '\n' for i in range(1, n + 1))


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, 'init', '-q')
    git(tmp_path, 'config', 'user.name', 't')
    git(tmp_path, 'config', 'user.email', 't@t')
    git(tmp_path, 'config', 'core.autocrlf', 'false')
    commit(tmp_path, 'init', {'a.py': numbered(100)})
    return tmp_path


def test_只取覆盖目标行的hunk(repo):
    sha = commit(repo, 'change two places', {'a.py': numbered(100, {10: 'NEAR', 80: 'FAR'})})
    out = commit_hunks(repo, sha, 'a.py', {10})
    assert '+NEAR' in out
    assert 'FAR' not in out


def test_没有覆盖目标行时返回空(repo):
    sha = commit(repo, 'change', {'a.py': numbered(100, {80: 'FAR'})})
    assert commit_hunks(repo, sha, 'a.py', {10}) == ''


def test_长hunk只留目标行附近(repo):
    # 第 20-70 行全部改掉，形成一个很长的 hunk；目标是第 45 行
    changed = {i: 'NEW_%d' % i for i in range(20, 71)}
    sha = commit(repo, 'rewrite block', {'a.py': numbered(100, changed)})
    out = commit_hunks(repo, sha, 'a.py', {45})
    assert '+NEW_45' in out
    assert '+NEW_37' in out and '+NEW_53' in out        # 前后 8 行
    assert 'NEW_25' not in out and 'NEW_65' not in out
    assert out.startswith('@@ ')


def test_blame给出搬家前的路径和行号(repo):
    old = commit(repo, 'edit line 5', {'a.py': numbered(100, {5: 'EDITED'})})
    git(repo, 'mv', 'a.py', 'b.py')
    git(repo, 'commit', '-q', '-m', 'move')
    rows = blame(repo, 'b.py', 5, 5)
    assert rows[0]['sha'] == old
    assert rows[0]['orig_path'] == 'a.py'
    assert rows[0]['orig_line'] == 5
    # 用旧路径能取到 diff，用现在的路径取不到——这就是要记 orig_path 的原因
    assert '+EDITED' in commit_hunks(repo, old, 'a.py', {5})
    assert commit_hunks(repo, old, 'b.py', {5}) == ''


def test_diff_for三种情况(repo):
    sha = commit(repo, 'edit', {'a.py': numbered(100, {10: 'X'})})
    origins = blame_origins(blame(repo, 'a.py', 10, 10))
    # 1. -L 有：直接用
    assert diff_for(repo, sha, {sha: 'FROM_L'}, origins) == 'FROM_L'
    # 2. -L 没有，blame 有：按行号取 hunk，并注明来源
    out = diff_for(repo, sha, {}, origins)
    assert '+X' in out and 'git log -L 没有覆盖' in out
    # 3. 都没有：写"未能获取"，不写"没有改动"
    assert diff_for(repo, 'f' * 40, {}, origins) == MISSING_DIFF


# ---------- GitHub 请求重试 ----------

def test_github读超时会重试(monkeypatch):
    import httpx
    from app.github import client as gh

    monkeypatch.setattr(gh.time, 'sleep', lambda s: None)
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) < 3:
            raise httpx.ReadTimeout('timed out', request=request)
        return httpx.Response(200, json={'ok': True})

    with httpx.Client(transport=httpx.MockTransport(handler)) as c:
        assert gh._send(c, 'https://api.github.com/x').json() == {'ok': True}
    assert len(calls) == 3


def test_github重试用完后抛出原错误(monkeypatch):
    import httpx
    from app.github import client as gh

    monkeypatch.setattr(gh.time, 'sleep', lambda s: None)

    def handler(request):
        raise httpx.ConnectTimeout('timed out', request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as c:
        with pytest.raises(httpx.ConnectTimeout):
            gh._send(c, 'https://api.github.com/x')
