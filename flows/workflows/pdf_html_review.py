from __future__ import annotations

from pathlib import Path
from typing import Any

from flows.context import AppContext
from flows.modules.pdf_table_html import export_pdf_tables


def run(
    ctx: AppContext,
    input_root: str | Path,
    output_dir: str | Path,
    *,
    force: bool = False,
) -> dict[str, Any]:
    return export_pdf_tables(
        project_root=ctx.project_root,
        input_root=ctx.resolve_path(input_root),
        output_dir=ctx.resolve_path(output_dir),
        force=force,
    )
