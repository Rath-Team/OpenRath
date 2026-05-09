# OpenRath documentation

OpenRath is an open-source Python framework for **dynamic multi-agent workflows**
with a deliberately **torch-inspired API surface**: composable modules
(`Workflow`), attachable configuration (`Agent`), a tape-like conversation state
(`Session`), structured tool calls (`FlowToolCall`) dispatched through sandbox
**backends**, and an OpenAI-compatible **LLM** client path.

Features described in this documentation are classified by release status:

**Stable (API-stable):** Symbols and behaviors we intend to keep compatible across
minor releases, subject to normal semver caveats for `0.y.z`. Breaking changes,
when unavoidable, should be called out in release notes ahead of time.

**Experimental (API-unstable):** Areas under active iteration—layout of optional
extras, edge cases around remote sandboxes, or hooks that may gain parameters as
the runtime hardens. Expect APIs and performance characteristics to evolve.

## Install OpenRath

* [Installation](install.md) — supported Python versions, `pip` / `uv`, and optional extras.

## User Guide

* [User Guide](user_guide/index.md)
  * [Design overview](user_guide/concepts.md)
  * [OpenRath main components](user_guide/main_components.md)
  * [Sessions and chunks](user_guide/session.md)
  * [Workflow and Agent](user_guide/workflow_agent.md)
  * [Tools and ToolTable](user_guide/tools.md)
  * [Backends and sandboxes](user_guide/backends.md)
  * [LLM client and settings](user_guide/llm.md)

## Reference API

* [Python API overview](reference/index.md)

## Developer Notes

* [Notes](notes/index.md)

## Examples

* [Examples index](examples/index.md)

## Community

* [Community](community/index.md)

## Indices and tables

* {ref}`genindex`
* {ref}`modindex`

```{toctree}
:maxdepth: 3
:caption: Site navigation
:hidden:

install
user_guide/index
reference/index
examples/index
notes/index
community/index
```
