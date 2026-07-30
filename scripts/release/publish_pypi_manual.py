"""Publish the verified OpenRath GA bundle with an interactive PyPI token."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

CONFIRMATION = "publish openrath 2.0.0 to pypi"
TWINE_VERSION = "6.2.0"


def _run(*arguments: str, env: dict[str, str] | None = None) -> None:
    subprocess.run(arguments, check=True, env=env)


def twine_environment(source: dict[str, str]) -> dict[str, str]:
    """Return an environment that cannot reuse stored Twine credentials."""
    clean = dict(source)
    for name in (
        "TWINE_PASSWORD",
        "TWINE_USERNAME",
        "TWINE_REPOSITORY",
        "TWINE_REPOSITORY_URL",
    ):
        clean.pop(name, None)
    clean["PYTHON_KEYRING_BACKEND"] = "keyring.backends.null.Keyring"
    return clean


def twine_upload_command(distributions: list[str]) -> list[str]:
    """Build the interactive upload command without embedding a token."""
    return [
        "uvx",
        "--from",
        f"twine=={TWINE_VERSION}",
        "twine",
        "upload",
        "--repository-url",
        "https://upload.pypi.org/legacy/",
        "--username",
        "__token__",
        "--skip-existing",
        *distributions,
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-dir", type=Path, required=True)
    args = parser.parse_args()

    bundle = args.bundle_dir.resolve()
    repository_root = Path(__file__).resolve().parents[2]
    manifest = bundle / "release/evidence/2.0.0/manifest.json"
    packages_dir = bundle / "dist"
    wheel = next(packages_dir.glob("openrath-2.0.0-*.whl"), None)
    sdist = packages_dir / "openrath-2.0.0.tar.gz"
    if wheel is None or not sdist.is_file() or not manifest.is_file():
        raise SystemExit("bundle must contain the 2.0.0 wheel, sdist, and manifest")

    _run(
        sys.executable,
        str(repository_root / "scripts/release/verify_evidence.py"),
        str(manifest),
        "--artifact-root",
        str(bundle),
    )
    _run(
        sys.executable,
        str(repository_root / "scripts/release/verify_pypi_files.py"),
        "--packages-dir",
        str(packages_dir),
        "--version",
        "2.0.0",
    )
    distributions = [str(sdist), str(wheel)]
    _run(
        "uvx",
        "--from",
        f"twine=={TWINE_VERSION}",
        "twine",
        "check",
        *distributions,
    )

    print("The token will be requested by Twine and will not be stored by this script.")
    if input(f'Type "{CONFIRMATION}" to continue: ') != CONFIRMATION:
        raise SystemExit("publication cancelled")

    _run(*twine_upload_command(distributions), env=twine_environment(os.environ))
    _run(
        sys.executable,
        str(repository_root / "scripts/release/verify_pypi_files.py"),
        "--packages-dir",
        str(packages_dir),
        "--version",
        "2.0.0",
        "--require-complete",
        "--attempts",
        "12",
        "--delay-seconds",
        "10",
    )


if __name__ == "__main__":
    main()
