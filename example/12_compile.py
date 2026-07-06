"""12 · Workflow compile — static resource manifest & lifecycle (no LLM key).

`Workflow.compile()` is OpenRath's torch-like static pass: before a workflow
runs, it walks the module tree and produces a `ResourceManifest` of every
reachable provider, memory binding, and agent — plus any `Selector` nodes,
recorded as *dynamic* (their runtime routing is decided by the model, never
guessed). Use it to:

  * inspect the static graph (`cw.manifest`, `repr(cw)`),
  * fail fast before a run (`cw.validate()` — offline, no model call),
  * acquire/release planned resources deterministically (`with wf.compile():`).

Compiling runs no model and materializes no session, so this needs **no key**.

Run:
    python example/12_compile.py
"""

from __future__ import annotations

from rath import flow
from rath.flow.agent_param import AgentParam
from rath.llm import Provider
from rath.session import Session


class ResearchTeam(flow.Workflow):
    """A tiny nested workflow: a coordinator with two specialist sub-agents."""

    def __init__(self) -> None:
        super().__init__(description="research team")
        # Nested Workflow children register into the module tree (torch-like).
        self.triage = _Specialist("Triage quickly.", "gpt-5.5")
        self.deep = _Specialist("Answer in depth.", "claude-sonnet-4-6")
        # A leaf AgentParam registered directly on this workflow.
        self.summarizer = AgentParam(
            agent_session=Session.from_agent_prompt("Summarize the team's findings."),
            provider=Provider(model="gpt-5.5", api_key="sk-example"),
        )

    def forward(self, session: Session) -> Session:  # pragma: no cover - demo only
        return session


class _Specialist(flow.Workflow):
    def __init__(self, prompt: str, model: str) -> None:
        super().__init__(description=prompt)
        self.agent = AgentParam(
            agent_session=Session.from_agent_prompt(prompt),
            provider=Provider(model=model, api_key="sk-example"),
        )

    def forward(self, session: Session) -> Session:  # pragma: no cover - demo only
        return session


def main() -> None:
    team = ResearchTeam()

    # 1) Compile: a static pass over the module tree. No model runs.
    compiled = team.compile()
    print("Compiled workflow:")
    print(repr(compiled))

    # 2) Inspect the static resource manifest.
    manifest = compiled.manifest
    print("\nReachable provider models:", manifest.provider_models())
    print("Agents:")
    for agent in manifest.agents:
        print(
            f"  - {agent.path}: model={agent.provider.model} memory={agent.has_memory}"
        )
    if manifest.dynamic_nodes:
        print("Dynamic nodes (runtime-decided):")
        for node in manifest.dynamic_nodes:
            print(f"  - {node.path} [{node.kind}]: {node.reason}")

    # 3) Pre-flight validation — offline, before any run.
    problems = compiled.validate()
    print("\nvalidate() problems:", problems or "none — ready to run")

    # 4) Deterministic resource lifecycle. Bound memory stores (none here) are
    #    acquired on enter and released on exit.
    with team.compile() as live:
        print(f"\nInside lifecycle: {len(live.manifest.agents)} agents ready.")
    print("Resources released on exit.")


if __name__ == "__main__":
    main()
