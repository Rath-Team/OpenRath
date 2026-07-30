from __future__ import annotations

from uuid import uuid4

from rath.definition import EffectClass, WorkflowCompiler, step
from rath.flow import Workflow
from rath.session import Session


def test_handler_implementation_change_changes_definition_identity() -> None:
    class _ImplementationIdentity(Workflow):
        @step(entry=True, effects=EffectClass.READ_ONLY)
        def execute(self, state, context):  # type: ignore[no-untyped-def]
            return {"value": 1}

        def forward(self, session: Session) -> Session:
            return session

    revision_id = uuid4()
    compiler = WorkflowCompiler()
    first = compiler.compile(_ImplementationIdentity(), revision_id=revision_id)

    def replacement(self, state, context):  # type: ignore[no-untyped-def]
        return {"value": 999}

    replacement.__name__ = "execute"
    setattr(
        _ImplementationIdentity,
        "execute",
        step(entry=True, effects=EffectClass.READ_ONLY)(replacement),
    )
    second = compiler.compile(
        _ImplementationIdentity(),
        revision_id=revision_id,
    )

    assert first.definition_hash != second.definition_hash
    assert first.id != second.id
