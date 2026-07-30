from __future__ import annotations

from scripts.release.publish_pypi_manual import (
    twine_environment,
    twine_upload_command,
)


def test_manual_upload_command_prompts_without_exposing_a_token() -> None:
    command = twine_upload_command(["openrath.whl", "openrath.tar.gz"])

    assert command[:4] == ["uvx", "--from", "twine==6.2.0", "twine"]
    assert "__token__" in command
    assert "--password" not in command
    assert "--skip-existing" in command
    assert not any(value.startswith("pypi-") for value in command)


def test_manual_upload_environment_removes_credential_overrides() -> None:
    environment = twine_environment(
        {
            "PATH": "kept",
            "TWINE_PASSWORD": "secret",
            "TWINE_USERNAME": "wrong",
            "TWINE_REPOSITORY": "wrong",
            "TWINE_REPOSITORY_URL": "wrong",
        }
    )

    assert environment["PATH"] == "kept"
    assert environment["PYTHON_KEYRING_BACKEND"] == "keyring.backends.null.Keyring"
    assert not any(name.startswith("TWINE_") for name in environment)
