"""Generated-code execution boundary with deterministic simulation support.

The sandbox is intentionally narrow: generated snippets receive JSON input,
may use a small standard-library allowlist, and return a JSON-serializable
``RESULT`` value.  Network/process APIs and paths outside an ephemeral working
directory are rejected before launch and again inside the child interpreter.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import platform
import sys
import tempfile
from importlib import metadata
from pathlib import Path
from typing import Any

from pydantic import Field

from .contracts import ContractModel
from .process_supervisor import ProcessLimits, ProcessSupervisor


class SandboxPolicy(ContractModel):
    timeout_seconds: float = Field(default=10.0, gt=0, le=300)
    max_output_bytes: int = Field(default=1_000_000, ge=1024, le=20_000_000)
    max_source_bytes: int = Field(default=200_000, ge=1, le=2_000_000)
    max_input_bytes: int = Field(default=1_000_000, ge=1, le=20_000_000)
    max_memory_bytes: int = Field(default=268_435_456, ge=16_777_216, le=4_294_967_296)
    max_cpu_seconds: int = Field(default=10, ge=1, le=300)
    allowed_imports: set[str] = Field(
        default_factory=lambda: {"base64", "collections", "datetime", "hashlib", "itertools", "json", "math", "re", "statistics"}
    )
    network_enabled: bool = False
    persistent_filesystem: bool = False


class SandboxResult(ContractModel):
    status: str
    returncode: int | None = None
    output: dict[str, Any] = Field(default_factory=dict)
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float = 0.0
    timed_out: bool = False
    cancelled: bool = False
    output_truncated: bool = False
    dry_run: bool = False
    simulated: bool = False
    findings: list[str] = Field(default_factory=list)
    code_hash: str = ""
    environment_fingerprint: dict[str, Any] = Field(default_factory=dict)


def environment_fingerprint(*, packages: tuple[str, ...] = ("pydantic", "fastapi", "httpx")) -> dict[str, Any]:
    versions: dict[str, str] = {}
    for name in packages:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = "not-installed"
    executable = Path(sys.executable)
    try:
        executable_hash = hashlib.sha256(executable.read_bytes()).hexdigest()
    except OSError:
        executable_hash = hashlib.sha256(str(executable).encode()).hexdigest()
    return {
        "schema_version": "environment.v1",
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "executable_hash": executable_hash,
        "packages": versions,
    }


class GeneratedCodeSandbox:
    _FORBIDDEN_IMPORTS = {
        "asyncio", "ctypes", "ftplib", "http", "multiprocessing", "os", "pathlib",
        "shutil", "signal", "socket", "subprocess", "telnetlib", "urllib", "webbrowser",
    }
    _FORBIDDEN_CALLS = {
        "breakpoint", "compile", "eval", "exec", "exit", "getattr", "globals", "help",
        "input", "locals", "quit", "setattr", "vars", "__import__",
    }
    _FORBIDDEN_ATTRIBUTES = {
        "__bases__", "__builtins__", "__class__", "__code__", "__dict__", "__globals__",
        "__loader__", "__mro__", "__subclasses__", "__traceback__",
    }

    def __init__(self, policy: SandboxPolicy | None = None, *, supervisor: ProcessSupervisor | None = None):
        self.policy = policy or SandboxPolicy()
        self.supervisor = supervisor or ProcessSupervisor()

    def scan(self, code: str) -> list[str]:
        encoded = str(code).encode("utf-8", errors="replace")
        findings: list[str] = []
        if len(encoded) > self.policy.max_source_bytes:
            findings.append("source exceeds sandbox size limit")
            return findings
        try:
            tree = ast.parse(str(code), mode="exec")
        except SyntaxError as exc:
            return [f"syntax error at line {exc.lineno or 0}"]
        allowed = set(self.policy.allowed_imports)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [alias.name.split(".", 1)[0] for alias in node.names] if isinstance(node, ast.Import) else [str(node.module or "").split(".", 1)[0]]
                for name in names:
                    if name in self._FORBIDDEN_IMPORTS or name not in allowed:
                        findings.append(f"import is outside sandbox allowlist: {name}")
            elif isinstance(node, ast.Call):
                name = node.func.id if isinstance(node.func, ast.Name) else ""
                if name in self._FORBIDDEN_CALLS:
                    findings.append(f"call is outside sandbox contract: {name}")
                if name == "open" and node.args and isinstance(node.args[0], ast.Constant):
                    path_value = str(node.args[0].value)
                    if Path(path_value).is_absolute() or path_value.startswith(("/", "\\")) or ".." in Path(path_value).parts:
                        findings.append("path is outside sandbox root")
            elif isinstance(node, ast.Attribute) and node.attr in self._FORBIDDEN_ATTRIBUTES:
                findings.append(f"attribute is outside sandbox contract: {node.attr}")
            elif isinstance(node, ast.Name) and node.id in {"memoryview"}:
                findings.append(f"name is outside sandbox contract: {node.id}")
        if not self.policy.network_enabled:
            text = str(code).lower()
            if any(token in text for token in ("connect(", "urlopen(", "requests.", "httpx.", "socket.")):
                findings.append("network access is disabled")
        return list(dict.fromkeys(findings))

    def run(
        self,
        code: str,
        input_data: dict[str, Any] | None = None,
        *,
        dry_run: bool = False,
        simulated_result: dict[str, Any] | None = None,
    ) -> SandboxResult:
        code_text = str(code)
        code_hash = hashlib.sha256(code_text.encode()).hexdigest()
        fingerprint = environment_fingerprint()
        findings = self.scan(code_text)
        if findings:
            return SandboxResult(
                status="blocked",
                findings=findings,
                code_hash=code_hash,
                environment_fingerprint=fingerprint,
            )
        input_json = json.dumps(input_data or {}, ensure_ascii=False, sort_keys=True, default=str)
        if len(input_json.encode()) > self.policy.max_input_bytes:
            return SandboxResult(
                status="blocked",
                findings=["input exceeds sandbox size limit"],
                code_hash=code_hash,
                environment_fingerprint=fingerprint,
            )
        if dry_run or simulated_result is not None:
            return SandboxResult(
                status="simulated" if simulated_result is not None else "dry_run",
                output=dict(simulated_result or {}),
                dry_run=bool(dry_run),
                simulated=simulated_result is not None,
                code_hash=code_hash,
                environment_fingerprint=fingerprint,
            )

        with tempfile.TemporaryDirectory(prefix="sdit-sandbox-") as temporary:
            root = Path(temporary)
            source_path = root / "snippet.py"
            input_path = root / "input.json"
            runner_path = root / "runner.py"
            source_path.write_text(code_text, encoding="utf-8")
            input_path.write_text(input_json, encoding="utf-8")
            runner_path.write_text(self._runner_source(), encoding="utf-8")
            child_env = {
                "PATH": os.environ.get("PATH", ""),
                "PYTHONIOENCODING": "utf-8",
                "PYTHONHASHSEED": "0",
                "SDIT_SANDBOX_ROOT": str(root),
                "SDIT_SANDBOX_IMPORTS": ",".join(sorted(self.policy.allowed_imports)),
                "SDIT_SANDBOX_MEMORY": str(self.policy.max_memory_bytes),
                "SDIT_SANDBOX_CPU": str(self.policy.max_cpu_seconds),
            }
            process = self.supervisor.run(
                [sys.executable, "-I", "-S", str(runner_path)],
                limits=ProcessLimits(
                    timeout_seconds=self.policy.timeout_seconds,
                    max_output_bytes=self.policy.max_output_bytes,
                ),
                cwd=str(root),
                env=child_env,
                shell=False,
            )
            marker = "__SDIT_SANDBOX_RESULT__="
            output: dict[str, Any] = {}
            visible_stdout: list[str] = []
            for line in process.stdout.splitlines():
                if line.startswith(marker):
                    try:
                        parsed = json.loads(line[len(marker):])
                        output = parsed if isinstance(parsed, dict) else {"result": parsed}
                    except json.JSONDecodeError:
                        output = {}
                else:
                    visible_stdout.append(line)
            status = "completed" if process.returncode == 0 and not process.timed_out and not process.cancelled else "failed"
            if process.timed_out:
                status = "timeout"
            elif process.cancelled:
                status = "cancelled"
            return SandboxResult(
                status=status,
                returncode=process.returncode,
                output=output,
                stdout="\n".join(visible_stdout),
                stderr=process.stderr,
                duration_seconds=process.duration_seconds,
                timed_out=process.timed_out,
                cancelled=process.cancelled,
                output_truncated=process.output_truncated,
                code_hash=code_hash,
                environment_fingerprint=fingerprint,
            )

    @staticmethod
    def _runner_source() -> str:
        return r'''
import builtins
import json
import os
import sys
from pathlib import Path

ROOT = Path(os.environ["SDIT_SANDBOX_ROOT"]).resolve()
ALLOWED_IMPORTS = set(filter(None, os.environ.get("SDIT_SANDBOX_IMPORTS", "").split(",")))

try:
    import resource
    memory = int(os.environ.get("SDIT_SANDBOX_MEMORY", "0"))
    cpu = int(os.environ.get("SDIT_SANDBOX_CPU", "0"))
    if memory > 0:
        resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
    if cpu > 0:
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
except (ImportError, OSError, ValueError):
    pass

def safe_open(path, mode="r", *args, **kwargs):
    candidate = (ROOT / str(path)).resolve() if not Path(str(path)).is_absolute() else Path(str(path)).resolve()
    if candidate != ROOT and ROOT not in candidate.parents:
        raise PermissionError("path outside sandbox root")
    return builtins.open(candidate, mode, *args, **kwargs)

def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    top = str(name).split(".", 1)[0]
    if top not in ALLOWED_IMPORTS:
        raise ImportError("module outside sandbox allowlist")
    return builtins.__import__(name, globals, locals, fromlist, level)

SAFE_NAMES = (
    "abs", "all", "any", "bool", "bytes", "dict", "enumerate", "filter", "float",
    "format", "frozenset", "int", "isinstance", "issubclass", "len", "list", "map",
    "max", "min", "next", "print", "range", "repr", "reversed", "round", "set",
    "slice", "sorted", "str", "sum", "tuple", "zip", "Exception", "ValueError",
    "TypeError", "RuntimeError"
)
safe_builtins = {name: getattr(builtins, name) for name in SAFE_NAMES}
safe_builtins["open"] = safe_open
safe_builtins["__import__"] = safe_import

code = (ROOT / "snippet.py").read_text(encoding="utf-8")
input_data = json.loads((ROOT / "input.json").read_text(encoding="utf-8"))
namespace = {"__builtins__": safe_builtins, "INPUT": input_data, "RESULT": {}}
try:
    exec(compile(code, "snippet.py", "exec"), namespace, namespace)
    result = namespace.get("RESULT", {})
    print("__SDIT_SANDBOX_RESULT__=" + json.dumps(result, ensure_ascii=False, default=str))
except Exception as exc:
    print(type(exc).__name__ + ": " + str(exc), file=sys.stderr)
    raise SystemExit(2)
'''.strip()


__all__ = ["SandboxPolicy", "SandboxResult", "GeneratedCodeSandbox", "environment_fingerprint"]
