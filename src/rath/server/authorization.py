"""Fail-closed action authorization for the Agent Server."""

from __future__ import annotations

from rath.security import SecurityContext

__all__ = ["allows", "project_allows"]


def allows(context: SecurityContext, action: str) -> bool:
    """Return whether an explicit grant permits an action.

    Grants support an exact action, a namespace wildcard such as ``run.*``,
    or the explicit administrative ``*`` grant.
    """

    if "*" in context.grants or action in context.grants:
        return True
    namespace, _, _ = action.partition(".")
    return f"{namespace}.*" in context.grants


def project_allows(
    context: SecurityContext,
    resource_project_id: object | None,
) -> bool:
    """Enforce project isolation when either side declares project scope."""

    if resource_project_id is None:
        return True
    return (
        context.project_id is not None
        and str(resource_project_id) == context.project_id
    )
