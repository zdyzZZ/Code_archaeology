# -*- coding: utf-8 -*-
"""is_noise_commit 的测试。

启发式判断很容易改坏，而且坏了不报错，只是结果变差，所以分两类测：

1. 造的小仓库：验证每条规则的**逻辑**写对了（每个用例只触发一条规则）
2. requests 的真实提交：验证**阈值**定对了（本地没克隆 requests 时自动跳过）

运行（在项目根目录）：
    python -m pytest tests/test_blame.py -v
"""
from pathlib import Path

import pytest

from app.git.blame import is_noise_commit
from app.git.repo import run


# ---------- 工具函数 ----------

def git(repo: Path, *args: str) -> str:
    return run(['git', *args], cwd=repo)


def commit(repo: Path, message: str, files: dict[str, str]) -> str:
    """写入文件并提交，返回完整 sha。"""
    for name, content in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8', newline='\n')
    git(repo, 'add', '-A')
    git(repo, 'commit', '-q', '-m', message)
    return git(repo, 'rev-parse', 'HEAD').strip()


BASE_CODE = (
    'def get_name(user):\n'
    '    return user.name\n'
)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """一个带初始提交的临时仓库。"""
    git(tmp_path, 'init', '-q')
    git(tmp_path, 'config', 'user.name', 't')
    git(tmp_path, 'config', 'user.email', 't@t')
    git(tmp_path, 'config', 'core.autocrlf', 'false')   # Windows 换行转换会干扰"只改空白"的判断
    commit(tmp_path, 'init', {'app.py': BASE_CODE})
    return tmp_path


# ---------- 1. 造的仓库：每条规则各测一次 ----------

def test_业务提交不是噪声(repo):
    sha = commit(repo, 'fix: handle None', {'app.py': (
        'def get_name(user):\n'
        '    if user is None:\n'
        '        return ""\n'
        '    return user.name\n'
    )})
    assert is_noise_commit(repo, sha) is None


def test_提交说明命中格式化前缀(repo):
    # 内容也有真实改动，确保是"提交说明"这条规则命中，而不是"只改空白"
    sha = commit(repo, 'style: black', {'app.py': BASE_CODE + '\nX = 1\n'})
    assert is_noise_commit(repo, sha) is not None


def test_只改空白是噪声(repo):
    # 提交说明不带任何噪声前缀，只能靠 git show -w 判断
    sha = commit(repo, 'update', {'app.py': (
        'def get_name(user):\n'
        '        return user.name\n'      # 只改了缩进
    )})
    assert is_noise_commit(repo, sha) is not None


def test_merge提交不是噪声(repo):
    main = git(repo, 'rev-parse', '--abbrev-ref', 'HEAD').strip()
    git(repo, 'checkout', '-q', '-b', 'feature')
    commit(repo, 'feat: add helper', {'helper.py': 'def helper():\n    return 1\n'})
    git(repo, 'checkout', '-q', main)
    commit(repo, 'feat: add other', {'other.py': 'Y = 2\n'})
    git(repo, 'merge', '-q', '--no-ff', '-m', 'Merge branch feature', 'feature')
    sha = git(repo, 'rev-parse', 'HEAD').strip()
    assert is_noise_commit(repo, sha) is None


# ---------- 2. requests 的真实提交：验证阈值 ----------

REQUESTS = Path(__file__).resolve().parent.parent / 'data' / 'repos' / 'psf' / 'requests'

REAL_CASES = [
    # (sha, 是否噪声, 说明)
    ('2a6f290b', True,  '自动格式化 #6095'),
    ('f8bec2f7', True,  '迁移到 Ruff，批量改 import #7190'),
    ('8bce583b', False, '移除 Python 2 支持，改了很多文件但有意义'),
    ('4e383642', False, '按 urllib3 版本选择编码'),
    ('1c38e1f5', False, 'Windows 代理绕过'),
    ('01353d3b', False, '反转 urllib3 版本判断，改动很小但有意义'),
    ('561e4b68', False, '加内联类型标注 #7272：有意不算噪声，交给模型在报告里说明'),
]


@pytest.mark.skipif(not REQUESTS.exists(), reason='本地没有克隆 requests')
@pytest.mark.parametrize('short_sha, expect_noise, desc', REAL_CASES, ids=[c[0] for c in REAL_CASES])
def test_真实提交(short_sha, expect_noise, desc):
    sha = git(REQUESTS, 'rev-parse', short_sha).strip()
    reason = is_noise_commit(REQUESTS, sha)
    assert (reason is not None) == expect_noise, '%s（%s）实际返回: %r' % (short_sha, desc, reason)
