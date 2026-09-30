"""Resolução do caminho de saída das exportações (planilhas/DWG).

Centraliza a lógica de "descobrir onde salvar" que estava duplicada nas
funções de exportação do sidecar:

- caminho explícito escolhido pelo usuário ("Salvar como") → usa o
  diretório do arquivo e garante a extensão;
- sem caminho explícito → ``last_directory`` registrado no config.json
  (``update_last_directory``); se ausente, cai para ``fallback_dir``
  (ex.: diretório do desenho aberto no CAD) ou ``~/nexus_exports``;
- sanitiza o nome do arquivo (caracteres inválidos do Windows) e cria o
  diretório com ``mkdir(parents=True, exist_ok=True)``.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from backend.core.config import get_last_directory

# Caracteres inválidos em nomes de arquivo do Windows (e controle 0x00-0x1f).
_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

_DEFAULT_EXPORT_DIR = Path.home() / "nexus_exports"


def sanitize_filename(name: str) -> str:
    """Remove caracteres inválidos para nomes de arquivo do Windows."""
    safe = _INVALID_FILENAME_CHARS.sub("_", name).strip().rstrip(".")
    return safe or "arquivo"


def resolve_output_path(
    filename_stem: str,
    suffix: str = ".xlsx",
    output_path: str | os.PathLike | None = None,
    fallback_dir: str | os.PathLike | None = None,
) -> Path:
    """Resolve o caminho final de um arquivo exportado.

    Args:
        filename_stem: Nome do arquivo sem extensão (sanitizado internamente).
            Usado apenas quando ``output_path`` é ``None``.
        suffix: Extensão esperada (ex.: ``".xlsx"``, ``".dwg"``). Se o
            ``output_path`` explícito tiver outra extensão, é trocada.
        output_path: Caminho completo escolhido pelo usuário (diálogo
            "Salvar como"), ou ``None`` para usar o ``last_directory``.
        fallback_dir: Diretório usado quando não há ``output_path`` nem
            ``last_directory`` registrado (ex.: diretório do desenho no CAD).
            Padrão: ``~/nexus_exports``.

    Returns:
        Caminho final (com diretório já criado via ``mkdir(parents=True)``).
    """
    if output_path:
        path = Path(output_path)
        if path.suffix.lower() != suffix:
            path = path.with_suffix(suffix)
        output_dir = path.parent
    else:
        last_dir = get_last_directory()
        if last_dir:
            output_dir = Path(last_dir)
        else:
            output_dir = Path(fallback_dir) if fallback_dir else _DEFAULT_EXPORT_DIR
        path = output_dir / (sanitize_filename(filename_stem) + suffix)
    output_dir.mkdir(parents=True, exist_ok=True)
    return path


def pick_open_path(
    title: str = "Abrir projeto Univer",
    initial_dir: str | os.PathLike | None = None,
    filetypes: list[tuple[str, str]] | None = None,
) -> str:
    """Abre o diálogo nativo "Abrir arquivo" e devolve o caminho escolhido.

    O backend roda na máquina do usuário, então o diálogo do sistema é a
    forma de escolher o arquivo sem digitar o caminho. Usa o
    ``initial_dir`` informado (ou o ``last_directory`` registrado) como pasta
    inicial.

    Returns:
        Caminho absoluto escolhido, ou ``""`` quando o usuário cancela.

    Raises:
        RuntimeError: quando o Tkinter (diálogo nativo) não está disponível ou
            o ambiente não permite abrir a janela.
    """
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as exc:  # pragma: no cover - depende do Python instalado
        raise RuntimeError(
            "O diálogo de arquivo não está disponível: o Tkinter não pôde ser "
            "importado neste Python. Reinstale-o com suporte a Tk."
        ) from exc

    start_dir = str(initial_dir) if initial_dir else (get_last_directory() or None)

    try:
        root = tk.Tk()
    except Exception as exc:  # pragma: no cover - ambiente sem display
        raise RuntimeError(
            "Não foi possível abrir o diálogo de arquivo neste ambiente."
        ) from exc

    root.withdraw()
    try:
        # Mantém o diálogo à frente da janela do navegador.
        root.attributes("-topmost", True)
    except Exception:  # pragma: no cover - alguns gerenciadores ignoram
        pass

    try:
        selected = filedialog.askopenfilename(
            title=title,
            initialdir=start_dir,
            filetypes=filetypes
            or [
                ("Projeto Univer", "*.md"),
                ("Todos os arquivos", "*.*"),
            ],
        )
    finally:
        root.destroy()

    return str(selected or "")
