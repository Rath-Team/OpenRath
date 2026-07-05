"""P2.4 — the registry emits a stable, sorted env reference (markdown)."""

from __future__ import annotations

from rath.config.env import env_reference_markdown, env_reference_rows


def test_markdown_has_header_and_all_rows() -> None:
    md = env_reference_markdown()
    # Header row + separator + one line per declared var.
    lines = [ln for ln in md.splitlines() if ln.strip()]
    assert lines[0].startswith("| Name | Kind | Consumers | Default |")
    assert set(lines[1].replace(" ", "")) <= {"|", "-"}
    body = lines[2:]
    assert len(body) == len(env_reference_rows())
    # Sorted by name and includes a known var.
    assert "OPENAI_API_KEY" in md
    names_in_order = [ln.split("|")[1].strip().strip("`") for ln in body]
    assert names_in_order == sorted(names_in_order)


def test_secret_defaults_never_leak_a_value() -> None:
    # Secrets have no default, so the Default column is blank for them.
    md = env_reference_markdown()
    for line in md.splitlines():
        if "OPENAI_API_KEY" in line and line.startswith("|"):
            cols = [c.strip() for c in line.strip("|").split("|")]
            assert cols[-1] == ""  # no default value printed for a secret
