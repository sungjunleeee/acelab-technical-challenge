"""OpenRouter LLM helpers used by every agent stage.

Two primitives:

- ``structured_completion`` — force a model to return data matching a pydantic
  schema via the universally supported "forced tool call" pattern.
- ``tool_calling_loop`` — run an LLM tool-use loop with caps and an optional
  per-call observer (used to drive ``SearchProgress`` events in Stage 3).
"""

from __future__ import annotations

import json
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

DEFAULT_MODEL = "anthropic/claude-sonnet-4.6"


def _client() -> AsyncOpenAI:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set in the environment.")
    return AsyncOpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")


def default_model() -> str:
    return os.environ.get("MODEL", DEFAULT_MODEL)


# ---------------------------------------------------------------------------
# Structured output
# ---------------------------------------------------------------------------


async def structured_completion(
    messages: list[dict[str, Any]],
    response_model: type[T],
    *,
    model: str | None = None,
    temperature: float = 0.0,
) -> T:
    """Return a validated instance of ``response_model``.

    Uses the forced-tool-call pattern (expose the schema as a single tool, force
    the LLM to call it). This works across every provider that supports tool
    use, including Anthropic via OpenRouter, where ``response_format`` may not
    be honored uniformly.
    """
    client = _client()
    schema = response_model.model_json_schema()
    response = await client.chat.completions.create(
        model=model or default_model(),
        messages=messages,
        temperature=temperature,
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "respond",
                    "description": f"Return a structured {response_model.__name__}.",
                    "parameters": schema,
                },
            }
        ],
        tool_choice={"type": "function", "function": {"name": "respond"}},
    )
    tool_calls = response.choices[0].message.tool_calls or []
    if not tool_calls:
        raise RuntimeError(
            f"Expected a forced tool call to 'respond', got none. "
            f"Content: {response.choices[0].message.content!r}"
        )
    return response_model.model_validate_json(tool_calls[0].function.arguments)


# ---------------------------------------------------------------------------
# Tool-calling loop
# ---------------------------------------------------------------------------


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Awaitable[Any]]

    def to_openai_format(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class ToolCallRecord:
    name: str
    args: dict[str, Any]
    iteration: int
    result_summary: str


async def tool_calling_loop(
    messages: list[dict[str, Any]],
    tools: list[Tool],
    *,
    model: str | None = None,
    max_iters: int = 8,
    max_tool_calls: int = 12,
    terminator_tool: str | None = None,
    on_tool_call: Callable[[str, dict[str, Any], Any], None] | None = None,
    temperature: float = 0.3,
) -> tuple[str, list[ToolCallRecord]]:
    """Run an LLM tool-use loop.

    Terminates when any of the following happen:
    - the model returns an assistant turn with no tool calls,
    - ``terminator_tool`` is invoked,
    - ``max_iters`` model turns or ``max_tool_calls`` total invocations.
    """
    client = _client()
    history: list[dict[str, Any]] = list(messages)
    records: list[ToolCallRecord] = []
    tool_count = 0
    by_name = {t.name: t for t in tools}

    for iter_n in range(max_iters):
        response = await client.chat.completions.create(
            model=model or default_model(),
            messages=history,
            tools=[t.to_openai_format() for t in tools],
            temperature=temperature,
        )
        msg = response.choices[0].message
        history.append(_assistant_message_to_dict(msg))

        tool_calls = msg.tool_calls or []
        if not tool_calls:
            return (msg.content or ""), records

        terminate = False
        for tc in tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}

            if name == terminator_tool:
                terminate = True
                history.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": "Acknowledged — finishing searches.",
                    }
                )
                continue

            tool = by_name.get(name)
            if tool is None:
                history.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": f"Error: unknown tool {name!r}.",
                    }
                )
                continue

            try:
                result = await tool.handler(**args)
            except Exception as e:  # surface tool errors back to the model
                history.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": f"Tool error: {type(e).__name__}: {e}",
                    }
                )
                continue

            summary = _summarize_for_transcript(result)
            records.append(
                ToolCallRecord(
                    name=name, args=args, iteration=iter_n, result_summary=summary
                )
            )
            tool_count += 1
            if on_tool_call:
                on_tool_call(name, args, result)

            history.append(
                {"role": "tool", "tool_call_id": tc.id, "content": summary}
            )

            if tool_count >= max_tool_calls:
                terminate = True

        if terminate:
            final = await client.chat.completions.create(
                model=model or default_model(),
                messages=history,
                temperature=temperature,
            )
            return (final.choices[0].message.content or ""), records

    return "", records


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _assistant_message_to_dict(msg: Any) -> dict[str, Any]:
    """Convert an OpenAI ChatCompletionMessage back into the wire format."""
    out: dict[str, Any] = {"role": "assistant", "content": msg.content}
    if msg.tool_calls:
        out["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in msg.tool_calls
        ]
    return out


def _summarize_for_transcript(result: Any) -> str:
    """Compact a tool result to a string for inclusion in the conversation."""
    if isinstance(result, str):
        return result[:8000]
    if isinstance(result, BaseModel):
        return result.model_dump_json()[:8000]
    try:
        return json.dumps(result, default=str)[:8000]
    except Exception:
        return str(result)[:8000]
