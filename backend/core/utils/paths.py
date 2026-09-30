"""Resolução de caminhos do Univer (compatível com PyInstaller).

Espelha o padrão do Seer (``anafas_seer/core/db.py``), que separa dois
espaços de arquivos:

- **Recursos embutidos** (read-only): em modo frozen ficam em
  ``sys._MEIPASS`` — a pasta temporária onde o ``--onefile`` extrai o bundle
  (ex.: ``...\\Temp\\_MEI000062c82``). Em desenvolvimento, são resolvidos a
  partir da raiz do ``backend/`` no disco.
- **Dados do usuário** (gravável e persistente):
  ``%LOCALAPPDATA%\\NEXUS`` — mesma pasta já usada por ``config.py``,
  ``env_loader.py`` e ``sidecar/state.py``.
"""

from __future__ import annotations

import os
import sys

# Nome da pasta raiz dentro do bundle (modo frozen).
_BUNDLE_ROOT_NAME = "backend"

# Permite apontar os dados do usuário para outro diretório (testes,
# instalação portátil).
_DATA_DIR_ENV_VAR = "UNIVER_DATA_DIR"


def is_frozen() -> bool:
    """Indica se o código está rodando dentro de um executável PyInstaller."""
    return bool(getattr(sys, "frozen", False))


def get_backend_root() -> str:
    """Retorna a raiz do backend (onde fica ``Modules/``).

    Em modo frozen: ``<_MEIPASS>/backend``.
    Em desenvolvimento: a pasta ``backend/`` deste arquivo (utils/ -> core/
    -> backend/).
    """
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return os.path.join(meipass, _BUNDLE_ROOT_NAME)
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_sheets_dir() -> str:
    """Retorna a pasta ``Modules/Sheets`` (templates Excel e banco semente)."""
    return os.path.join(get_backend_root(), "Modules", "Sheets")


def get_docs_dir() -> str:
    """Retorna a pasta ``Modules/docs`` (modelos .docx de relatório)."""
    return os.path.join(get_backend_root(), "Modules", "docs")


def get_user_data_dir() -> str:
    """Retorna o diretório gravável do Univer (``%LOCALAPPDATA%\\NEXUS``).

    Não cria o diretório — quem escreve deve usar ``os.makedirs``.
    """
    # Compat: ``UNIVER_DATA_DIR`` é o nome atual (aplicação Univer);
    # ``NEXUS_DATA_DIR`` é o nome antigo, mantido para não ignorar
    # instalações que já o utilizam.
    override = os.environ.get(_DATA_DIR_ENV_VAR) or os.environ.get("NEXUS_DATA_DIR")
    if override:
        return override
    base = os.environ.get("LOCALAPPDATA") or os.path.join(
        os.path.expanduser("~"), "AppData", "Local"
    )
    return os.path.join(base, "NEXUS")




