from langchain_openai import ChatOpenAI
from app.config import settings


# 输出语言。提示词本身是中文，但 v5 之后材料里有大量英文 PR 讨论，
# 不明确指定的话模型会跟着材料用英文写——所以每次调用都在系统提示词末尾加上这一段。
LANGUAGE_RULES = {
    'zh': ('## 输出语言\n用简体中文写。引用英文讨论时，用中文转述意思，关键的英文原句或术语可以保留在引号里。'
           '代码、函数名、参数名、提交 sha、#编号一律保持原样，不要翻译。'),
    'en': ('## Output language\nWrite in English. Keep code, function names, parameter names, '
           'commit SHAs and #numbers exactly as they are.'),
}


def language_rule(language: str | None) -> str:
    """state 里没有 language（比如 v5 之前的调用方）时默认中文。"""
    return LANGUAGE_RULES.get(language or 'zh', LANGUAGE_RULES['zh'])


def get_llm(temperature: float | None = None):
    kwargs = {}
    if temperature is not None:
        kwargs['temperature'] = temperature
    return ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url or None,
        **kwargs,
    )