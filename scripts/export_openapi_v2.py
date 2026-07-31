"""Export the deterministic v2 Agent Server OpenAPI contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from rath.server.app import _openapi_document


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("deploy/docs/openapi-v2.json"),
    )
    parser.add_argument("--version", default="2.0.0")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            _openapi_document(args.version, store_enabled=True),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
