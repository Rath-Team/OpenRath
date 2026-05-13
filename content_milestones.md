# OpenRath Documentation Milestones

This file tracks documentation work after the 1.0 release. The main published
site is English-first and lives under `docs/source`.

## Milestone Overview

| ID | Name | Goal | Status |
| --- | --- | --- | --- |
| M1 | Session depth | Explain `Session` as the core runtime carrier and make the session basics tutorial guided. | Done |
| M2 | Tool and sandbox depth | Explain `FlowToolCall`, backend payloads, tool results, local backend, and OpenSandbox lifecycle. | Done |
| M3 | Workflow and multi-agent depth | Explain `Workflow`, `AgentParam`, and the progression from one agent to multi-agent workflows. | Done |
| M4 | Guided tutorials | Give tutorials learning goals, key-line explanations, expected observations, failure checks, and exercises. | Done |
| M5 | End-to-end verification | Verify OpenAI-compatible LLM config, local backend, OpenSandbox, and multi-agent examples. | Done |
| M6 | Release audit | Check search, navigation, links, API reference, example commands, secret handling, and OpenSandbox setup. | Done |
| M7 | English site baseline | Keep `docs/source` as the primary English Sphinx site and remove stale Chinese-site maintenance assumptions. | In progress |

## Page Standards

Each core concept page should answer:

| Question | Standard |
| --- | --- |
| What problem does this component solve? | Start with a short intuition, not only an API list. |
| Why is OpenRath organized this way? | Connect design motivation to source behavior. |
| When does a user touch it directly? | Give common development scenarios and decision points. |
| How do key APIs change runtime state? | Explain inputs, outputs, state transitions, and side effects. |
| What boundaries are easy to misunderstand? | Document errors, lifecycle rules, defaults, and checks. |

Each tutorial should include:

| Section | Purpose |
| --- | --- |
| Learning goal | State what the reader should understand afterward. |
| Code steps | Introduce one concept at a time. |
| Key-line explanation | Explain why specific lines matter. |
| Observation point | Tell the reader what they should see. |
| Failure check and exercise | Help readers move from copying to modifying. |
