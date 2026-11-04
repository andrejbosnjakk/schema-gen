"""The whole model as JSON (lossless; `source: {path: model.json}` reads it back)."""
from __future__ import annotations

import json
from pathlib import Path

from ..core.model import Model


def dumps(m: Model) -> str:
    return json.dumps(m.model_dump(mode="json", by_alias=True), ensure_ascii=False, indent=1)


def export(m: Model, path: Path) -> None:
    Path(path).write_text(dumps(m) + "\n", encoding="utf-8")
