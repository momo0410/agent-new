#!/usr/bin/env python3
"""Linux one-click launcher for the frontend and Python backend."""

from __future__ import annotations

import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT / "src-python"
VENV_DIR = ROOT / ".venv"
VENV_PYTHON = VENV_DIR / "bin" / "python"
VENV_PIP = VENV_DIR / "bin" / "pip"
BACKEND_PORT = 3001
FRONTEND_PORT = 1420
FRONTEND_START_RETRIES = 1


def log(message: str) -> None:
    print(f"[start_linux] {message}", flush=True)


def fail(message: str, exit_code: int = 1) -> None:
    log(f"ERROR: {message}")
    raise SystemExit(exit_code)


def run(
    command: list[str],
    *,
    cwd: Path = ROOT,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    log(f"Running: {' '.join(command)}")
    return subprocess.run(
        command,
        cwd=str(cwd),
        env=env,
        text=True,
        check=check,
    )


def command_exists(command: str) -> bool:
    return shutil.which(command) is not None


def read_version(command: list[str]) -> str:
    completed = subprocess.run(command, capture_output=True, text=True, check=True)
    output = (completed.stdout or completed.stderr).strip()
    return output.splitlines()[0] if output else "unknown"


def ensure_linux() -> None:
    if sys.platform != "linux":
        fail(f"This script only supports Linux, current platform: {sys.platform}")


def ensure_commands() -> None:
    missing = [name for name in ("python3", "node", "npm") if not command_exists(name)]
    if missing:
        fail(
            "Missing required commands: "
            + ", ".join(missing)
            + ". Please install them first."
        )

    log(f"Python: {read_version(['python3', '--version'])}")
    log(f"Node: {read_version(['node', '--version'])}")
    log(f"NPM: {read_version(['npm', '--version'])}")


def ensure_python_version() -> None:
    if sys.version_info < (3, 10):
        fail("Python 3.10+ is required to run this project.")


def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def find_port_pids(port: int) -> list[int]:
    if not command_exists("lsof"):
        fail("`lsof` is required to detect and kill processes occupying ports.")

    completed = subprocess.run(
        ["lsof", "-ti", f"tcp:{port}"],
        capture_output=True,
        text=True,
        check=False,
    )
    pids: list[int] = []
    for line in completed.stdout.splitlines():
        line = line.strip()
        if line.isdigit():
            pids.append(int(line))
    return sorted(set(pids))


def kill_processes_on_port(port: int) -> None:
    pids = find_port_pids(port)
    if not pids:
        return

    log(f"Port {port} is occupied by PIDs: {', '.join(str(pid) for pid in pids)}")
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            continue

    deadline = time.time() + 8
    while time.time() < deadline:
        remaining = find_port_pids(port)
        if not remaining:
            log(f"Released port {port}.")
            return
        time.sleep(0.2)

    remaining = find_port_pids(port)
    if remaining:
        log(f"Force killing remaining PIDs on port {port}: {', '.join(str(pid) for pid in remaining)}")
        for pid in remaining:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                continue
        time.sleep(0.5)

    if is_port_in_use(port):
        fail(f"Failed to release occupied port {port}.")


def release_ports() -> None:
    for port in (BACKEND_PORT, FRONTEND_PORT):
        kill_processes_on_port(port)


def recreate_venv() -> None:
    if VENV_DIR.exists():
        log(f"Removing broken virtualenv: {VENV_DIR}")
        shutil.rmtree(VENV_DIR)

    run(["python3", "-m", "venv", str(VENV_DIR)])
    run([str(VENV_PIP), "install", "--upgrade", "pip", "setuptools", "wheel"])
    run([str(VENV_PIP), "install", "-r", "requirements.txt"], cwd=BACKEND_DIR)


def python_env_is_healthy() -> bool:
    if not VENV_PYTHON.exists() or not VENV_PIP.exists():
        return False

    try:
        run([str(VENV_PYTHON), "-c", "import fastapi, uvicorn, websockets"], check=True)
    except subprocess.CalledProcessError:
        return False

    return True


def ensure_python_env() -> None:
    if python_env_is_healthy():
        log("Python virtualenv looks healthy.")
        return

    log("Python environment is missing or unhealthy. Reinstalling...")
    recreate_venv()


def npm_install() -> None:
    lockfile = ROOT / "package-lock.json"
    if lockfile.exists():
        run(["npm", "ci"], cwd=ROOT)
    else:
        run(["npm", "install"], cwd=ROOT)


def reinstall_frontend_env() -> None:
    node_modules = ROOT / "node_modules"
    lockfile = ROOT / "package-lock.json"

    if node_modules.exists():
        log(f"Removing frontend dependencies directory: {node_modules}")
        shutil.rmtree(node_modules)
    if lockfile.exists():
        log(f"Removing lockfile for clean reinstall: {lockfile}")
        lockfile.unlink()

    run(["npm", "install"], cwd=ROOT)


def frontend_env_is_healthy() -> bool:
    node_modules = ROOT / "node_modules"
    vite_bin = node_modules / ".bin" / ("vite.cmd" if os.name == "nt" else "vite")
    if not node_modules.exists() or not vite_bin.exists():
        return False

    try:
        run(["npm", "ls", "--depth=0"], cwd=ROOT, check=True)
    except subprocess.CalledProcessError:
        return False

    return True


def ensure_frontend_env() -> None:
    if frontend_env_is_healthy():
        log("Frontend dependencies look healthy.")
        return

    log("Frontend environment is missing or unhealthy. Reinstalling...")
    npm_install()


def wait_for_port(port: int, process: subprocess.Popen[str], service_name: str) -> None:
    deadline = time.time() + 45
    while time.time() < deadline:
        if process.poll() is not None:
            fail(f"{service_name} exited early with code {process.returncode}.")
        if is_port_in_use(port):
            log(f"{service_name} is ready on port {port}.")
            return
        time.sleep(0.5)
    fail(f"{service_name} did not become ready on port {port} in time.")


def build_backend_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PY_BACKEND_RELOAD"] = env.get("PY_BACKEND_RELOAD", "1")
    env["VIRTUAL_ENV"] = str(VENV_DIR)
    env["PATH"] = f"{VENV_DIR / 'bin'}:{env.get('PATH', '')}"
    return env


def spawn_backend() -> subprocess.Popen[str]:
    backend_env = build_backend_env()
    return subprocess.Popen(
        [str(VENV_PYTHON), "run.py"],
        cwd=str(BACKEND_DIR),
        env=backend_env,
        text=True,
    )


def spawn_frontend() -> subprocess.Popen[str]:
    return subprocess.Popen(
        ["npm", "run", "dev", "--", "--host", "0.0.0.0"],
        cwd=str(ROOT),
        env=os.environ.copy(),
        text=True,
    )


def start_processes() -> list[subprocess.Popen[str]]:
    backend = spawn_backend()
    try:
        wait_for_port(BACKEND_PORT, backend, "Backend")

        frontend: subprocess.Popen[str] | None = None
        for attempt in range(FRONTEND_START_RETRIES + 1):
            frontend = spawn_frontend()
            deadline = time.time() + 45
            while time.time() < deadline:
                if frontend.poll() is not None:
                    log(f"Frontend exited early with code {frontend.returncode}.")
                    if attempt < FRONTEND_START_RETRIES:
                        log("Frontend start failed. Reinstalling frontend dependencies and retrying...")
                        reinstall_frontend_env()
                        break
                    fail(f"Frontend exited early with code {frontend.returncode}.")
                if is_port_in_use(FRONTEND_PORT):
                    log(f"Frontend is ready on port {FRONTEND_PORT}.")
                    log("Frontend: http://127.0.0.1:1420")
                    log("Backend:  http://127.0.0.1:3001")
                    log("Press Ctrl+C to stop both services.")
                    return [backend, frontend]
                time.sleep(0.5)
            else:
                if attempt < FRONTEND_START_RETRIES:
                    log("Frontend did not become ready in time. Reinstalling frontend dependencies and retrying...")
                    terminate_processes([frontend])
                    reinstall_frontend_env()
                    continue
                fail(f"Frontend did not become ready on port {FRONTEND_PORT} in time.")

        fail("Frontend failed to start for an unknown reason.")
    except BaseException:
        terminate_processes([backend])
        raise


def terminate_processes(processes: Iterable[subprocess.Popen[str]]) -> None:
    alive = [process for process in processes if process.poll() is None]
    if not alive:
        return

    log("Stopping child processes...")
    for process in alive:
        process.terminate()

    deadline = time.time() + 10
    while time.time() < deadline:
        remaining = [process for process in alive if process.poll() is None]
        if not remaining:
            return
        time.sleep(0.2)

    for process in alive:
        if process.poll() is None:
            process.kill()


def wait_forever(processes: list[subprocess.Popen[str]]) -> int:
    try:
        while True:
            for process in processes:
                exit_code = process.poll()
                if exit_code is not None:
                    log(f"A child process exited with code {exit_code}.")
                    return exit_code
            time.sleep(1)
    except KeyboardInterrupt:
        log("Received Ctrl+C.")
        return 0
    finally:
        terminate_processes(processes)


def _handle_signal(_signum: int, _frame: object) -> None:
    raise KeyboardInterrupt


def main() -> int:
    ensure_linux()
    ensure_python_version()
    ensure_commands()
    release_ports()
    ensure_python_env()
    ensure_frontend_env()

    signal.signal(signal.SIGTERM, _handle_signal)
    processes = start_processes()
    return wait_forever(processes)


if __name__ == "__main__":
    raise SystemExit(main())
