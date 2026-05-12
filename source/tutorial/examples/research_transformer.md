# Research Transformer

Directory on `main`: [`example/research_transformer/`](https://github.com/Rath-Team/OpenRath/tree/main/example/research_transformer).

Research Transformer is a multi-stage academic writing pipeline. It uses a
Transformer metaphor, but the implementation is ordinary OpenRath workflow code:
the input `Session` flows through branch workflows, compression points, and an
output head.

This page documents the example currently on `origin/main`. If you are previewing
the `docs` branch before it is rebased or merged with `main`, use the GitHub link
above for the runnable source.

The point of the example is not the metaphor itself. It is a compact way to show
how OpenRath can keep a complex agent workflow readable: each station is explicit,
the state carrier is still a `Session`, and the orchestration remains normal
Python code.

```{figure} ../../_static/research-transformer-overview.png
:alt: Research Transformer architecture
:class: or-research-transformer-figure

Research Transformer maps a research-writing workflow onto a transformer-like
stack: one branch works from the research question and advisor feedback, another
branch works from thesis context and deadline pressure, and the output head
polishes the final report.
```

## What it covers

| Topic | Result |
| --- | --- |
| nested workflows | The full pipeline is composed from literature, reproduction, and output-head workflows. |
| per-role providers | Each station can use its own `Provider` from environment variables. |
| repeated layers | `--layers` repeats the branch blocks to deepen the pipeline. |
| session compression | `run_session_compress` runs between major stages unless disabled. |
| optional tool | The verifier can receive a `background_image` `FlowToolCall`. |
| observability | `--print-chunks` prints one line for each appended chunk. |

For readers evaluating OpenRath, this example is useful because it combines the
core abstractions in one place without requiring a custom scheduler. `Workflow`
defines the shape, `AgentParam` defines the stations, `Provider` controls the
model used by each station, and `Session` carries the evolving research state.

## Pipeline shape

The example starts from one user session containing a research question and
advisor constraints. The reproduction branch appends a thesis excerpt and a
deadline note before its own agent loop.

| Stage | Agent roles | Session behavior |
| --- | --- | --- |
| literature branch | packager, literature, rewrite | Packages the task, then runs `literature -> rewrite` for each layer. |
| compression | compressor | Summarizes the accumulated session before the next branch. |
| reproduction branch | QA, verifier | Adds thesis context, then runs `QA -> verifier` for each layer. |
| compression | compressor | Compacts the second branch output. |
| output head | jargon, de-AI | Tightens academic register and polishes the final prose. |

The full workflow class is `ResearchTransformerWorkflow`. Its `forward(...)`
method is intentionally linear:

```python
s = self._literature.forward(session)
if self._enable_compress:
    s = self._compressor.forward(s)
s = self._repro.forward(s)
if self._enable_compress:
    s = self._compressor.forward(s)
return self._head.forward(s)
```

The branch workflows are still normal `Workflow` subclasses. Each station is an
`AgentParam`, and each station calls `run_session_loop(...)` with its own
provider.

The important design choice is that branches and compression points are visible
in user code. OpenRath does not hide the orchestration behind a graph DSL; the
workflow remains inspectable and easy to modify.

## Environment

The CLI reads OpenAI-compatible credentials from either shared OpenRath variables
or Research Transformer-specific variables.

| Variable | Required | Purpose |
| --- | --- | --- |
| `OPENAI_API_KEY` or `RESEARCH_TRANSFORMER_API_KEY` | Yes | API key for all stations unless you split keys later. |
| `OPENAI_BASE_URL` or `RESEARCH_TRANSFORMER_BASE_URL` | No | Custom OpenAI-compatible gateway. |
| `OPENAI_DEFAULT_MODEL` | No | Fallback model when a station-specific model is unset. |
| `RESEARCH_TRANSFORMER_MODEL_*` | No | Per-station model override. |
| `ZHIPU_API_KEY` | No | Enables the optional `background_image` tool. |

Per-station model variables:

| Variable | Station |
| --- | --- |
| `RESEARCH_TRANSFORMER_MODEL_PACKAGER` | Literature branch packaging. |
| `RESEARCH_TRANSFORMER_MODEL_LITERATURE` | Literature synthesis turns. |
| `RESEARCH_TRANSFORMER_MODEL_REWRITE` | Rewrite and refinement turns. |
| `RESEARCH_TRANSFORMER_MODEL_QA` | Thesis reproduction Q&A. |
| `RESEARCH_TRANSFORMER_MODEL_VERIFIER` | Verification, optionally with image tools. |
| `RESEARCH_TRANSFORMER_MODEL_JARGON` | Academic register pass. |
| `RESEARCH_TRANSFORMER_MODEL_DEAI` | Style polish pass. |
| `RESEARCH_TRANSFORMER_MODEL_COMPRESSOR` | Compression between major stages. |

## How to run

Run from the repository `example/` directory so sibling imports resolve:

```bash
cd example

uv run python research_transformer/main.py \
  --research-question "How should we frame the system contribution?" \
  --supervisor-notes "Prefer precise claims and avoid broad positioning." \
  --thesis-path ./path/to/thesis_excerpt.txt
```

Useful flags:

| Flag | Meaning |
| --- | --- |
| `--workdir` | Sandbox workspace, defaulting to `research_transformer/.workspace/`. |
| `--layers` / `--iterations` | Number of repetitions per branch. |
| `--ddl-note` | Deadline or pressure context for the reproduction branch. |
| `--skip-images` | Do not register the optional `background_image` tool. |
| `--no-compress` | Disable compression between major stages. |
| `--print-chunks` | Print concise chunk append events. |

## Optional background image tool

`tools.py` defines `BackgroundImageTool`, a `FlowToolCall` named
`background_image`. It is optional and can be skipped with `--skip-images`.

The tool is passed only to the verifier station. That keeps the model-visible
tool surface narrow: most stations only receive the built-in OpenRath tools,
while the verifier can request a research-style background image when useful.

## Source map

| File | Responsibility |
| --- | --- |
| `README.md` | Usage notes, environment table, and CLI examples. |
| `main.py` | Argument parsing, session creation, local workspace binding, workflow execution. |
| `workflow.py` | Literature branch, reproduction branch, output head, compression points. |
| `providers.py` | Builds `ResearchTransformerProviders` from environment variables. |
| `prompts.py` | System prompts for every station. |
| `tools.py` | Optional `background_image` tool. |

## Expected success output

The CLI currently returns a final `Session`. With `--print-chunks`, stdout shows
one concise line per appended chunk, including loop, compression, and branch
preamble rows. The final content should reflect:

1. the original research question;
2. supervisor constraints;
3. thesis excerpt constraints from the reproduction branch;
4. compressed context between branch stages;
5. the final academic-register and style-polish passes.

If `--no-compress` is enabled, the same pipeline runs without the two compression
passes, but context can grow quickly for larger `--layers` values.
