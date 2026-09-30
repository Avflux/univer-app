"""Utilitários para persistir arquivos sem corromper o arquivo existente."""

import json
import os
from pathlib import Path
import tempfile
from typing import Any


def atomic_write_json(path: str | os.PathLike[str], payload: Any) -> None:
    """Serializa ``payload`` como JSON em ``path`` via substituição atômica."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_path = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(payload, file, indent=2, ensure_ascii=False)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, target)
    except Exception:
        try:
            os.unlink(temporary_path)
        except FileNotFoundError:
            pass
        raise
