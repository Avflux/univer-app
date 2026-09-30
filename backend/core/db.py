"""Banco de costura (``nexus_costura.db``): localização e semente.

O banco é dado de referência derivado das planilhas Excel de
``Modules/Sheets``. Ele vive em ``%LOCALAPPDATA%\\NEXUS`` — gravável e
persistente — e é semeado a partir da cópia embutida no bundle na primeira
execução (:func:`ensure_database`, chamado no startup da API).

Nunca leia o banco direto da pasta de templates: use :func:`get_db_path`.
"""

from __future__ import annotations

import os
import shutil

from backend.core.logging.logger import get_logger
from backend.core.utils.paths import get_sheets_dir, get_user_data_dir

log = get_logger(__name__)

DB_FILENAME = "nexus_costura.db"

# Sufixos dos arquivos auxiliares do SQLite (journal/WAL).
_SIDECAR_SUFFIXES = ("-wal", "-shm", "-journal")


def get_db_path() -> str:
    """Caminho do banco de costura no diretório gravável do usuário."""
    return os.path.join(get_user_data_dir(), DB_FILENAME)


def get_seed_db_path() -> str:
    """Caminho do banco embutido no bundle (semente versionada no git)."""
    return os.path.join(get_sheets_dir(), DB_FILENAME)


def _remove_sidecars(db_path: str) -> None:
    """Remove ``-wal``/``-shm``/``-journal`` do banco.

    O banco do usuário fica em modo WAL depois das leituras (ver
    ``db_cable_fetcher``); ao substituir o arquivo principal, os auxiliares do
    arquivo antigo precisam sair para não "sombrearem" o novo.
    """
    for suffix in _SIDECAR_SUFFIXES:
        aux = db_path + suffix
        if os.path.exists(aux):
            try:
                os.remove(aux)
            except OSError:
                pass


def _copy_seed_to(db_path: str) -> bool:
    """Copia a semente do bundle para ``db_path`` (cópia atômica).

    Retorna ``False`` se a semente não existir no bundle.
    """
    seed_path = get_seed_db_path()
    if not os.path.isfile(seed_path):
        log.warning("Banco semente não encontrado no bundle: %s", seed_path)
        return False

    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    # Cópia atômica: nunca deixa um banco truncado se a cópia falhar.
    tmp_path = f"{db_path}.tmp"
    shutil.copyfile(seed_path, tmp_path)
    _remove_sidecars(db_path)
    os.replace(tmp_path, db_path)
    return True


def ensure_database() -> str:
    """Garante o banco do usuário, copiando a semente do bundle se preciso.

    Não roda migrações. Retorna o caminho do banco — que pode não existir se
    não houver nem banco do usuário nem semente no bundle.
    """
    db_path = get_db_path()
    if os.path.isfile(db_path):
        return db_path

    if _copy_seed_to(db_path):
        log.info("Banco de costura semeado do bundle em: %s", db_path)
    return db_path

