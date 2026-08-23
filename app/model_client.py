"""Outbound call to the model API (OpenAI-compatible /v1/chat/completions).

Provider is Ollama by default (local, zero-cost, exposed at
MODEL_API_BASE_URL). Swapping to a hosted provider (OpenAI/Anthropic-via-
compat-shim) should only require changing MODEL_API_BASE_URL/MODEL_API_KEY
in .env, not this code. Reused by 1.5 (response-side interception sits
directly downstream of this call) and later Control actions (retry/
regenerate/route) that need to call the model again.
"""

import os
import time

import httpx
from dotenv import load_dotenv

from app.schemas.chat import ChatCompletionRequest, ChatCompletionResponse, ChatMessage, Choice, Usage

load_dotenv()

# .get()-based, not the bracket-required os.environ[...] pattern app/db.py
# and app/redis_client.py use - both of these are meant to be optional/
# defaulted for a local Ollama target, not hard requirements.
MODEL_API_BASE_URL = os.environ.get("MODEL_API_BASE_URL", "http://localhost:11434/v1").rstrip("/")
MODEL_API_KEY = os.environ.get("MODEL_API_KEY") or None

# Local inference (and Ollama "cloud" model tags) can be slow, especially on
# a cold model load. Distinct from Workload.latency_budget_ms (Fork #4:
# that's governance-overhead budget for evaluators, not the outbound
# model-call timeout).
_TIMEOUT = httpx.Timeout(120.0, connect=5.0)

_client = httpx.AsyncClient(timeout=_TIMEOUT)


class ModelCallError(Exception):
    code: str = "model_call_error"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class ModelUnreachableError(ModelCallError):
    code = "model_unreachable"


class ModelAPIError(ModelCallError):
    code = "model_api_error"

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        super().__init__(f"model API returned {status_code}: {detail}")


class ModelResponseInvalidError(ModelCallError):
    code = "model_response_invalid"


async def call_model(request: ChatCompletionRequest) -> tuple[ChatCompletionResponse, int]:
    """POST to {MODEL_API_BASE_URL}/chat/completions. Returns (parsed
    response, latency_ms measured around just this HTTP call). Raises a
    ModelCallError subclass on any failure - never returns a partial result.
    """
    payload = {
        "model": request.model,
        "messages": [message.model_dump() for message in request.messages],
        "stream": False,  # Fork #4: non-streaming only, enforced here too.
    }
    headers = {"Authorization": f"Bearer {MODEL_API_KEY}"} if MODEL_API_KEY else {}

    start = time.perf_counter()
    try:
        resp = await _client.post(
            f"{MODEL_API_BASE_URL}/chat/completions", json=payload, headers=headers
        )
    except httpx.RequestError as exc:
        raise ModelUnreachableError(f"could not reach {MODEL_API_BASE_URL}: {exc}") from exc
    latency_ms = round((time.perf_counter() - start) * 1000)

    if resp.status_code < 200 or resp.status_code >= 300:
        raise ModelAPIError(resp.status_code, resp.text[:500])

    # Field-by-field construction, not ChatCompletionResponse.model_validate(json):
    # our schema's fields are all required/non-Optional, so a naive
    # model_validate would raise an opaque ValidationError (-> 500) on any
    # small shape difference (e.g. a missing usage block) instead of the
    # clean 502 the router expects for upstream failures.
    try:
        data = resp.json()
        choice_data = data["choices"][0]
        message_data = choice_data["message"]
        usage_data = data.get("usage") or {}
        parsed = ChatCompletionResponse(
            id=data.get("id", f"chatcmpl-{time.time_ns()}"),
            object=data.get("object", "chat.completion"),
            created=data.get("created", int(time.time())),
            model=data.get("model", request.model),
            choices=[
                Choice(
                    index=choice_data.get("index", 0),
                    message=ChatMessage(
                        role=message_data.get("role", "assistant"),
                        content=message_data.get("content", ""),
                    ),
                    finish_reason=choice_data.get("finish_reason") or "stop",
                )
            ],
            usage=Usage(
                prompt_tokens=usage_data.get("prompt_tokens", 0),
                completion_tokens=usage_data.get("completion_tokens", 0),
                total_tokens=usage_data.get("total_tokens", 0),
            ),
        )
    except (KeyError, IndexError, TypeError, ValueError, AttributeError) as exc:
        raise ModelResponseInvalidError(f"unparseable model API response: {exc}") from exc

    return parsed, latency_ms
