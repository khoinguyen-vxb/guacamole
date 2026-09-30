Graph based Unified Agentic Coordination Architecture for Multidisciplinary Optimization and Lifecycle Engineering (guacemole)

## Local runtime

Guacamole exposes supplied Python tools, coordinates a Chief Engineer and dynamic
workers, and keeps their context, messages, decisions, artifacts, and review history
in a local SQLite workspace. There is no platform frontend or HTTP service.

```bash
uv sync
```

Tool input/output annotations generate strict runtime validation and MCP schemas.
New tools do not require a solver adapter, agent role, or skill file in Guacamole.

## Loading custom tools

Put your typed functions in a module beside your script, or import them from an
installed package. For example, create `engineering_tools.py`:

```python
from typing import Annotated
from pydantic import Field

type Positive = Annotated[float, Field(gt=0, allow_inf_nan=False)]

def temperature_rise(power_w: Positive, resistance_k_w: Positive) -> float:
    """Steady temperature rise in kelvin for a lumped thermal resistance."""
    return power_w * resistance_k_w
```

Then import and register the functions you want to expose:

```python
import asyncio
from pathlib import Path
from guacamole import Project, ToolRegistry
from engineering_tools import temperature_rise

async def main() -> None:
    tools = ToolRegistry()
    tool = tools.register(temperature_rise, version="1", retry_safe=True)
    with Project(
        Path(".guacamole/example"), sandbox=Path("results/example"), tools=tools
    ) as project:
        job = project.submit(tool, {"power_w": 20.0, "resistance_k_w": 0.5})
        print(await job.collect())
        print(project.trace(job.id))

asyncio.run(main())
```

In this example, `temperature_rise` declares positive, finite inputs in watts and
kelvins per watt and returns a temperature rise in kelvin. Its docstring becomes
the tool description. Supplying `"20"` instead of a number, a negative resistance,
or an unknown argument fails validation before execution. The same registry can
be passed to an autonomous Project configured with a reasoning provider.

Use fully annotated functions, bound methods, dataclasses, or Pydantic models.
Declare physical bounds, units, frames, and shapes in provider-owned models and
validators. Missing annotations, `Any`/opaque objects, undeclared input fields,
coercible strings, nonfinite values, and invalid outputs are rejected. A successful
tool execution does not imply convergence or physical acceptance.

Tools write native files under `project.sandbox` and return
`ProducedFile.from_path(path)`. The executor snapshots the bytes before success.
Explicit acceptance tools return `VerificationResult`. Publishing evidence checks
that the verification actually used the claimed artifact revision. Native solver
objects remain inside the provider. Keep credentials in provider configuration or
environment variables rather than tool arguments, documents, or model context.

## Agent sandbox

Choose the directory for CAD, software, PCB files, and other deliverables when
creating the project:

```python
with Project(
    Path(".guacamole/rocket"),  # SQLite history and runtime lock
    sandbox=Path("results/rocket"),  # Shared Chief/worker output directory
    tools=tools,
) as project:
    destination = project.output_path(Path("software/controller.py"))
    # A registered tool can write here and return ProducedFile.from_path(destination).
```

The sandbox is created automatically and its absolute path is included in every
agent's context as `state.sandbox`. Tools can use `project.sandbox` or
`project.output_path(relative_path)`; the latter rejects paths and symlinks escaping
the sandbox. Tools create their own subdirectories and return each generated file
as a `ProducedFile`. Artifact snapshots live in `sandbox/artifacts/`, and PDR/CDR
packages in `sandbox/reviews/`. `FileRecord.path` is relative to the sandbox.
Original input documents may live outside it and are copied into artifact storage.

The path is saved with the project and reused when reopening it, including
read-only inspection. On first initialization, omitting `sandbox` uses the workspace
directory. An existing project's sandbox cannot be changed through this argument;
repointing it would detach stored file references. Relative paths are resolved
against the process's current directory. Tool working directories are unchanged.

This boundary validates output paths; registered Python tools and their subprocesses
retain their operating-system permissions. Providers manage any process isolation.

## Autonomous projects

Configure a reasoning provider. `guacamole.providers.codex.CodexReasoning` launches
an ephemeral local `codex exec -m gpt-6-astra` process for each turn using your
existing ChatGPT login (`codex login`). It requires no API key; model inference
is hosted and uses your Codex account limits. It runs in a temporary read-only
working directory, skips user configuration, and disables shell, apps, plugins,
web search, and delegation by default so Guacamole executes the returned typed
actions. Pass `CodexReasoning(web_search=True)` to enable built-in live web
research; the Electronic Hopper launcher enables it for component sourcing.
Timeouts and cancellation stop the child process group.

Codex input budgeting uses a conservative UTF-8 byte upper bound, recorded as
`token_count_method="utf8_upper_bound"`; it makes no API token-count calls.
This may defer more optional source material than an exact tokenizer.
`reserved_output_tokens` reserves context headroom; the CLI controls generation
limits and its own prompt overhead. See [Codex non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode).

The separate `guacamole.providers.astra.AstraReasoning` adapter uses
`gpt-6-astra` through the OpenAI Responses API. It reads `OPENAI_API_KEY` at call
time; it does not reuse Codex CLI login credentials. Token counting uses the
[official input-token endpoint](https://developers.openai.com/api/docs/guides/token-counting)
for the exact saved prompt, including tool/action schemas and context. The model's
documented capacity is checked separately from each agent's configured budget.

The Chief makes engineering selections through a typed `decide` action containing
the alternatives and the selected candidate ID. Its rationale explains the choice.
The runtime validates constraints, task/tool grants, requirement coverage, and input
revisions before recording the decision. Invalid selections and stale evidence
block dependent work. Decision records retain the author, rationale/context links,
and resolved input snapshots. Host scripts can use
`await project.decisions.choose(request, selected="candidate-id", explanation="...")`.

Register source readers with `requires_plan=False` to allow agent inspection before
the initial work plan. Tool grants and input revision checks still apply. Kookaburra
does this for `list_files`, `read_text`, and `read_document`; file-writing and
execution tools retain the default requirement for a validated plan.

```python
from pathlib import Path

from guacamole import ContextSpec, Project, ProjectRequest
from guacamole.providers.codex import CodexReasoning

project = Project(
    workspace, sandbox=Path("results/project"), tools=tools,
    reasoning=CodexReasoning(),
)
try:
    result = await project.run(ProjectRequest(
        description=your_project_description,
        documents=tuple(document_paths),
        context=ContextSpec(
            instructions="Use the supplied designs and experimental evidence.",
            max_input_tokens=128_000,
            reserved_output_tokens=4_000,
        ),
    ))
    print(result.model_dump_json(indent=2))
finally:
    await project.drain()
    project.close()
```

The Chief records typed requirements, alternatives, deliverables and its selected
work plans. Workers are created from validated task IDs, with their
own objective, context, result schema, tool/peer grants and budgets. Workers can
request information and reply directly to allowed peers through persistent inboxes.
Each provider invocation saves its context before dispatch. Pinned material is
never silently dropped; oversized context blocks the invocation. Optional excerpts
and inbox messages that do not fit have explicit deferral records. Summaries cite
their original revisions. Binary or large documents require a supplied reader
returning `SourceExcerpt`; originals remain available and unparsed inputs stay open.

PDR and CDR packages contain manifests, copied editable artifacts, record snapshots,
readable review summaries and communication/tool traces. Required artifacts,
verification kinds, current dependencies and open items determine readiness.
Human acceptance is a separate operation on the exact returned
review `Ref`:

```python
accepted = project.reviews.accept(
    ready_review_ref, reviewer="Your name", disposition="Accepted with recorded disposition"
)
result = await project.run(resume=result.run_id)
```

A CDR plan requires a current human-accepted PDR. Changing cited inputs invalidates
dependent evidence and baseline readiness. Missing tools, source metadata, failed
analysis, and outstanding evidence keep a project incomplete. The engine cannot
manufacture CAD, electronics, software builds, or physical test results when the
supplied tools cannot produce them.

Supply project documents through `ProjectRequest.documents` as shown above.
Actual rocket PDR/CDR delivery is **not yet validated**;
the offline tests exercise orchestration with labelled fixtures.

## Human questions and corrections

The Chief and every worker can issue a typed `AskHuman` action with a question,
suggested choices, and references to relevant records. Its question, originating
context, rationale, replies, and request status are saved in the project history.
By default, the requesting agent waits; independent agents can continue. Agents
can use `blocking=False` for a question that allows their own work to continue.

Inspect pending questions and answer one from your script:

```python
for entry in project.human.inbox(run_id=result.run_id):
    print(entry.message.request_id, entry.message.payload)

source = project.human.reply(
    request_id, "The payload mass is now 2.5 kg.", author="Khoi"
)
result = await project.run(resume=result.run_id)
```

`ProjectResult.human_requests` lists pending request IDs. A required question
returns `awaiting_human`; ready PDR/CDR packages return `awaiting_review` and also
create human requests. These requests survive closing and reopening the workspace.
`project.human.inbox(pending_only=False)` includes answered and superseded requests.
Review questions require `project.reviews.accept(...)` with the exact review `Ref`;
an ordinary reply cannot approve a baseline. Request changes with
`accepted=False` and the corrections in `disposition`.

You can also correct the project at any stage without waiting for a question:

```python
source = project.human.interject(
    "Use the revised payload envelope in drawing B.",
    author="Khoi",
    run_id=result.run_id,
    references=(drawing_ref,),
)
result = await project.run(resume=result.run_id)
```

Replies, corrections, and rejected reviews reopen the Chief for replanning.
Human input is pinned in subsequent agent context and captured in new decisions. The
returned source `Ref` lets the Chief cite the correction when amending typed
requirements. Previous wording and decisions remain in history. Current plans
and dependent results become stale, and unfinished workers are superseded so the
Chief can assign replacement tasks under a fresh validated plan.

During a live run, call these synchronous methods from another coroutine on the
same event loop, or use the optional WebSocket connection. `run_id` can be omitted
when interjecting into the current runtime. Corrections take effect at the next
runtime boundary: a provider response already in flight cannot dispatch its old
proposal. Running tools retain their actual status and their eventual results are
saved as stale when their plan changed. Human input is never silently dropped to
fit a context budget; an oversized context blocks for correction.
Records explicitly requested with `read` are required in the next prompt and
take priority over older optional sources. If they cannot fit, the run blocks
with a context error instead of repeatedly requesting omitted content.

A ping is a persistent local inbox entry plus a `human.requested` event. Scripts
can inspect `project.events()` or use WebSocket `subscribe` to receive it live.

## Inspection, restart, and transports

```python
with Project(workspace, read_only=True) as history:
    history.inbox(agent_id)
    history.sent(agent_id)
    history.requests(status="blocked")
    history.trace(request_id)
    history.context(packet_id)
    history.events(after=sequence, task="task-id")
    history.export(Path("timeline.jsonl"))
```

Read-only inspection can run beside the active process without changing records.
Rationales are explicit agent/provider summaries, not private model deliberation.
Delivery, context inclusion, acknowledgement, and execution completion are distinct.
On a runtime restart, unfinished tools become `uncertain`; agents become
`interrupted`. Nothing is replayed merely by opening a workspace. Explicit retries
retain the request ID and append an attempt. Unsafe/uncertain operations require a
recorded user reconciliation. A running Python thread may finish after a timeout or
cancellation request; Guacamole never reports that it was killed. Providers needing
hard termination must manage a subprocess. Drain outstanding tools before closing.

Local MCP is generated through the [official Python SDK](https://github.com/modelcontextprotocol/python-sdk):

```python
from guacamole.tools.mcp import ToolSession, serve_stdio
await serve_stdio(ToolSession(project, grants=(tool.definition.grant,)))
```

Both listing and invocation enforce the host-configured grants. MCP and Python use
the same executor. The transport is stdio and opens no network listener.

For optional scripting control, install `uv sync --extra websocket`, then use
`guacamole.websocket.WebSocketBridge(ToolSession(project))` and its async `serve()`
context manager. It binds only to loopback and requires
`Authorization: Bearer <bridge.token>`. Commands are typed JSON envelopes:

```json
{"id":"call-1","command":{"kind":"call","tool":"temperature_rise@1","arguments":{"power_w":20.0,"resistance_k_w":0.5}}}
```

`call` returns a job ID; `status` queries its saved result. Reusing a mutation ID
with identical content returns the recorded response without repeating execution.
`events` and `subscribe` accept `after` for cursor recovery. Use a separate
connection for a subscription. No listener starts automatically.

Host scripting sessions also accept `human_inbox`, `reply_human`, `interject`, and
`review_disposition` commands. Agent sessions cannot use human controls. For example:

```json
{"id":"reply-1","command":{"kind":"reply_human","request_id":"QUESTION_ID","author":"Khoi","text":"Use the revised payload mass of 2.5 kg."}}
```

These commands call the same Python APIs and use the same mutation deduplication.
Keep `project.run(...)` running in the host script for live interaction; if it has
returned while awaiting input, the host resumes it after recording the response.

## Repository layout

The runtime lives in `src/guacamole` and tests live in `tests`.
[outline.txt](outline.txt) lists the files and their responsibilities.
Engineering tools, their schemas, and numerical dependencies belong in supplied
project code or separately installed packages.

### Sounding-rocket example

[kookaburra.py](examples/sounding_rocket/kookaburra.py) uses the supplied
`technical_documents/` and `tooling/` trees, including `nsga.py`, plus the
`Parachute-Opening-Shock/` checkout at the repository root when present.
Edit its configuration constants, install Codex CLI, and sign in with your ChatGPT
account. Kookaburra uses local Codex processes with GPT-6 Astra; no API key or
`.env` file is needed. No script arguments are required:

```bash
codex login
uv run examples/sounding_rocket/kookaburra.py
```

For the module entry point, install the example's dependencies into the project environment:

```bash
uv sync --extra sounding-rocket
.venv/bin/python -m examples.sounding_rocket.kookaburra
```

The script selects the same extra using
[uv inline metadata](https://docs.astral.sh/uv/guides/scripts/); `python -m` does not
install inline dependencies. Startup checks for Codex and missing readers before reasoning.
It registers typed
file/document access, command execution, and verification tools. Backend packages
retain their own dependencies and can use separate interpreters via
`PYTHON_EXECUTABLES`. PDF/PPTX extraction reads text; figures still require visual
interpretation. XLSX cell addresses/formulas and OpenRocket XML remain traceable.

Outputs go to `examples/sounding_rocket/results/`; SQLite history goes to
`examples/sounding_rocket/.guacamole/`. The host prints human questions and the
authenticated loopback WebSocket connection details, waits at human/review gates,
and resumes after replies or review dispositions. Rerunning resumes a single saved
run; `RESUME_RUN_ID` selects one if several exist. Imported backend availability
and complete rocket engineering remain unvalidated until the configured tools run.
Startup applies the current `CONTEXT` limits and `BUDGET` to the saved run and
Chief, preserving their instructions, references and accumulated usage. Worker
allocations remain those of their approved tasks. Input is capped at the configured
provider capacity minus reserved output; startup prints the effective limit.
The control URL accepts authenticated WebSocket clients; opening it as an HTTP
page returns connection instructions. Reader open items remain pending until the
agent extracts and reviews the source content.

## Checks

```bash
uv sync --extra sounding-rocket
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -v
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src tests
.venv/bin/ty check
uv lock --check
```
