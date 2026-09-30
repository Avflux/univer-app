"""Abertura de um arquivo gerado no aplicativo padrão do sistema.

O backend roda na máquina do usuário, então "abrir" o arquivo exportado é só
delegar ao shell do SO — é o que a exportação faz logo depois de gravar, para
o relatório ``.docx`` já aparecer no Word e a planilha no Excel.

- Windows → ``os.startfile``;
- macOS   → ``open``;
- demais  → ``xdg-open``.

A abertura não espera o aplicativo fechar (o comando só dispara o programa), e
um ambiente sem abridor disponível levanta ``RuntimeError`` — quem chama decide
se isso invalida a operação (normalmente não: o arquivo já está no disco).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def open_path(path: str | os.PathLike) -> None:
    """Abre ``path`` no aplicativo padrão do sistema.

    Args:
        path: Caminho do arquivo a abrir (string ou ``Path``).

    Raises:
        FileNotFoundError: quando o arquivo não existe.
        RuntimeError: quando o SO não tem um abridor disponível ou o comando
            não pôde ser iniciado.
    """
    target = Path(path)
    if not target.is_file():
        raise FileNotFoundError(f"Arquivo não encontrado: {target}")

    if sys.platform == "win32":
        # ``os.startfile`` só existe no Windows (o typeshed não o expõe em posix).
        opener = getattr(os, "startfile", None)
        if opener is None:  # pragma: no cover - Windows sempre tem
            raise RuntimeError("os.startfile não está disponível neste Python.")
        opener(str(target))
        return

    command = "open" if sys.platform == "darwin" else "xdg-open"
    try:
        subprocess.Popen(
            [command, str(target)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:  # pragma: no cover - depende do ambiente
        raise RuntimeError(
            f"Não foi possível abrir {target.name}: comando '{command}' indisponível."
        ) from exc
