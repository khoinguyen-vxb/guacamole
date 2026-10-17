"""Run tool processes on the host or in a container, behind one interface.

runner(project, container) gives a HostRunner, or a ContainerRunner for a
Container spec. A container sees the sandbox at /work (read-write) and each extra
input read-only at /inputs/<n>; path() translates host paths in and refuses any
outside every mount. Its image is pinned by digest, so results can record exactly
which build produced them. By default it gets no network, no capabilities, no
privilege escalation and none of the host's environment. Every run is a fresh
container named and labelled with its project and request, so a timeout or
cancellation kills the container itself rather than only the engine client, and
reap() removes any a crashed host left behind.
"""

import asyncio
import os
import re
import signal
import subprocess
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from mcp import StdioServerParameters

from ..contracts import uid
from .execution import CURRENT_REQUEST

if TYPE_CHECKING:
    from ..project import Project

HOST = ("PATH", "HOME", "USER", "LANG", "LC_ALL", "TMPDIR")
# What an engine client needs to reach its daemon; containers never see these.
ENGINE = (
    *HOST,
    "DOCKER_HOST",
    "DOCKER_CONFIG",
    "DOCKER_CONTEXT",
    "DOCKER_CERT_PATH",
    "DOCKER_TLS_VERIFY",
    "CONTAINER_HOST",
    "XDG_RUNTIME_DIR",
)
PINNED = re.compile(r"(?:[^\s@]+@)?sha256:[0-9a-f]{64}")
WORK = PurePosixPath("/work")
INPUTS = PurePosixPath("/inputs")
PROJECT_LABEL = "guacamole.project"


def _environment(keys: Sequence[str]) -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k in keys}


@dataclass(frozen=True)
class Container:
    """How to run tools in a container; runner() binds it to a project."""

    image: str  # name@sha256:<digest>, or a local image ID sha256:<digest>
    engine: str = "docker"  # Or podman
    inputs: tuple[Path, ...] = ()  # Mounted read-only at /inputs/<n>
    env: Mapping[str, str] = field(default_factory=dict)
    network: bool = False
    user: str | None = field(default_factory=lambda: f"{os.getuid()}:{os.getgid()}")
    shm_size: str | None = None  # MPI needs more than the default, e.g. "1g"
    memory: str | None = None
    cpus: float | None = None

    def __post_init__(self) -> None:
        if not PINNED.fullmatch(self.image):
            raise ValueError(
                f"Pin image {self.image!r} by digest (name@sha256:...); "
                f"`{self.engine} images --digests` lists them"
            )


@dataclass(frozen=True)
class Launch:
    argv: list[str]
    env: dict[str, str]
    cwd: Path | None
    container: str | None  # The container name, to kill it


class Runner:
    runtime = "host"  # What results record as having run them

    def path(self, host: Path) -> str:
        """host as the process sees it."""
        raise NotImplementedError

    def launch(
        self, command: Sequence[str], cwd: Path, *, interactive: bool = False
    ) -> Launch:
        raise NotImplementedError

    def kill(self, launch: Launch) -> None:
        """Stop what launch started beyond the client process; nothing on the host."""

    async def _stop(self, process: asyncio.subprocess.Process, launch: Launch) -> None:
        await asyncio.to_thread(self.kill, launch)
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        await process.wait()

    async def run(
        self, command: Sequence[str], *, cwd: Path, log: Path, timeout_s: float
    ) -> tuple[int, bool]:
        """Run command with its output in log; (returncode, timed_out)."""
        launch = self.launch(command, cwd)
        with log.open("wb") as output:
            process = await asyncio.create_subprocess_exec(
                *launch.argv,
                cwd=launch.cwd,
                env=launch.env,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=output,
                stderr=asyncio.subprocess.STDOUT,
                start_new_session=True,
            )
            try:
                await asyncio.wait_for(process.wait(), timeout_s)
            except (TimeoutError, asyncio.CancelledError) as exc:
                await self._stop(process, launch)
                if isinstance(exc, asyncio.CancelledError):
                    raise
                return -1, True
        return process.returncode if process.returncode is not None else -1, False

    async def capture(
        self, command: Sequence[str], *, cwd: Path, timeout_s: float
    ) -> tuple[int, str]:
        """Run command and return (returncode, combined output)."""
        launch = self.launch(command, cwd)
        process = await asyncio.create_subprocess_exec(
            *launch.argv,
            cwd=launch.cwd,
            env=launch.env,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            output, _ = await asyncio.wait_for(process.communicate(), timeout_s)
        except (TimeoutError, asyncio.CancelledError) as exc:
            await self._stop(process, launch)
            if isinstance(exc, asyncio.CancelledError):
                raise
            # Not TimeoutError: the runtime would read that as its own turn timing out.
            raise RuntimeError(f"{command[0]} took over {timeout_s:g} s") from None
        return process.returncode or 0, output.decode(errors="replace")

    def check(
        self, command: Sequence[str], *, cwd: Path, timeout_s: float = 300
    ) -> str:
        """Run command synchronously, as host scripts do while registering tools."""
        launch = self.launch(command, cwd)
        try:
            result = subprocess.run(
                launch.argv,
                cwd=launch.cwd,
                env=launch.env,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired:
            self.kill(launch)
            raise RuntimeError(f"{command[0]} took over {timeout_s:g} s") from None
        output = (result.stdout + result.stderr).decode(errors="replace")
        if result.returncode:
            raise RuntimeError(
                f"{command[0]} exited {result.returncode}:\n{output[-2000:]}"
            )
        return result.stdout.decode(errors="replace")

    def server(self, command: Sequence[str], *, cwd: Path) -> StdioServerParameters:
        """Parameters that start command as a stdio MCP server."""
        launch = self.launch(command, cwd, interactive=True)
        return StdioServerParameters(
            command=launch.argv[0],
            args=launch.argv[1:],
            env=launch.env,
            cwd=launch.cwd,
        )


@dataclass(frozen=True)
class HostRunner(Runner):
    """Host processes with the user's OS permissions: a convention, not a sandbox."""

    env: Mapping[str, str] = field(default_factory=dict)  # Over the minimal host env

    def path(self, host: Path) -> str:
        return str(host)

    def launch(
        self, command: Sequence[str], cwd: Path, *, interactive: bool = False
    ) -> Launch:
        return Launch(list(command), {**_environment(HOST), **self.env}, cwd, None)


class ContainerRunner(Runner):
    def __init__(self, project: "Project", container: Container) -> None:
        self.container = container
        self.project_id = project.store.project_id
        self.runtime = container.image
        mounts = [(project.sandbox, WORK, False)]
        mounts += [
            (p.resolve(), INPUTS / str(i), True) for i, p in enumerate(container.inputs)
        ]
        for root, _, _ in mounts:
            if "," in str(root):
                raise ValueError(f"Mount paths cannot contain commas: {root}")
        self.mounts = tuple(mounts)

    def path(self, host: Path) -> str:
        host = host.resolve()
        holding = [m for m in self.mounts if host == m[0] or host.is_relative_to(m[0])]
        if not holding:
            raise ValueError(
                f"{host} is outside every container mount (sandbox and inputs)"
            )
        root, mounted, _ = max(holding, key=lambda m: len(m[0].parts))
        return str(mounted / host.relative_to(root))

    def launch(
        self, command: Sequence[str], cwd: Path, *, interactive: bool = False
    ) -> Launch:
        spec = self.container
        name = f"guacamole-{self.project_id[:12]}-{uid()[:12]}"
        argv = [
            spec.engine,
            "run",
            "--rm",
            "--name",
            name,
            "--label",
            f"{PROJECT_LABEL}={self.project_id}",
            "--label",
            f"guacamole.request={CURRENT_REQUEST.get() or 'script'}",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--workdir",
            self.path(cwd),
        ]
        if interactive:
            argv.append("--interactive")
        if not spec.network:
            argv += ["--network", "none"]
        if spec.user:
            argv += ["--user", spec.user]
        if Path(spec.engine).name == "podman":
            # Rootless podman maps --user through subordinate IDs unless keep-id
            # maps the host user onto itself, and SELinux hosts deny bind mounts
            # without a relabel, which would rewrite the labels of host files.
            if spec.user:
                argv += ["--userns", "keep-id"]
            argv += ["--security-opt", "label=disable"]
        for flag, value in (
            ("--shm-size", spec.shm_size),
            ("--memory", spec.memory),
            ("--cpus", spec.cpus),
        ):
            if value is not None:
                argv += [flag, str(value)]
        for root, mounted, read_only in self.mounts:
            mount = f"type=bind,source={root},target={mounted}"
            argv += ["--mount", mount + (",readonly" if read_only else "")]
        # An arbitrary --user has no home directory in the image.
        env = ({"HOME": "/tmp"} if spec.user else {}) | dict(spec.env)
        for key, value in sorted(env.items()):
            argv += ["--env", f"{key}={value}"]
        return Launch([*argv, spec.image, *command], _environment(ENGINE), None, name)

    def kill(self, launch: Launch) -> None:
        if launch.container:
            with suppress(OSError, subprocess.SubprocessError):
                subprocess.run(
                    [self.container.engine, "kill", launch.container],
                    env=_environment(ENGINE),
                    capture_output=True,
                    timeout=60,
                    check=False,  # Gone already: it exited or was never started
                )

    def reap(self) -> int:
        """Remove this project's containers; any running now outlived their host."""
        engine, env = self.container.engine, _environment(ENGINE)
        try:
            listed = subprocess.run(
                [
                    engine,
                    "ps",
                    "--all",
                    "--quiet",
                    "--filter",
                    f"label={PROJECT_LABEL}={self.project_id}",
                ],
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
                check=True,
            ).stdout.split()
        except (OSError, subprocess.SubprocessError) as exc:
            raise RuntimeError(
                f"{engine} is not installed, or its daemon is not running"
            ) from exc
        if listed:
            subprocess.run(
                [engine, "rm", "--force", *listed],
                env=env,
                capture_output=True,
                timeout=120,
                check=False,  # A container --rm removed meanwhile needs nothing
            )
        return len(listed)


def runner(
    project: "Project",
    container: Container | None = None,
    env: Mapping[str, str] | None = None,
) -> Runner:
    """Host processes with env over the minimal host environment, or containers.

    A ContainerRunner first reaps the project's leftover containers, so call this
    while registering tools, before any work starts.
    """
    if container is None:
        return HostRunner(dict(env or {}))
    contained = ContainerRunner(project, container)
    contained.reap()
    return contained
