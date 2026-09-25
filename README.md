Graph based Unified Agentic Coordination Architecture for Multidisciplinary Optimization and Lifecycle Engineering (guacemole)

## Local runtime

Guacamole exposes supplied Python tools, coordinates a Chief Engineer and dynamic
workers, and keeps their context, messages, decisions, artifacts, and review history
in a local SQLite workspace. There is no platform frontend or HTTP service.

```bash
uv sync
uv run python examples/cross_domain.py
```

The example registers beam and thermal calculations directly. Tool input/output
annotations generate strict runtime validation and MCP schemas. New tools do not
require a solver adapter, agent role, or skill file in Guacamole.

```python
import asyncio
from pathlib import Path
from guacamole import Project, ToolRegistry

def temperature_rise(power_w: float, resistance_k_w: float) -> float:
    """Temperature rise in kelvin for a lumped thermal resistance."""
    return power_w * resistance_k_w

async def main():
    tools = ToolRegistry()
    tool = tools.register(temperature_rise, version="1", retry_safe=True)
    with Project(Path(".guacamole/example"), tools=tools) as project:
        job = project.submit(tool, {"power_w": 20.0, "resistance_k_w": 0.5})
        print(await job.collect())
        print(project.trace(job.id))

asyncio.run(main())
```

Use fully annotated functions, bound methods, dataclasses, or Pydantic models.
Declare physical bounds, units, frames, and shapes in provider-owned models and
validators. Missing annotations, `Any`/opaque objects, undeclared input fields,
coercible strings, nonfinite values, and invalid outputs are rejected. A successful
tool execution does not imply convergence or physical acceptance.

Tools write native files under the project workspace and return
`ProducedFile.from_path(path)`. The executor snapshots the bytes before success.
Explicit acceptance tools return `VerificationResult`. Publishing evidence checks
that the verification actually used the claimed artifact revision. Native solver
objects remain inside the provider. Keep credentials in provider configuration or
environment variables rather than tool arguments, documents, or model context.

## Autonomous projects

Configure a reasoning provider and a **mandatory Jev provider**. The initial
reasoning adapter is `guacamole.providers.astra.AstraReasoning`, using the requested
`gpt-6-astra` through the OpenAI Responses API. It reads `OPENAI_API_KEY` at call
time; it does not reuse Codex CLI login credentials. Token counting uses the
[official input-token endpoint](https://developers.openai.com/api/docs/guides/token-counting)
for the exact saved prompt, including tool/action schemas and context. The model's
documented capacity is checked separately from each agent's configured budget.

No Jev implementation has been selected for this project. Supply an object matching
`JevProvider`: `name`, `version`, `is_test_double`, and
`async decide(request_id: str, request: DecisionRequest) -> DecisionResult`.
The runtime fills `DecisionRequest.context` with the resolved, versioned evidence
and input snapshots before calling Jev; the provider does not need database access.
Failure, abstention, stale evidence, and invalid selections block dependent work.
There is no default or fallback decision provider. Test doubles are explicitly
labelled in decision records, review manifests, and project results.

```python
from guacamole import ContextSpec, Project, ProjectRequest
from guacamole.providers.astra import AstraReasoning

project = Project(workspace, tools=tools, reasoning=AstraReasoning(), jev=your_jev)
try:
    result = await project.run(ProjectRequest(
        description=your_project_description,
        documents=tuple(document_paths),
        context=ContextSpec(
            instructions="Use the supplied designs and experimental evidence.",
            max_input_tokens=32_000,
            reserved_output_tokens=4_000,
        ),
    ))
    print(result.model_dump_json(indent=2))
finally:
    await project.drain()
    project.close()
```

The Chief proposes typed requirements, alternatives, deliverables and work plans.
Jev selects eligible plans. Workers are created from approved task IDs, with their
own objective, context, result schema, tool/peer grants and budgets. Workers can
request information and reply directly to allowed peers through persistent inboxes.
Each provider invocation saves its context before dispatch. Pinned material is
never silently dropped; oversized context blocks the invocation. Optional excerpts
and inbox messages that do not fit have explicit deferral records. Summaries cite
their original revisions. Binary or large documents require a supplied reader
returning `SourceExcerpt`; originals remain available and unparsed inputs stay open.

PDR and CDR packages contain manifests, copied editable artifacts, record snapshots,
readable review summaries and communication/tool traces. Required artifacts,
verification kinds, current dependencies and open items are checked before Jev's
readiness decision. Human acceptance is a separate operation on the exact returned
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

The [sounding rocket script](examples/sounding_rocket/run.py) accepts a
`module:function` factory returning a Project with your tools and Jev configured.
It preserves the requested brief and accepts repeated `--document` arguments.
Actual rocket PDR/CDR delivery and real Jev integration are **not yet validated**;
the offline tests exercise orchestration with labelled fixtures.

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
On a runtime restart, unfinished tools/Jev calls become `uncertain`; agents become
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

## Repository layout

The runtime lives in `src/guacamole`, runnable scripts in `examples`, and checks in
`tests`. [outline.txt](outline.txt) lists the files and their responsibilities.
Engineering tools, their schemas, and numerical dependencies belong in supplied
project code or separately installed packages.

## Checks

```bash
uv sync --extra websocket
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -v
.venv/bin/ruff check src examples tests
.venv/bin/ruff format --check src examples tests
.venv/bin/ty check
uv lock --check
```
