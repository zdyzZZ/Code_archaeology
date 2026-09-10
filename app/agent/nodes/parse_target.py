# -*- coding: utf-8 -*-
"""解析输入的 GitHub URL

⚠️ 实现你自己写。

职责：把 URL 拆成 repo / file_path / line_range，并确保本地有该 repo 的克隆。

注意：
  - URL 形态不止一种：
      https://github.com/owner/repo/blob/main/path/to/file.py#L12-L30
      https://github.com/owner/repo/blob/<sha>/path/file.py
  - 分支名可能含斜杠（feature/foo），不能简单按 / 切
  - 只需要 blame，不需要完整历史 → 可以考虑 --filter=blob:none 的部分克隆省时间
"""


def parse_target(state: dict) -> dict:
    """TODO"""
    raise NotImplementedError
