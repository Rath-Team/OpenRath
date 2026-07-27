from __future__ import annotations

import json
from uuid import uuid4

from rath.definition import EffectClass, WorkflowCompiler, step
from rath.flow import AgentParam, Workflow
from rath.llm import Provider
from rath.session import Session


class _WithSecretProvider(Workflow):
    def __init__(self) -> None:
        super().__init__()
        self.agent = AgentParam(
            Session.from_agent_prompt("system"),
            Provider(model="model", api_key="must-not-leak"),
        )

    @step(entry=True, effects=EffectClass.READ_ONLY)
    def execute(self, state, context):  # type: ignore[no-untyped-def]
        return state

    def forward(self, session: Session) -> Session:
        return session


def test_canonical_plan_never_serializes_provider_secret_values() -> None:
    plan = WorkflowCompiler().compile(_WithSecretProvider(), revision_id=uuid4())
    encoded = plan.canonical_json()

    assert "must-not-leak" not in encoded
    payload = json.loads(encoded)
    assert payload["resources"]["providers"][0]["model"] == "model"
    assert "api_key" not in payload["resources"]["providers"][0]


def test_existing_compiled_workflow_exposes_v2_execution_plan() -> None:
    workflow = _WithSecretProvider()
    compiled = workflow.compile()

    assert compiled.execution_plan.definition_hash
    assert compiled.execution_plan.durable is True

