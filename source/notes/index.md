# Notes

Developer-facing notes follow the spirit of [PyTorch Notes](https://docs.pytorch.org/docs/stable/notes.html):
focused articles on semantics, migration, and sharp edges.

## Current topics

* **Registry defaults** — `rath.backend.set_default` mirrors `torch.set_default_device` ergonomics; always confirm availability with `is_available()` before assuming OpenSandbox is importable.
* **Tool loop budgets** — `max_tool_rounds` prevents infinite tool chatter; tune per workflow risk profile.
* **Session lineage** — Opt-in graph stamping adds bookkeeping overhead; enable only when provenance queries justify it.
* **Blocking loop** — `run_session_loop` is synchronous; async stacks should wrap executor calls explicitly until native async clients ship.

For narrative context see the User Guide:

* [Sessions](../user_guide/session)
* [Tools](../user_guide/tools)
* [Backends](../user_guide/backends)
