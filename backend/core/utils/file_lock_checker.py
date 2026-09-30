"""Verificador de bloqueio de arquivo.

No Windows, quando um arquivo .xlsx está aberto pelo Excel (ou outro
programa), o SO aplica um bloqueio exclusivo de escrita. Tentar abrir
o arquivo com ``open(path, 'r+b')`` lança ``PermissionError`` — o que
é usado aqui como sinal confiável de que o arquivo está em uso.

Casos:
- Arquivo existe e está bloqueado → ``PermissionError`` → retorna True.
- Arquivo existe e não está bloqueado → abre com sucesso → retorna False.
- Arquivo não existe (novo) → ``FileNotFoundError`` → retorna False.
"""

from __future__ import annotations

import os


def is_file_locked(path: str | os.PathLike) -> bool:
    """Retorna ``True`` se o arquivo existir **e** estiver bloqueado.

    Usa uma tentativa de abertura em modo ``'r+b'`` (leitura/escrita
    binária sem truncar) para detectar o bloqueio exclusivo do Windows.
    Não altera o conteúdo do arquivo em caso de sucesso.

    Args:
        path: Caminho do arquivo a verificar (string ou ``Path``).

    Returns:
        ``True``  → arquivo existe e está bloqueado por outro processo.
        ``False`` → arquivo não existe (novo) ou não está bloqueado.
    """
    try:
        with open(path, "r+b"):
            return False
    except PermissionError:
        return True
    except (FileNotFoundError, OSError):
        # FileNotFoundError: arquivo novo — sem problema.
        # OSError genérico: trata como "não bloqueado" para não bloquear
        # a exportação por razões inesperadas.
        return False
