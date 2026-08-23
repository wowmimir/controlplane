"""OpenAI-compatible request/response schemas for /v1/chat/completions.

Body shape matches OpenAI's chat/completions exactly (per
.agents/prompts/1.1-openai-compatible-endpoint-plan.md) - no ControlPlane
fields here. workload_id/session_id travel as headers, parsed in the router.
"""

from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessage]


class Usage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class Choice(BaseModel):
    index: int
    message: ChatMessage
    finish_reason: str


class ChatCompletionResponse(BaseModel):
    id: str
    object: str
    created: int
    model: str
    choices: list[Choice]
    usage: Usage
