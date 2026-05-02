from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class CommandResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def run_command(command: list[str], timeout_sec: int = 30) -> CommandResult:
    process = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_sec,
        check=False,
    )
    return CommandResult(command=command, returncode=process.returncode, stdout=process.stdout, stderr=process.stderr)


def check_nvidia_smi() -> CommandResult:
    return run_command(["nvidia-smi"])
