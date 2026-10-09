"""模型访问边界：按需创建客户端，统一超时和对外错误信息。"""

import os
from pathlib import Path

from dotenv import load_dotenv
from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AsyncOpenAI,
    OpenAI,
    RateLimitError,
)

load_dotenv(Path(__file__).with_name(".env"))


class ModelServiceError(Exception):
    """只携带可以安全返回给客户端的信息，不携带密钥或上游响应。"""

    def __init__(self, detail: str, status_code: int = 502):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def model_config():
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    model = (os.getenv("MODEL") or "").strip()
    if not api_key or not model:
        raise ModelServiceError("模型服务未配置，请设置 OPENAI_API_KEY 和 MODEL", 503)

    config = {"api_key": api_key, "timeout": 20.0, "max_retries": 1}
    base_url = (os.getenv("OPENAI_BASE_URL") or "").strip()
    if base_url:
        config["base_url"] = base_url
    return config, model


def public_model_error(exc: APIError):
    # APITimeoutError 是 APIConnectionError 的子类，要先判断超时。
    if isinstance(exc, APITimeoutError):
        return ModelServiceError("模型服务响应超时，请稍后重试", 504)
    if isinstance(exc, APIConnectionError):
        return ModelServiceError("暂时无法连接模型服务，请稍后重试", 503)
    if isinstance(exc, RateLimitError):
        return ModelServiceError("模型服务繁忙或额度不足，请稍后重试", 503)
    return ModelServiceError("模型服务请求失败，请检查服务配置或稍后重试", 502)


async def create_chat_completion(**kwargs):
    config, model = model_config()
    try:
        async with AsyncOpenAI(**config) as client:
            return await client.chat.completions.create(model=model, **kwargs)
    except APIError as exc:
        raise public_model_error(exc) from None


def create_sync_chat_completion(**kwargs):
    config, model = model_config()
    try:
        with OpenAI(**config) as client:
            return client.chat.completions.create(model=model, **kwargs)
    except APIError as exc:
        raise public_model_error(exc) from None
