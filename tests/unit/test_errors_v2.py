from __future__ import annotations

from rath.errors import ErrorCode, RathError


def test_rath_error_has_stable_machine_contract() -> None:
    error = RathError(
        ErrorCode.INVALID_ARGUMENT,
        "invalid input",
        retryable=False,
        details={"field": "name"},
    )

    assert error.to_dict() == {
        "code": "request.invalid_argument",
        "message": "invalid input",
        "retryable": False,
        "details": {"field": "name"},
    }


def test_error_details_are_immutable_copies() -> None:
    details = {"nested": {"value": 1}}
    error = RathError(ErrorCode.INTERNAL, "internal", details=details)
    details["nested"]["value"] = 2

    assert error.details["nested"]["value"] == 1  # type: ignore[index]
