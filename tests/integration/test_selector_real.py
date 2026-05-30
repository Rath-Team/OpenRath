"""Real-LLM Selector routing: picks the obvious branch (marked, opt-in)."""

from __future__ import annotations

import pytest

from rath import flow
from rath.session import Session

pytestmark = pytest.mark.live_llm


def _provider():  # type: ignore[no-untyped-def]
    from rath.llm import Provider

    return Provider.from_config()


def test_selector_routes_to_obvious_branch_real() -> None:
    provider = _provider()
    selector = flow.Selector(provider)
    billing = flow.Agent("Billing help.", provider, description="Billing and invoices")
    tech = flow.Agent("Tech help.", provider, description="Technical troubleshooting")

    chosen = selector.forward(
        Session.from_user_message("I was double-charged on my invoice."),
        billing,
        tech,
    )
    assert chosen is billing
