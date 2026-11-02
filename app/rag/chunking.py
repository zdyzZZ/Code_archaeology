# -*- coding: utf-8 -*-
"""分块：三种材料用不同的切法。

  - 提交说明：本来就短，整条一块，不切
  - PR / issue 正文：先清洗，再按空行分段；太短的段并到一起，太长的段再切
  - 评论：一条评论就是一个完整的观点，先按"一条一块"，长评论再按段落切

为什么限制单块长度（MAX_CHARS）：rerank 模型一次最多看 512 个 token，超出的部分会被直接截掉；
块太长时，真正相关的那句话可能正好在被截掉的后半段。
为什么合并太短的段（MIN_CHARS）："LGTM"、"Thanks!" 这种单独成块，只会在检索结果里占位置。
"""
import re

MAX_CHARS = 800
MIN_CHARS = 80

_HTML_COMMENT = re.compile(r'<!--.*?-->', re.S)   # PR 模板里的注释和填写说明
_BLANK_LINES = re.compile(r'\n\s*\n')


def clean(text: str) -> str:
    """去掉对检索没用、还会制造重复的内容。"""
    text = (text or '').replace('\r\n', '\n')
    text = _HTML_COMMENT.sub('', text)
    # '>' 开头的行是 GitHub 的引用回复，内容和被引用的那条评论重复
    lines = [l for l in text.split('\n') if not l.lstrip().startswith('>')]
    return '\n'.join(lines).strip()


def _split_long(paragraph: str, max_chars: int) -> list[str]:
    """超长段落按行切，单行还超长就按字数硬切。"""
    out, buf = [], ''
    for line in paragraph.split('\n'):
        while len(line) > max_chars:
            if buf:
                out.append(buf)
                buf = ''
            out.append(line[:max_chars])
            line = line[max_chars:]
        if buf and len(buf) + 1 + len(line) > max_chars:
            out.append(buf)
            buf = line
        else:
            buf = buf + '\n' + line if buf else line
    if buf:
        out.append(buf)
    return out


def split_paragraphs(text: str, max_chars: int = MAX_CHARS, min_chars: int = MIN_CHARS) -> list[str]:
    """按空行分段 -> 太短的往后合并 -> 太长的再切。"""
    paragraphs = [p.strip() for p in _BLANK_LINES.split(text) if p.strip()]
    merged, buf = [], ''
    for p in paragraphs:
        buf = buf + '\n\n' + p if buf else p
        if len(buf) >= min_chars:
            merged.append(buf)
            buf = ''
    if buf:
        # 剩下一点尾巴：并进上一块（不超长的话），否则单独成块
        if merged and len(merged[-1]) + 2 + len(buf) <= max_chars:
            merged[-1] += '\n\n' + buf
        else:
            merged.append(buf)
    chunks = []
    for m in merged:
        chunks += _split_long(m, max_chars) if len(m) > max_chars else [m]
    return chunks


def chunk_commit(message: str) -> list[str]:
    text = (message or '').strip()
    return [text[:MAX_CHARS * 2]] if text else []   # 不切，只防极端长的说明


def chunk_issue_body(body: str) -> list[str]:
    return split_paragraphs(clean(body))


MIN_COMMENT_CHARS = 20   # 'LGTM'、':shipit:'、'Thanks!' 这种没有信息量，实测会挤进检索结果占位置


def chunk_comment(body: str) -> list[str]:
    text = clean(body)
    if len(text) < MIN_COMMENT_CHARS:
        return []
    return [text] if len(text) <= MAX_CHARS else split_paragraphs(text)
