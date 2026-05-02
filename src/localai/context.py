from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AppContext:
    project_root: Path
    config: dict[str, Any]
    entry_name: str

    @property
    def app_config(self) -> dict[str, Any]:
        return self.config.get("app", {})

    @property
    def output_dir(self) -> Path:
        value = self.app_config.get("output_dir", "./output/")
        return self.resolve_path(value)

    @property
    def log_dir(self) -> Path:
        return self.project_root / "log"

    def resolve_path(self, value: str | Path) -> Path:
        path = Path(value)
        if path.is_absolute():
            return path
        return self.project_root / path

    def flow_config(self, name: str) -> dict[str, Any]:
        flows = self.config.get("flows", {})
        return flows.get(name, {})
