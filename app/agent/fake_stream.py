# -*- coding: utf-8 -*-
"""演示模式：产出和 graph.astream(stream_mode='updates') 格式完全一样的假 chunk。

用途：
  - graph.astream / aresume 还没写好时，网页和接口照样能开发、能演示
  - 你实现 graph 时可以对照这里，看每个 chunk 长什么样

开启：.env 里加 FAKE_AGENT=true。数据取自之前真实运行 psf/requests 的结果，做了删减。
"""
import asyncio
import re

from langgraph.types import Interrupt

STEP_DELAY = 0.5   # 每一步之间停一下，网页上才看得出"一步一步"的效果

# thread_id -> 这次演示走的是哪个剧本，resume 时要用
_threads: dict[str, str] = {}


def _target(url: str) -> dict:
    m = re.search(r'github\.com/([^/]+)/([^/]+)/blob/[^/]+/([^#?]+)(?:#L(\d+)(?:C\d+)?(?:-L(\d+))?)?', url)
    if not m:
        return {'owner': 'psf', 'repo': 'requests', 'file_path': 'src/requests/adapters.py',
                'start_line': 97, 'end_line': 105}
    owner, repo, path, start, end = m.groups()
    start = int(start or 1)
    return {'owner': owner, 'repo': repo, 'file_path': path,
            'start_line': start, 'end_line': int(end or start)}


def _sha(prefix: str) -> str:
    return (prefix * 5)[:40]


def _commit(prefix: str, date: str, message: str) -> dict:
    return {'sha': _sha(prefix), 'date': date, 'author': 'demo', 'message': message, 'diff': '（演示数据）'}


def _issue(number: int, title: str, sha_prefix: str, is_pr: bool = True, via_pr: int | None = None) -> dict:
    return {'number': number, 'title': title, 'is_pr': is_pr, 'from_sha': _sha(sha_prefix),
            'via_pr': via_pr, 'body': '（演示数据）', 'url': '', 'refs': []}


# ---------- 剧本 1：adapters，第 0 层就够了 ----------

def _adapters_steps(target: dict) -> list[dict]:
    lines = [{'line': target['start_line'] + i, 'sha': _sha('c0813a2d' if i < 5 else '9a40d127'), 'code': ''}
             for i in range(9)]
    return [
        {'parse_target': {**target, 'repo_path': ''}},
        {'blame': {'blame_lines': lines, 'new_shas': [_sha('c0813a2d'), _sha('9a40d127')], 'depth': 0}},
        {'filter_noise': {'new_shas': [_sha('c0813a2d'), _sha('9a40d127')], 'skipped': []}},
        {'link_context': {
            'commits': [
                _commit('c0813a2d', '2024-03-03', 'Use TLS settings in selecting connection pool'),
                _commit('9a40d127', '2024-05-15', 'Avoid reloading root certificates to improve concurrent performance (#6667)'),
            ],
            'issues': [
                _issue(6655, 'Use TLS settings in selecting connection pool', 'c0813a2d'),
                _issue(6667, 'Avoid reloading root certificates to improve concurrent performance', '9a40d127'),
            ],
        }},
        {'assess': {'enough': True, 'missing': '', 'stop_reason': '模型判断证据足够'}},
        {'narrate': {'report': ADAPTERS_REPORT}},
    ]


ADAPTERS_REPORT = """> 演示数据：以下内容是预先写好的，不是实时生成的。

### 时间线

- **2024-03-03，c0813a2d / PR #6655**：加入 `cert_reqs`，`verify=False` 时为 `CERT_NONE`，否则为 `CERT_REQUIRED`。PR 说明：同一主机先发起 `verify=False` 请求、再发起需要验证的请求时，连接池可能复用未经 TLS 验证的连接。
- **2024-05-15，9a40d127 / PR #6667**：字符串形式的 `verify` 按路径区分，文件传给 `ca_certs`，目录传给 `ca_cert_dir`；目的是避免并发请求时重复加载根证书。

### 结论

**不能删**：这段代码负责把 TLS 验证设置交给连接池，避免复用未验证的连接（#6655），并按 CA 路径类型传参（#6667）。
"""


# ---------- 剧本 2：utils，挖到上限时中断，问用户要不要继续 ----------

def _utils_steps_before_interrupt(target: dict) -> list[dict]:
    lines = [{'line': target['start_line'] + i,
              'sha': _sha('2a6f290b' if i not in (2, 4) else ('01353d3b' if i == 2 else '561e4b68')), 'code': ''}
             for i in range(11)]
    return [
        {'parse_target': {**target, 'repo_path': ''}},
        {'blame': {'blame_lines': lines,
                   'new_shas': [_sha('2a6f290b'), _sha('01353d3b'), _sha('561e4b68')], 'depth': 0}},
        {'filter_noise': {
            'new_shas': [_sha('01353d3b'), _sha('561e4b68')],
            'skipped': [{'sha': _sha('2a6f290b'), 'summary': 'Add automatic code formatting to Requests (#6095)',
                         'reason': '提交说明包含formatting'}],
        }},
        {'link_context': {
            'commits': [
                _commit('01353d3b', '2024-07-23', 'Invert major version check'),
                _commit('561e4b68', '2026-05-03', 'Add inline types to Requests (#7272)'),
            ],
            'issues': [
                _issue(6757, 'Test on urllib3 1.26.x', '01353d3b'),
                _issue(6734, 'requests 2.32.3 & urllib3 1.26.18 issue with unicode put', '01353d3b',
                       is_pr=False, via_pr=6757),
                _issue(7272, 'Add inline types to Requests', '561e4b68'),
            ],
        }},
        {'assess': {'enough': False, 'missing': '9 行指向格式化提交 2a6f290b，需要更早的历史'}},
        {'expand_history': {'new_shas': [_sha('f8bec2f7'), _sha('4e383642'), _sha('8bce583b'), _sha('2aab9a9a')],
                            'depth': 1}},
        {'filter_noise': {
            'new_shas': [_sha('4e383642'), _sha('8bce583b'), _sha('2aab9a9a')],
            'skipped': [{'sha': _sha('f8bec2f7'), 'summary': 'Fix CI and build failures (#7190)',
                         'reason': '疑似批量机械修改：修改 19 个文件，平均每文件改动 7.6 行'}],
        }},
        {'link_context': {
            'commits': [
                _commit('4e383642', '2024-07-18', 'Add conditional string encoding based on urllib3 major version'),
                _commit('8bce583b', '2022-03-25', 'Farewell, sweet Concorde!'),
                _commit('2aab9a9a', '2018-12-29', 'Remove internal use of unnecessary compat shim for OrderedDict'),
            ],
            'issues': [_issue(6091, 'Remove support for Python 2.7, 3.6 and Pypy3.6', '8bce583b')],
        }},
        {'assess': {'enough': False,
                    'missing': 'quote、urlparse、proxy_bypass 等导入的最初来源还没找到'}},
        {'__interrupt__': (Interrupt(value={
            'depth': 1, 'missing': 'quote、urlparse、proxy_bypass 等导入的最初来源还没找到'}),)},
    ]


def _utils_steps_continue() -> list[dict]:
    return [
        {'expand_history': {'new_shas': [_sha('7e297ed9'), _sha('1c38e1f5'), _sha('40402cd0')], 'depth': 2}},
        {'filter_noise': {'new_shas': [_sha('7e297ed9'), _sha('1c38e1f5'), _sha('40402cd0')], 'skipped': []}},
        {'link_context': {
            'commits': [
                _commit('7e297ed9', '2018-02-04', 'Separate collections from collections.abc'),
                _commit('1c38e1f5', '2017-04-20', 'proxy bypass on Windows without DNS lookups'),
                _commit('40402cd0', '2016-10-27', 'adding rewind for re-POST bodies'),
            ],
            'issues': [
                _issue(3979, 'proxy bypass on Windows without DNS lookups', '1c38e1f5'),
                _issue(3976, "Don't use `urllib.proxy_bypass` on Windows", '1c38e1f5', is_pr=False, via_pr=3979),
            ],
        }},
        {'assess': {'enough': True, 'missing': '', 'stop_reason': '模型判断证据足够'}},
        {'narrate': {'report': UTILS_REPORT_CONTINUED}},
    ]


def _utils_steps_stop() -> list[dict]:
    return [
        {'assess': {'enough': True, 'stop_reason': '循环次数达到上限'}},
        {'narrate': {'report': UTILS_REPORT_STOPPED}},
    ]


UTILS_REPORT_CONTINUED = """> 演示数据：以下内容是预先写好的，不是实时生成的。

### 时间线

- **2017-04，1c38e1f5 / PR #3979，issue #3976**：加入 `proxy_bypass_environment` 和 `getproxies_environment`。Windows 上 `urllib.proxy_bypass` 会做 DNS 查询，可能带来延迟和 DNS 泄露。
- **2022-04，2a6f290b / #6095（已跳过）**：自动格式化，只调整了导入的排版，不是原因。
- **2024-07，4e383642、01353d3b / PR #6757，issue #6734**：引入 urllib3 主版本判断，后改为 `is_urllib3_1`，处理 urllib3 1.x 下非 ASCII 请求挂起的问题。

### 结论

**不能整体删除**：代理相关导入来自 #3976 的 Windows DNS 问题，`is_urllib3_1` 用于 urllib3 1.x/2.x 的兼容。
"""

UTILS_REPORT_STOPPED = """> 演示数据：以下内容是预先写好的，不是实时生成的。

### 时间线

- **2022-04，2a6f290b / #6095（已跳过）**：自动格式化，只调整了导入的排版，不是原因。
- **2024-07，4e383642、01353d3b / PR #6757，issue #6734**：引入 urllib3 主版本判断，后改为 `is_urllib3_1`。

### 证据边界

按你的选择，挖到第 1 层就停止了。`quote`、`urlparse`、`proxy_bypass` 等导入的最初来源**还没有找到**。

### 结论

`is_urllib3_1` 不能删；其余导入是否可删，现有证据不足以判断。
"""


async def _play(steps: list[dict]):
    for chunk in steps:
        await asyncio.sleep(STEP_DELAY)
        yield chunk


async def astream(url: str, question: str | None, thread_id: str):
    target = _target(url)
    if target['file_path'].endswith('utils.py'):
        _threads[thread_id] = 'utils'
        steps = _utils_steps_before_interrupt(target)
    else:
        steps = _adapters_steps(target)
    async for chunk in _play(steps):
        yield chunk


async def aresume(thread_id: str, approve: bool):
    if _threads.pop(thread_id, None) != 'utils':
        raise ValueError('找不到这个 thread_id 的中断记录：%s' % thread_id)
    async for chunk in _play(_utils_steps_continue() if approve else _utils_steps_stop()):
        yield chunk
