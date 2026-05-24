"""Sampling / routing options and OpenAI HTTP identity for chat requests."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Callable, Literal, Mapping

if TYPE_CHECKING:
    from rath.config.store import ConfigStore


@dataclass(frozen=True, kw_only=True, slots=True)
class Provider:
    """LLM routing for ``run_session_loop`` (no ``messages`` / ``tools``).

    ``base_url``, ``api_key``, and ``model`` configure the OpenAI-compatible HTTP
    client when using :class:`~rath.llm.client.RathOpenAIChatClient`. Other
    fields mirror :class:`~rath.llm.chat_request.RathLLMChatRequest` (excluding
    what the loop fills in).

    ``api_key`` may be omitted when callers supply a custom ``executor`` that
    never instantiates :class:`~rath.llm.client.RathOpenAIChatClient`.
    """

    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None
    temperature: float | None = None
    top_p: float | None = None
    max_completion_tokens: int | None = None
    max_tokens: int | None = None
    stop: str | list[str] | None = None
    n: int | None = None
    seed: int | None = None
    frequency_penalty: float | None = None
    presence_penalty: float | None = None
    tool_choice: Literal["auto", "none", "required"] | Mapping[str, Any] | None = None
    parallel_tool_calls: bool | None = None
    response_format: dict[str, Any] | None = None
    logit_bias: dict[str, int] | None = None
    logprobs: bool | None = None
    top_logprobs: int | None = None
    reasoning_effort: str | None = None
    verbosity: str | None = None
    metadata: dict[str, str] | None = None
    user: str | None = None
    store: bool | None = None
    service_tier: str | None = None
    extra_create_args: Mapping[str, Any] = field(
        default_factory=lambda: MappingProxyType({})
    )
    # Retry policy for transient OpenAI-compatible errors. ``None`` means use
    # the built-in defaults in :mod:`rath.llm._retry`.
    retry_max_attempts: int | None = None
    retry_base_seconds: float | None = None
    # Token budget guardrail. When non-None, the **first** completion in a
    # ``run_session_loop`` that pushes ``Session.cumulative_usage`` past the
    # cap invokes ``on_budget_exceeded`` (or emits a single
    # ``logger.warning`` if no callback is set). The guard is latched per
    # session: subsequent completions in the same loop do not re-fire it
    # even if the running total stays above the cap. Callers that want to
    # abort the loop are expected to raise
    # :class:`BudgetExceededError` from the callback on that first call.
    budget_total_tokens: int | None = None
    on_budget_exceeded: Callable[..., None] | None = None
    # Which adapter the default loop should construct when no executor is
    # passed. ``None`` (default) means OpenAI-compatible. Setting to
    # ``"anthropic"`` selects
    # :class:`~rath.llm.anthropic_client.RathAnthropicChatClient`.
    provider_kind: Literal["openai", "anthropic"] | None = None

    def __str__(self) -> str:
        return self.model if self.model is not None else "(no model)"

    def __repr__(self) -> str:
        return self.__str__()

    @classmethod
    def from_config(
        cls,
        name: str | None = None,
        *,
        store: "ConfigStore | None" = None,
        **overrides: Any,
    ) -> "Provider":
        """Build a :class:`Provider` from ``~/.openrath/config.json``.

        Looks up ``name`` (or ``llm.default_provider`` when ``name=None``)
        under ``llm.providers``, then constructs a :class:`Provider` whose
        fields come from the entry. Any explicit ``overrides`` win — pass
        e.g. ``Provider.from_config("openai-main", api_key="ad-hoc")`` to
        rotate one field without touching the on-disk file.

        Lazy-imports :mod:`rath.config` so that ``import rath.llm`` never
        touches the filesystem.

        Raises :class:`KeyError` when the named provider is missing; the
        message lists what is available.
        """
        from rath.config.store import ConfigStore  # local import — see docstring

        s = store or ConfigStore.load()
        entry = s.get_llm_provider(name)
        base = cls(
            provider_kind=entry.provider_kind,
            model=entry.model,
            api_key=entry.api_key,
            base_url=entry.base_url,
            temperature=entry.temperature,
            max_tokens=entry.max_tokens,
        )
        if not overrides:
            return base
        return replace(base, **overrides)


__all__ = ["Provider"]
