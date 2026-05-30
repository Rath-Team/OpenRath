"""``EmptyWorkflow``: no-op :class:`~rath.flow.workflow.Workflow` (identity forward)."""

from __future__ import annotations

from rath.flow.workflow import Workflow
from rath.session.session import Session


class EmptyWorkflow(Workflow):
    """No-op workflow: ``forward`` returns the input session unchanged.

    Returned by :class:`~rath.flow.selector.Selector` when no candidate fits / the
    session is complete, so callers can dispatch unconditionally and detect completion
    via ``isinstance(result, EmptyWorkflow)``.
    """

    def forward(self, session: Session) -> Session:
        return session


__all__ = ["EmptyWorkflow"]
