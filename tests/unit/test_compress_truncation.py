"""Compression must refuse a summary truncated by the output-token limit.

The compressed summary REPLACES the entire prior transcript. A summary that
hit the model's output cap (``finish_reason='length'``) is cut off, so
accepting it would silently drop the tail of the history. The summary-body
extractor raises instead, so the caller can retry with a larger budget.
"""

from __future__ import annotations

import pytest

from rath.llm.chat_response import (
    RathLLMAssistantMessage,
    RathLLMChatChoice,
    RathLLMChatResponse,
)
from rath.session.compress import _completion_body


def _response(finish_reason: str, content: str | None) -> RathLLMChatResponse:
    return RathLLMChatResponse(
        id="",
        choices=(
            RathLLMChatChoice(
                index=0,
                finish_reason=finish_reason,  # type: ignore[arg-type]
                message=RathLLMAssistantMessage(role="assistant", content=content),
            ),
        ),
        created=0,
        model="",
        usage=None,
    )


def test_length_finish_is_rejected() -> None:
    with pytest.raises(RuntimeError, match="truncated"):
        _completion_body(_response("length", "partial summary..."))


def test_stop_finish_is_accepted() -> None:
    assert _completion_body(_response("stop", "full summary")) == "full summary"


def test_content_filter_finish_still_accepted() -> None:
    assert _completion_body(_response("content_filter", "x")) == "x"
