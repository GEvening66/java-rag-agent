"""LLM 调用封装：对话（DeepSeek）+ 向量化（BGE-M3）+ **失败恢复**。

失败恢复策略：
- 只重试"可恢复错误"：超时 / 连接失败 / 429 限流 / 5xx
- **指数退避 + 抖动**（jitter）——避免所有请求同时重试造成"重试风暴"
- 4xx（参数错误 / 权限问题）**不重试**：重试没有意义，直接抛出
- 客户端超时由 settings.LLM_TIMEOUT 控制
"""
import random
import time

import numpy as np
from openai import (APIConnectionError, APIStatusError, APITimeoutError,
                    OpenAI, RateLimitError)

from . import settings

# max_retries=0：重试逻辑由我们自己实现（显式、可观测、可测试）
_chat = OpenAI(api_key=settings.DEEPSEEK_API_KEY, base_url=settings.DEEPSEEK_BASE_URL,
               timeout=settings.LLM_TIMEOUT, max_retries=0)
_embed = OpenAI(api_key=settings.EMBEDDING_API_KEY, base_url=settings.EMBEDDING_BASE_URL,
                timeout=settings.LLM_TIMEOUT, max_retries=0)

_retry_stats = {"calls": 0, "retries": 0, "failures": 0}


def retry_stats():
    """重试统计（可接进可观测性）。"""
    return dict(_retry_stats)


def is_retryable(exc):
    """判断异常是否值得重试（纯函数，便于单测）。"""
    if isinstance(exc, (APITimeoutError, APIConnectionError, RateLimitError)):
        return True
    if isinstance(exc, APIStatusError):
        return exc.status_code >= 500
    return False


def _with_retry(fn, max_retries=None, base_delay=None, retryable=None):
    """执行 fn，失败按指数退避 + 抖动重试。"""
    max_retries = settings.RETRY_MAX if max_retries is None else max_retries
    base_delay = settings.RETRY_BASE_DELAY if base_delay is None else base_delay
    retryable = is_retryable if retryable is None else retryable

    _retry_stats["calls"] += 1
    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except Exception as exc:          # noqa: BLE001 —— 统一判定是否可重试
            if not retryable(exc):
                raise
            last_exc = exc
        if attempt < max_retries:
            _retry_stats["retries"] += 1
            delay = base_delay * (2 ** attempt) + random.uniform(0, 0.3)  # 抖动
            time.sleep(delay)
    _retry_stats["failures"] += 1
    raise last_exc


def chat(messages, tools=None):
    """一次对话调用，返回 (message, usage)。带 tools 时走 function calling。"""
    kwargs = {"model": settings.DEEPSEEK_MODEL, "messages": messages}
    if tools:
        kwargs["tools"] = tools
    resp = _with_retry(lambda: _chat.chat.completions.create(**kwargs))
    return resp.choices[0].message, resp.usage


def chat_text(messages):
    """一次对话调用，只取文本内容。"""
    msg, _ = chat(messages)
    return msg.content or ""


def embed_texts(texts):
    """批量向量化，返回 (N, dim) 的 float32 矩阵。"""
    resp = _with_retry(
        lambda: _embed.embeddings.create(model=settings.EMBEDDING_MODEL, input=texts)
    )
    return np.array([d.embedding for d in resp.data], dtype="float32")
