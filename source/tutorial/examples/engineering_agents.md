# Engineering Agents

Directory: `example/engineering_agents/`.

Engineering Agents decomposes an engineering task into layered workflows: the lead plans, the architect decomposes the design, backend and frontend roles implement separate parts, and QA reviews risks at the end. Each role is represented by an `AgentParam`, and ordinary Python `Workflow` composition defines the hierarchy.

## What it covers
| Topic | Result |
| --- | --- |
| nested workflow | A parent workflow calls a child workflow, which can call smaller workflows. |
| direct registration | Directly assigned `AgentParam` instances are registered by the current workflow. |
| ordinary attributes | Child workflows are stored as ordinary attributes and called in `forward(...)`. |
| session pipeline | All roles keep appending context along the same session. |
| session-level parallel | Subtasks without upstream/downstream dependencies can fork from the same session and run in parallel. |
| engineering decomposition | A complex engineering task is split into lead, architect, backend, frontend, and QA roles. |

## Directory structure
| File | Responsibility |
| --- | --- |
| `agents.py` | Defines system prompts for the lead engineer, architect, backend, frontend, and QA roles. |
| `workflows.py` | Defines `BackendPairWorkflow`, `FeatureSquadWorkflow`, `QualityAssuranceWorkflow`, and `EngineeringProjectWorkflow`. |
| `main.py` | CLI entry point that reads LLM configuration, constructs the user session, binds the local backend, and runs the workflow. |

## Workflow hierarchy
| Level | Class | Execution |
| --- | --- | --- |
| L1 | `EngineeringProjectWorkflow` | lead plan -> feature squad -> QA. |
| L2 | `FeatureSquadWorkflow` | architect -> backend pair -> frontend. |
| L3 | `BackendPairWorkflow` | backend auth -> backend data. |
| QA | `QualityAssuranceWorkflow` | Produces a test plan and risk review from the full session. |

This nested workflow uses three rules: `AgentParam` instances attached directly to the current workflow are registered; child workflows are stored as ordinary Python attributes; execution order is written explicitly in `forward(...)`.

## Session-level parallelism
Engineering Agents can also express parallel development with session branches. The current `BackendPairWorkflow` runs the auth backend and data backend sequentially. If both subtasks already have enough context from the architect stage, they can fork from the same session and run in parallel:

```python
from concurrent.futures import ThreadPoolExecutor


auth_input = session.fork()
data_input = session.fork()

with ThreadPoolExecutor(max_workers=2) as pool:
    auth_future = pool.submit(
        run_session_loop,
        auth_input,
        self.backend_auth.agent_session,
        agent_provider=self.backend_auth.provider,
        tools=None,
    )
    data_future = pool.submit(
        run_session_loop,
        data_input,
        self.backend_data.agent_session,
        agent_provider=self.backend_data.provider,
        tools=None,
    )
    auth_session = auth_future.result()
    data_session = data_future.result()
```

This pattern does not automatically merge the two branches into one transcript. The workflow must explicitly define the next input, such as extracting summaries from both branches and passing them to the frontend or QA agent. OpenRath records fork and loop lineage and keeps each branch's sandbox handle independent for the session lifecycle.

One minimal aggregation approach is to combine the final output from both branches into a new user session:

```python
from rath.session import ChunkKind, Session


def last_assistant_text(s: Session) -> str:
    for row in reversed(s.chunk_table.rows):
        if row.kind == ChunkKind.ASSISTANT and row.payload.get("content"):
            return str(row.payload["content"])
    return ""


frontend_input = Session.from_user_message(
    "Implement the frontend using both backend branches.\n\n"
    f"Auth backend:\n{last_assistant_text(auth_session)}\n\n"
    f"Data backend:\n{last_assistant_text(data_session)}"
).to("local")
```

If both branches write files, reset the workspace after the fork so the auth and data branches do not write into the same directory:

```python
auth_input = session.fork().to("local", spec=".workspace/auth-backend")
data_input = session.fork().to("local", spec=".workspace/data-backend")
```

## BackendPairWorkflow
The core structure comes from `example/engineering_agents/workflows.py`:

```python
class BackendPairWorkflow(Workflow):
    def __init__(self, prov: Provider) -> None:
        super().__init__()
        self.backend_auth = AgentParam(
            Session.from_agent_prompt(BACKEND_AUTH_SYSTEM),
            prov,
        )
        self.backend_data = AgentParam(
            Session.from_agent_prompt(BACKEND_DATA_SYSTEM),
            prov,
        )

    def forward(self, session: Session) -> Session:
        s = run_session_loop(
            session,
            self.backend_auth.agent_session,
            agent_provider=self.backend_auth.provider,
            tools=None,
        )
        return run_session_loop(
            s,
            self.backend_data.agent_session,
            agent_provider=self.backend_data.provider,
            tools=None,
        )
```

Key points:

| Line | Explanation |
| --- | --- |
| `self.backend_auth = AgentParam(...)` | The auth backend role is registered with the current workflow. |
| `self.backend_data = AgentParam(...)` | The data backend role is also registered. |
| `s = run_session_loop(...)` | The auth output session enters the data stage. |
| `tools=None` | The roles can still use built-in tools; no custom tools are added. |

## Outer composition
The outer workflow composes child workflows:

```python
class EngineeringProjectWorkflow(Workflow):
    def __init__(self, model: str) -> None:
        super().__init__()
        prov = Provider(model=model)
        self.lead = AgentParam(Session.from_agent_prompt(LEAD_ENGINEER_SYSTEM), prov)
        self._squad = FeatureSquadWorkflow(prov)
        self._qa = QualityAssuranceWorkflow(prov)

    def forward(self, session: Session) -> Session:
        s = run_session_loop(
            session,
            self.lead.agent_session,
            agent_provider=self.lead.provider,
            tools=None,
        )
        s = self._squad.forward(s)
        return self._qa.forward(s)
```

Key points:

| Line | Explanation |
| --- | --- |
| `self.lead = AgentParam(...)` | The lead is a direct agent on the current workflow. |
| `self._squad = FeatureSquadWorkflow(prov)` | The child workflow is stored as an ordinary attribute. |
| `self._qa = QualityAssuranceWorkflow(prov)` | The QA child workflow is also stored as an ordinary attribute. |
| `self._squad.forward(s)` | The parent workflow explicitly calls the child workflow. |
| `return self._qa.forward(s)` | The QA stage receives the full session. |

## Run
Run from the repository root:

```bash
python example/engineering_agents/main.py \
  --goal "Full-stack todo app with auth, DB, React frontend." \
  --workdir .workspace/engineering-agents
```

This example requires a real OpenAI-compatible LLM configuration. The script reads the default model configuration; if it is missing, it falls back to the default model name in the script.

## Successful output
The script prints the final `Session(...)`. On success, assistant rows grow in this order: lead, architect, backend auth, backend data, frontend, QA:

```text
Session(
  chunks=[
    [0] user: 'Full-stack todo app with auth...'
    [1] assistant: text='Lead plan...'
    [2] assistant: text='Architecture...'
    [3] assistant: text='Backend auth...'
    [4] assistant: text='Backend data...'
    [5] assistant: text='Frontend plan...'
    [6] assistant: text='QA review...'
  ]
)
```

If the model calls file-writing tools, implementation or review files appear under `.workspace/engineering-agents`. The example QA prompt asks for `ENGINEERING_REVIEW.md`, but actual file creation depends on whether the model calls tools.

## What to inspect
| Location | What to check |
| --- | --- |
| stdout | Lead, architect, backend, frontend, and QA append to the same session in order. |
| workflow repr | Directly registered `AgentParam` instances appear in `named_agents()` and `repr(workflow)`. |
| workspace | The QA prompt asks for `ENGINEERING_REVIEW.md`. |
| chunk table | Shows the order of assistant messages from each role. |

## Troubleshooting
| Symptom | Check |
| --- | --- |
| LLM request fails | Check the model gateway configuration. |
| Workspace has no output files | Check whether the model actually called file-writing tools. |
| Child workflow does not appear in repr | The current base class only registers directly attached `AgentParam` instances. |
| Output is repetitive | Check the role boundaries in each system prompt. |

## Exercises
1. Add a security reviewer to `FeatureSquadWorkflow`.
2. Move the QA stage to run before `Compressor`, then compress before producing the report.
3. Print the session row count after each stage and observe how context grows.
