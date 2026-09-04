"""Small, argument-based Docker Compose operations for the operator TUI.

The screen is an operator convenience, not a second deployment system. It
only runs the existing Compose file through ``docker compose`` and never uses
``shell=True``. Volume removal and arbitrary container deletion are absent on
purpose: those are recovery decisions, not routine status controls.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from pipeline.config import REPO_ROOT


class DockerControlError(RuntimeError):
    """Docker or Compose could not complete the requested operation."""


READ_ONLY_ACTIONS = frozenset({"status", "logs"})
ACTION_LABELS = {
    "status": "Inspect stack status",
    "up": "Start stack",
    "stop": "Stop stack",
    "restart": "Restart stack",
    "logs": "View recent logs",
}


def default_compose_files(root: Path = REPO_ROOT) -> list[Path]:
    """Return concrete local Compose files, in a stable operator order."""
    deploy = Path(root) / "deploy"
    files = list(deploy.glob("docker-compose*.yml"))
    return sorted(files, key=lambda path: (path.name != "docker-compose.postgres.yml", path.name))


def _validated_file(compose_file: Path) -> Path:
    path = Path(compose_file).expanduser().resolve()
    if not path.is_file():
        raise DockerControlError(f"Compose file does not exist: {path}")
    if path.suffix.lower() not in {".yml", ".yaml"}:
        raise DockerControlError(f"Compose file must be YAML: {path}")
    return path


def _docker_executable() -> str:
    executable = shutil.which("docker")
    if not executable:
        raise DockerControlError(
            "Docker is not on PATH. Start Docker Desktop or install the Docker CLI.")
    return executable


def run_compose(compose_file: Path, arguments: list[str], *, timeout: float = 180) -> str:
    """Run one Compose command and return its combined, human-readable output."""
    command = [_docker_executable(), "compose", "-f", str(_validated_file(compose_file)), *arguments]
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        result = subprocess.run(
            command,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            creationflags=creationflags,
        )
    except subprocess.TimeoutExpired as exc:
        raise DockerControlError(
            f"Docker Compose timed out after {timeout:g} seconds: {' '.join(command)}") from exc
    except OSError as exc:
        raise DockerControlError(f"could not start Docker Compose: {exc}") from exc

    output = (result.stdout or "") + (result.stderr or "")
    if result.returncode:
        detail = output.strip() or "no output"
        raise DockerControlError(
            f"Docker Compose exited with code {result.returncode}: {detail}")
    return output.strip() or "Compose completed without output."


def execute(action: str, compose_file: Path, *, service: str | None = None,
            tail: int = 80) -> str:
    """Execute one allowlisted operator action against a Compose stack."""
    if action not in ACTION_LABELS:
        raise DockerControlError(f"unknown Docker action: {action}")
    service_name = (service or "").strip()
    if action == "status":
        arguments = ["ps", "--all"]
    elif action == "up":
        arguments = ["up", "-d"]
    elif action == "stop":
        arguments = ["stop"]
    elif action == "restart":
        arguments = ["restart"]
    else:
        arguments = ["logs", "--tail", str(max(1, tail)), "--no-color"]
    if service_name:
        arguments.append(service_name)
    return run_compose(compose_file, arguments)
