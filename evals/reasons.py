# -*- coding: utf-8 -*-
"""理由标注：读写 evals/reasons.json，以及"证据原文是否出现在一段文本里"的匹配。

一条标注（按样本 id）：
    id / repo / file / start / end / gold_pr / code   从 dataset.jsonl 抄过来，方便审核时对照
    has_reason   讨论里能不能找到"为什么"。false 的样本不参与理由类指标
    question     中文问题，像读这段代码的开发者会问的那样；不能把答案写进问题里
    reason       真正的理由，1~2 句中文
    location     理由在哪：commit（只有提交说明）/ pr_body / issue / comments
    evidence     [{source, url, quote}]，quote 是英文原文的逐字摘录
    reviewed     人工审核过才算数；run_eval 默认只用 reviewed=true 的
    note         起草脚本或审核人的备注
"""
import json
import re
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REASONS = ROOT / 'reasons.json'


def load_reasons() -> dict[int, dict]:
    if not REASONS.exists():
        return {}
    return {r['id']: r for r in json.loads(REASONS.read_text(encoding='utf-8'))}


def save_reasons(reasons: dict[int, dict]) -> None:
    rows = [reasons[k] for k in sorted(reasons)]
    REASONS.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def norm(text: str) -> str:
    """比较前统一：小写、去掉 markdown 引用符号、空白压成一个空格。"""
    text = re.sub(r'^\s*>+\s?', '', text or '', flags=re.M)
    return re.sub(r'\s+', ' ', text).strip().lower()


def quote_found(quote: str, text: str, min_len: int = 60) -> bool:
    """quote 是否出现在 text 里。

    先看归一化后是否直接包含；不包含时看最长公共子串：材料会被截断、分块，
    摘录可能只有一部分落进来，连续 min_len 个字符一致就算（摘录本身更短时要求整段一致）。
    """
    q, t = norm(quote), norm(text)
    if not q or not t:
        return False
    if q in t:
        return True
    m = SequenceMatcher(None, q, t, autojunk=False).find_longest_match(0, len(q), 0, len(t))
    return m.size >= min(len(q), min_len)


def any_quote_found(evidence: list[dict], text: str) -> bool:
    return any(quote_found(e['quote'], text) for e in evidence)
