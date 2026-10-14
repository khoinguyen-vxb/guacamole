Graph based Unified Agentic Coordination Architecture for Multidisciplinary Optimization and Lifecycle Engineering (guacemole)

## Local runtime

Guacamole exposes supplied Python tools, coordinates a Chief Engineer and dynamic
workers, and keeps their context, messages, decisions, artifacts, and review history
in a local SQLite workspace. There is no platform frontend or HTTP service.

```bash
uv sync
```

It runs on Linux and macOS (the workspace lock uses `fcntl`; on Windows use WSL),
with Python 3.13.3 or newer, which `uv sync` installs if needed.

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

Codex input budgeting uses a local `o200k_base` estimate plus 10% and 1,024 tokens
of headroom (`token_count_method="tiktoken_o200k_base_estimate_10pct_plus_1024"`);
`guacamole.providers.claude.ClaudeReasoning` uses a conservative UTF-8 byte upper
bound (`utf8_upper_bound`), since no local tokenizer matches Claude's. Neither makes
API token-count calls, and the byte bound may defer more optional source material
than an exact tokenizer. `reserved_output_tokens` reserves context headroom; the CLI
controls generation limits and its own prompt overhead. See [Codex non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode).

Those counts are budget estimates. What a provider actually used comes back on
`AgentTurn.usage` (stored with each `agent_turn` record): full-price input, cache
reads, cache writes, output and, where reported, cost. The Claude CLI reports all
of them, `codex exec --json` its input, cached input and output, and LiteLLM the
provider's usage plus its own cost estimate.

Prompts lead with the fields that change least: instructions and schemas, then
the agent and its sources, then inbox messages and per-turn `state`.
`ContextPacket.cache_breakpoints` marks where the first two prefixes end. The CLI
providers send the first prefix with their system instructions, which each CLI
caches, and the rest as the user message; `LiteLLMReasoning` marks both prefixes
with `cache_control` for Claude models (`prompt_caching=` overrides; OpenAI caches
prefixes without markers). `ContextPacket.components` records the characters each
part of a prompt takes.

For API access, `guacamole.providers.litellm.LiteLLMReasoning` reaches any
[LiteLLM provider](https://docs.litellm.ai/docs/providers) (`uv sync --extra litellm`).
Swap providers by model string: `LiteLLMReasoning("openai/gpt-6-astra")` or
`LiteLLMReasoning("anthropic/claude-opus-5-5", effort="high")`. Credentials come
from each provider's environment variables (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`,
...), not Codex or Claude CLI logins. Capacity comes from LiteLLM's model map
unless you pass `context_capacity_tokens`; other keyword arguments such as
`api_base` or `num_retries` pass through to `litellm.acompletion`. Token counts use
LiteLLM's local tokenizer plus 10% and 1,024 tokens of headroom
(`token_count_method="litellm_estimate_10pct_plus_1024"`), with no API calls.
The model's capacity is checked separately from each agent's configured budget.

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
never silently dropped. When required material exceeds an agent's budget, the
runtime raises that budget to the run's `max_input_tokens` (capped by provider
capacity) and records `agent.budget_raised`; beyond that, the invocation blocks.
Optional excerpts and inbox messages that do not fit have explicit deferral records.
Summaries cite their original revisions. Each prompt's `state` lists current
records and unfinished, failed or interrupted requests; stale records and completed
or cancelled requests stay in history but are left out, as are records already
pinned among the agent's sources. Workers see only their own tool records and the
requests they made or received; the Chief sees all of them. An agent's last 8 tool
calls repeat as bounded previews (about 1,000 characters of arguments and 2,000 of
result, cut with a marker) with the `tool_result` ref to read for the full value;
the latest result arrives whole. Binary or large documents require a supplied reader
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

## Worker reasoning tiers

`Project(tiers={...})` names further reasoning providers that workers may run on;
the Chief and systems engineer always use `reasoning`. A work-plan task names its
`family`, the kind of work, and the runtime spawns its worker on the cheapest tier
qualified for that family. A `Qualification` record qualifies a tier when it passed
at least `MIN_PASS_RATE` (80%) of its measured trials in the family; qualified tiers
are ranked by measured cost per verified completion, so failed trials count against
a cheap tier. Work no tier is qualified for runs on the Chief's model, and a task's
`tier` overrides the choice. The Chief's instructions list each tier with its
records. A worker keeps its tier on restart, and a tier dropped from the
configuration blocks it rather than moving it to another model. A replacement plan
reroutes running workers, which is how the Chief escalates a task. Each spawn
records an `agent.routed` event with the reason; every `provider.dispatched` event
records the tier, model and effort.

```python
from pydantic import TypeAdapter
from guacamole import Project, Qualification
from guacamole.providers.claude import ClaudeReasoning

records = TypeAdapter(list[Qualification]).validate_json(
    Path("examples/qualification/qualifications.json").read_bytes()
)
project = Project(
    workspace,
    reasoning=ClaudeReasoning(),
    tiers={
        "haiku-low": ClaudeReasoning(model="claude-haiku-5-5", effort="low",
                                     context_capacity_tokens=1_000_000),
        "sonnet-medium": ClaudeReasoning(model="claude-sonnet-5-5", effort="medium",
                                         context_capacity_tokens=1_000_000),
    },
    qualifications=records,
)
```

Records match a tier by provider, model and effort. They come from
[qualify.py](examples/qualification/qualify.py): a scripted Chief, which makes no
model calls, gives every tier the same extraction, simulation, implementation and
diagnosis tasks, each tier and trial in its own project. A check the workers never
see verifies each result, and the event log supplies turns, rejected actions, time
and CLI-reported cost, including provider retries of malformed responses.

```bash
uv run python examples/qualification/qualify.py --trials 3
```

Records only qualify a profile on these four tasks with the current worker
instructions; rerun the harness after changing either, and add tasks from real
project work before relying on a family.

## Runtime watchdog

Pass a `Watchdog` to start a supervisor beside the Chief for every run:

```python
from guacamole import Watchdog

project = Project(
    workspace, sandbox=Path("results/project"), tools=tools,
    reasoning=CodexReasoning(),
    watchdog=Watchdog(CodexReasoning(web_search=False), report_interval_s=600),
)
```

Its reasoning provider can be a different model; `Watchdog()` reuses the project's.
Either way the watchdog runs a copy at the lowest reasoning effort (`effort="low"`
for `CodexReasoning`, `ClaudeReasoning` and `LiteLLMReasoning`) to reserve usage budget; the project's
provider keeps its own effort. `CodexReasoning(effort=...)` defaults to `"ultra"`.
It polls the activity log every `poll_s` seconds without calling a model. When an
agent's last `loop_turns` actions were all rejected or identical, or its last prompt
used at least `compact_at` of its input budget, the watchdog's model receives the
recent turns, cited references that are stale, superseded or unknown (with current
revisions), and the agent's largest optional sources. It then sends that agent a
`Note@1` from sender `watchdog` (waking it if waiting); when earlier notes have not
helped it is instructed to ask the human a non-blocking question instead. Agents compact their own context in
response; pinned material is never dropped. Every `report_interval_s` and at the end
of each run it emits a `watchdog.report` event with per-agent status, steps,
context use, deferred items, input sent and objective, plus pending human requests,
open items, reviews, dispatched input tokens and interventions. `details["tokens"]`
audits the run's tokens: estimated input sent and how much of it went to rejected
turns, provider-reported usage with its cache hit rate, the share of prompt
characters per component (such as `state.recent_tool_calls` or `sources.selected`),
and the watchdog's own calls. `details["text"]` is a readable
summary; the Electronic Hopper and Kookaburra launchers print it. Watchdog failures
are recorded as `watchdog.failed` events and never stop the run. Pass the request
from `project.requests(agent="watchdog")` to `project.trace` for its packets, turns and notes.

## Systems engineer and SysML truth

Pass a `SystemsEngineer` to make a SysML v2 model the project's deterministic
source of truth for every agent and decision:

```python
from guacamole import SystemsEngineer

project = Project(
    workspace, sandbox=Path("results/project"), tools=tools,
    reasoning=CodexReasoning(),
    systems_engineer=SystemsEngineer(),
)
```

Every run then starts a Systems Engineer agent beside the Chief. It writes the model
as SysML v2 text through a `model` action that cites the records the revision reflects.
A revision is recorded only after the
[SysML Toolkit](https://github.com/Open-MBEE/sysml-sdk) (the `sysml` package) parses
it and these checks pass:

- references resolve and qualified names are unique;
- each current recorded requirement is a SysML requirement with its ID
  (`requirement <'R1'> liftoffMass { ... }`), and each top-level SysML requirement is
  recorded; derived requirements are nested in the requirement they refine;
- each recorded `Constraint` appears exactly as a `require constraint`, for example
  `{ v.mass <= 50 [kg] }`, on a feature named as its metric, in the same unit;
- each `satisfy R by X` holds for the values `X` declares.

A rejected revision returns its full report to the agent. The current revision is
mirrored to `sandbox/sysml/` with `report.json`; history stays in the `system_model`
record. While the model is missing, stale (a cited record or a requirement changed)
or lacks a recorded requirement, every `decide` is blocked. Candidates whose `metrics`
contradict a modeled bound are ineligible; a metric key is the bounded feature's name
or qualified name, reported in the model's unit. Each new revision invalidates current
decisions it contradicts and notifies their authors. Decision records keep the model
revision they were validated against. Every prompt's `state.system_model` shows the
revision, status, bounds and amendments, and any worker can message the Systems
Engineer directly.

Changes that current records do not authorize go through amendments. The Systems
Engineer proposes changed files with `amend`; the runtime validates them, records the
requirement, bound, element and text differences, and notifies the Chief. A Chief
`decide` whose selected candidate cites the amendment adopts it, and selecting another
candidate rejects it; the Systems Engineer then implements exactly the adopted change.
Amendments that change requirements cannot be adopted until requirement records with
human-sourced quotes agree. An unusable model or an undecided or unimplemented
amendment keeps PDR/CDR packages from becoming ready. Packages include the reviewed
model, acceptance requires that revision to be current, and refining the model later
does not withdraw an accepted review.

Scripts use the same API without the agent: `await project.sysml.commit(summary=...,
files={...}, derived_from=(ref,))`, `await project.sysml.amend(Amendment(...))`,
`project.sysml.status(amendment_id)` and `await project.sysml.validate(files)`. A
project with neither a systems engineer nor a committed model behaves as before.
Existing `.sysml` and `.kerml` files supplied through `ProjectRequest.documents` are
ingested as text. `SystemsEngineer(budget=..., context=...)` overrides the run's budget
and the Chief's context. The first validation in a process loads the SysML standard
library (seconds); later ones take milliseconds. Only comparisons of a feature with a
literal or valued quantity, joined by `and`, are machine-checked; other constraints
are reported as unchecked warnings. Units are compared as written, without conversion.

## Context middleware

Pass middleware to run around every Chief and worker invocation. Install the extras
you use: `uv sync --extra langchain --extra graphiti --extra mem0`. The `graphiti`
extra embeds FalkorDB (`falkordblite`); its Linux wheels need glibc 2.39 or newer.

```python
from graphiti_core import Graphiti
from graphiti_core.driver.falkordb_driver import FalkorDriver
from langchain.agents.middleware import (
    ClearToolUsesEdit, ContextEditingMiddleware, SummarizationMiddleware,
)
from langchain_litellm import ChatLiteLLM
from mem0 import AsyncMemory
from redislite.async_falkordb_client import AsyncFalkorDB

from guacamole.middleware import GraphitiMemory, LangChainMiddleware, Mem0Memory

# Embedded FalkorDB; at exit await graph_db.client.shutdown(), then .close().
graph_db = AsyncFalkorDB(".guacamole/graph.db", serverconfig={"appendonly": "yes"})
graphiti = Graphiti(graph_driver=FalkorDriver(falkor_db=graph_db))
await graphiti.build_indices_and_constraints()
project = Project(
    workspace, sandbox=Path("results/project"), tools=tools,
    reasoning=CodexReasoning(),
    middleware=(
        LangChainMiddleware(SummarizationMiddleware(
            ChatLiteLLM(model="anthropic/claude-haiku-5-5"),
            trigger=("tokens", 60_000), keep=("messages", 12),
        )),
        LangChainMiddleware(ContextEditingMiddleware(
            edits=[ClearToolUsesEdit(trigger=40_000, keep=4)],
        )),
        GraphitiMemory(graphiti),
        Mem0Memory(AsyncMemory()),
    ),
)
```

Middleware sees only an agent's optional context. Pinned requirements, human input
and just-requested reads are never shown to it or removed.

- `LangChainMiddleware` presents summaries, then selected sources oldest first,
  as a LangChain conversation: read request, read tool call, source as tool result.
  `SummarizationMiddleware` compacts older sources into a stored `Summary` citing
  their exact revisions and updates the agent's context, like the `compact` action.
  The adapter sets `trim_tokens_to_summarize=None`, so the summary prompt holds
  every summarized source; choose a summary model whose context fits `trigger`.
  `ContextEditingMiddleware` clears older source results for that
  invocation only. Each one is listed in `ContextPacket.deferred`, and reading it
  again makes it the most recent.
- `GraphitiMemory` adds each agent turn (rationale, action, observation) to one
  knowledge graph per project and recalls its most relevant time-stamped facts.
- `Mem0Memory` stores turns per task (`user_id` is the project, `agent_id` the task)
  and recalls that task's memories across runs and replacement workers.

Recall queries use the agent's objective and last observation. Recalled items appear
under `memory` in the prompt, after all other optional material, and are deferred
first when the budget is tight. Agents treat them as unverified hints, not evidence.
Turns sent for memory extraction are truncated to 16,000 characters; full records
stay in SQLite. Each library keeps its own model, embedder and store configuration;
Graphiti and mem0 default to OpenAI and read `OPENAI_API_KEY`. Failures are recorded
as `middleware.failed` events with the hook and error type only, and never stop
the run. Memory ingestion runs inline after each action.

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

### Wall-bracket benchmark

[examples/bracket](examples/bracket/README.md) runs natural-language briefs for one
product family through to a ready PDR review package: parametric FreeCAD CAD, STEP,
drawing and BOM, all checked and traced to requirements, with no manual CAD or
document work. Needs FreeCAD and a logged-in Codex CLI.

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
uv sync --extra sounding-rocket --extra langchain --extra graphiti --extra mem0
.venv/bin/python -m examples.sounding_rocket.kookaburra
```

Kookaburra and the Electronic Hopper both run context middleware. Context editing
always runs: above `CLEAR_AT_TOKENS` of optional sources, all but an agent's 8
latest reads are left out of that call. With `OPENAI_API_KEY` set, sources above
`SUMMARIZE_AT_TOKENS` are also summarized by `SUMMARY_MODEL` (`openai/gpt-6-luna`)
through LiteLLM. Every turn also feeds Graphiti and mem0 memory, which use OpenAI's
default models and are billed to that key. The graph (embedded FalkorDB with an
append-only log) and the mem0 vectors live in the example's `.guacamole/`.
Library telemetry is disabled. Memory starts empty for an existing run; earlier
turns are not imported.

The script selects the same extras using
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
uv sync --all-extras
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -v
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src tests
.venv/bin/ty check
uv lock --check
```
