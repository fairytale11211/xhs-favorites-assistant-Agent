import re
import time
from typing import Any, Optional

from openai import OpenAI


class LLMCallError(Exception):
    pass


def _extract_message_content(response):
    if response is None:
        return None
    choices = getattr(response, "choices", None)
    if not choices:
        return None
    message = getattr(choices[0], "message", None)
    if message is None:
        return None
    return getattr(message, "content", None)


def _friendly_llm_error(raw_error: str) -> str:
    text = (raw_error or "").lower()
    if "timeout" in text:
        return "请求超时，可能是网络不稳定或模型服务响应较慢"
    if "connection" in text or "connect" in text:
        return "网络连接失败，暂时无法访问模型服务"
    if "429" in text or "rate limit" in text:
        return "请求过于频繁，触发了模型接口限流"
    if "nonetype" in text or "空响应" in text:
        return "模型服务返回了空/异常响应（上游接口偶发抖动，通常重试即可恢复）"
    return f"模型服务调用异常（{raw_error}）"


class OpenAICompatibleClient:
    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str,
        max_retries: int = 3,
        request_timeout: float = 30.0,
    ):
        self.model = model
        self.client = OpenAI(api_key=api_key, base_url=base_url, timeout=request_timeout, max_retries=0)
        self.max_retries = max_retries

    def _call(self, messages: list) -> str:
        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    stream=False,
                    temperature=0.3,
                )
                content = _extract_message_content(response)
                if content is not None and content.strip():
                    return content
                last_error = "空响应"
            except Exception as e:
                last_error = str(e)
            if attempt < self.max_retries:
                time.sleep(1.5 * attempt)
        raise LLMCallError(_friendly_llm_error(last_error))

    def generate(self, prompt: str, system_prompt: str) -> str:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]
        return self._call(messages)


def build_llm_client(llm_config: Optional[dict[str, str]]) -> OpenAICompatibleClient:
    if not llm_config or not llm_config.get("api_key"):
        raise LLMCallError("未配置 LLM API Key，请先在设置中填写 BYOK 密钥")
    return OpenAICompatibleClient(
        model=llm_config.get("model_id") or "deepseek-ai/DeepSeek-V4-Flash-0731",
        api_key=llm_config["api_key"],
        base_url=llm_config.get("base_url") or "https://api-inference.modelscope.cn/v1",
    )


def verify_llm_config(llm_config: dict[str, str]) -> dict[str, Any]:
    client = build_llm_client(llm_config)
    reply = client._call([{"role": "user", "content": "Reply with OK only."}])
    return {"ok": True, "reply": reply.strip()[:50]}
