"""11 · Dynamic control flow — route between agents with a Selector (if / while).

A `flow.Selector` is an LLM-backed router: given the current session and a set
of self-describing workflows, it returns which one to run next, or a no-op
`flow.EmptyWorkflow` when the task is done. Control flow stays plain Python — you
write the `if` / `while`; the Selector only makes the routing decision.

Run:
    python example/11_dynamic_selector.py
"""

from __future__ import annotations

from _shared import provider_from_env

from rath import flow
from rath.session import Session


def main() -> None:
    provider = provider_from_env()

    selector = flow.Selector(provider)
    billing = flow.Agent(
        "You handle billing questions. Be brief.",
        provider,
        description="Billing, invoices, refunds, payment methods",
    )
    tech = flow.Agent(
        "You solve technical problems. Be brief.",
        provider,
        description="Installation, errors, configuration, troubleshooting",
    )
    wrapup = flow.Agent(
        "You write a one-line closing summary.",
        provider,
        description="Wrap up and produce a final summary",
    )

    # --- if: route to at most one branch, once ---
    print("--- if: single branch ---")
    session = Session.from_user_message("My last invoice was charged twice.").to(
        "local"
    )
    chosen = selector.forward(session, billing, tech)
    if not isinstance(chosen, flow.EmptyWorkflow):
        print("routed to:", chosen.description)
        session = chosen(session)
        print(session.text())

    # --- while: keep routing until the Selector returns an EmptyWorkflow (done) ---
    print("--- while: loop until done ---")
    session = Session.from_user_message(
        "I got an error installing, then I want a summary."
    ).to("local")
    rounds = 0
    while not isinstance(
        nxt := selector.forward(session, tech, billing, wrapup), flow.EmptyWorkflow
    ):
        rounds += 1
        print(f"round {rounds} -> {nxt.description}")
        session = nxt(session)
        if rounds >= 4:  # safety bound for the demo
            break
    print("final:", session.text())


if __name__ == "__main__":
    main()
