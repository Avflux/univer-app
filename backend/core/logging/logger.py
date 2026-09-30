"""Sistema de logging configurável do Univer.

Lê a seção ``logging`` do config.json e configura o logger raiz com
saída para console e arquivo rotativo.
"""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path
from threading import Lock
from typing import Optional

from backend.core import config as _config

_lock = Lock()
_configured = False

DEFAULT_CONFIG = {
    "level": "INFO",
    "log_dir": "logs",
    "log_file": "univer.log",
    "max_bytes": 1_048_576,
    "backup_count": 5,
    "console": True,
    "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    "datefmt": "%Y-%m-%d %H:%M:%S",
}

_LEVELS = {
    "CRITICAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
    "NOTSET": logging.NOTSET,
}


def _resolve_log_cfg() -> dict:
    """Lê config.json e devolve dict com defaults aplicados."""
    cfg = dict(DEFAULT_CONFIG)
    try:
        user_cfg = _config.get_config().get("logging") or {}
        if isinstance(user_cfg, dict):
            cfg.update(user_cfg)
    except Exception:
        # Se config.json indisponível, mantém defaults
        pass
    return cfg


def configure_logging(force: bool = False) -> logging.Logger:
    """Configura o logger raiz. Idempotente salvo ``force=True``.

    Returns:
        Logger raiz configurado.
    """
    global _configured
    with _lock:
        if _configured and not force:
            return logging.getLogger("univer")

        cfg = _resolve_log_cfg()

        root = logging.getLogger("univer")
        root.setLevel(_LEVELS.get(str(cfg["level"]).upper(), logging.INFO))

        # Limpa handlers de execuções anteriores (importante em testes).
        for h in list(root.handlers):
            root.removeHandler(h)

        formatter = logging.Formatter(
            fmt=cfg["format"],
            datefmt=cfg.get("datefmt"),
        )

        # Handler de console
        if cfg.get("console", True):
            stream = logging.StreamHandler()
            stream.setFormatter(formatter)
            root.addHandler(stream)

        # Handler de arquivo rotativo
        log_dir = Path(cfg["log_dir"])
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            log_path = log_dir / cfg["log_file"]
            file_handler = logging.handlers.RotatingFileHandler(
                filename=str(log_path),
                maxBytes=int(cfg["max_bytes"]),
                backupCount=int(cfg["backup_count"]),
                encoding="utf-8",
            )
            file_handler.setFormatter(formatter)
            root.addHandler(file_handler)
        except (OSError, ValueError) as exc:
            # Sem permissão para gravar no diretório → cai só para console.
            stream = logging.StreamHandler()
            stream.setFormatter(formatter)
            root.addHandler(stream)
            logging.getLogger("univer").warning(
                "Não foi possível criar arquivo de log em %s: %s. "
                "Logs serão enviados apenas ao console.",
                log_dir, exc,
            )

        # Evita duplicação nos handlers do root do Python.
        root.propagate = False

        _configured = True

        console_note = ", console ativo" if cfg.get("console", True) else ""
        root.info(
            "Logs configurados: nível=%s%s, arquivo=%s",
            cfg["level"],
            console_note,
            log_dir / cfg["log_file"],
        )

        return root


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Retorna um logger filho do logger raiz do Univer (use ``__name__``)."""
    configure_logging()
    if name and not name.startswith("univer."):
        return logging.getLogger(f"univer.{name}")
    return logging.getLogger(name or "univer")


def reset_logging() -> None:
    """Reseta o estado de configuração (útil em testes)."""
    global _configured
    with _lock:
        root = logging.getLogger("univer")
        for h in list(root.handlers):
            root.removeHandler(h)
            try:
                h.close()
            except Exception:
                pass
        _configured = False