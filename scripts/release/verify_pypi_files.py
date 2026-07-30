"""Verify that existing PyPI files are identical to local release artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.error
import urllib.request
from pathlib import Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def local_distributions(packages_dir: Path, *, version: str) -> dict[str, str]:
    """Return the exact wheel and sdist hashes expected for one version."""
    sdist = packages_dir / f"openrath-{version}.tar.gz"
    wheels = sorted(packages_dir.glob(f"openrath-{version}-*.whl"))
    if not sdist.is_file() or len(wheels) != 1:
        raise ValueError("expected exactly one OpenRath wheel and one sdist")
    paths = [sdist, wheels[0]]
    return {path.name: _sha256(path) for path in paths}


def verify_remote_files(
    local: dict[str, str],
    payload: dict[str, object] | None,
    *,
    version: str,
    require_complete: bool,
) -> bool:
    """Reject conflicting files and return whether PyPI is complete."""
    if payload is None:
        if require_complete:
            raise ValueError(f"OpenRath {version} is not visible on PyPI")
        return False

    info = payload.get("info")
    if not isinstance(info, dict) or info.get("version") != version:
        raise ValueError("PyPI response version does not match the release")
    urls = payload.get("urls")
    if not isinstance(urls, list) or not urls:
        raise ValueError("PyPI response contains no distribution files")

    remote: dict[str, str] = {}
    for item in urls:
        if not isinstance(item, dict):
            raise ValueError("PyPI distribution entry must be an object")
        filename = item.get("filename")
        digests = item.get("digests")
        sha256 = digests.get("sha256") if isinstance(digests, dict) else None
        if not isinstance(filename, str) or not isinstance(sha256, str):
            raise ValueError("PyPI distribution entry is missing its SHA-256")
        remote[filename] = sha256

    unexpected = sorted(set(remote) - set(local))
    if unexpected:
        raise ValueError("PyPI contains unexpected files: " + ", ".join(unexpected))
    conflicts = sorted(
        filename for filename, digest in remote.items() if local.get(filename) != digest
    )
    if conflicts:
        raise ValueError("PyPI file hash mismatch: " + ", ".join(conflicts))

    missing = sorted(set(local) - set(remote))
    if require_complete and missing:
        raise ValueError("PyPI is missing release files: " + ", ".join(missing))
    return not missing


def _pypi_payload(*, version: str) -> dict[str, object] | None:
    url = f"https://pypi.org/pypi/openrath/{version}/json"
    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packages-dir", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--require-complete", action="store_true")
    parser.add_argument("--attempts", type=int, default=1)
    parser.add_argument("--delay-seconds", type=float, default=5)
    args = parser.parse_args()
    if args.attempts < 1:
        raise SystemExit("--attempts must be positive")

    local = local_distributions(args.packages_dir, version=args.version)
    last_error: ValueError | None = None
    for attempt in range(1, args.attempts + 1):
        try:
            complete = verify_remote_files(
                local,
                _pypi_payload(version=args.version),
                version=args.version,
                require_complete=args.require_complete,
            )
        except ValueError as error:
            last_error = error
            if attempt == args.attempts:
                raise SystemExit(str(error)) from error
        else:
            state = "complete and identical" if complete else "absent or partial"
            print(f"PyPI OpenRath {args.version}: {state}")
            return
        time.sleep(args.delay_seconds)
    raise SystemExit(str(last_error))
