from langchain_openai import ChatOpenAI
from app.config import settings


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