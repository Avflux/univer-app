"""Conversão de arquivos .docx em .pdf no ambiente Windows/local."""

from __future__ import annotations

import os
from pathlib import Path


def convert_docx_to_pdf(docx_path: str | Path, pdf_path: str | Path) -> None:
    """Converte um arquivo .docx para .pdf usando o Microsoft Word nativo via COM.

    Args:
        docx_path: Caminho do arquivo .docx de entrada.
        pdf_path: Caminho onde o arquivo .pdf será salvo.

    Raises:
        FileNotFoundError: Se docx_path não existir.
        RuntimeError: Se a conversão falhar.
    """
    docx_path = Path(docx_path).resolve()
    pdf_path = Path(pdf_path).resolve()

    if not docx_path.exists():
        raise FileNotFoundError(f"Arquivo .docx não encontrado: {docx_path}")

    # Garante que o diretório de destino existe
    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        import pythoncom
        import win32com.client
    except ImportError as exc:
        raise RuntimeError(
            "pywin32 não está instalado. Instale com: pip install pywin32"
        ) from exc

    pythoncom.CoInitialize()
    word = None
    try:
        word = win32com.client.Dispatch("Word.Application")
        word.Visible = False
        doc = word.Documents.Open(str(docx_path))
        try:
            # 17 = wdFormatPDF
            doc.SaveAs(str(pdf_path), FileFormat=17)
        finally:
            doc.Close(False)
    except Exception as exc:
        raise RuntimeError(f"Falha ao converter docx para pdf via Word: {exc}") from exc
    finally:
        if word is not None:
            try:
                word.Quit()
            except Exception:
                pass
        pythoncom.CoUninitialize()

    if not pdf_path.exists():
        raise RuntimeError(f"O PDF não foi gerado em: {pdf_path}")
