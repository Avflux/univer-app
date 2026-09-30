"""Gerenciamento de estado do sidecar Univer.

Mantém em memória o estado ativo do projeto (bays, dados, cache)
e fornece persistência via JSON.  Sem dependência de interface
gráfica.
"""

from __future__ import annotations

import copy
import json
import os
import threading
from datetime import datetime, timezone
from typing import Any

from backend.core.bay.project_serializer import normalize_project_data
from backend.core.logging.logger import get_logger
from backend.core.utils.atomic_io import atomic_write_json

log = get_logger(__name__)

# Diretório onde os projetos .md são salvos (fallback: cwd)
_PROJECTS_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
    "AppData", "Local", "NEXUS", "projects",
)


class UniverState:
    """Estado ativo do sidecar — singleton por processo.

    Attributes:
        project_path: Caminho do arquivo .md aberto (ou None).
        project_data: Dict completo do projeto (version, bays, …).
        bay_cache: Cache de dados processados por bay_id.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.project_path: str | None = None
        self.project_data: dict[str, Any] = {
            "version": "2.0",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_modified": None,
            "point_aliases_default": {},
            "bays": {},
        }
        # Cache de dados processados {bay_id: {…}}
        self.bay_cache: dict[str, dict[str, Any]] = {}
        # (mtime, size) da última escrita — referência para detectar mudanças
        # externas ao reabrir o projeto.
        self.last_known_mtime: tuple[float, int] | None = None

    # ---- Projeto ----

    def new_project(self, name: str = "Projeto Univer") -> dict:
        """Cria um projeto vazio em memória."""
        with self._lock:
            self.project_path = None
            self.project_data = {
                "version": "2.0",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "last_modified": None,
                "point_aliases_default": {},
                "bays": {},
            }
            self.bay_cache.clear()
        log.info("Novo projeto criado: %s", name)
        return {"status": "sucesso", "name": name}

    def load_project(self, path: str) -> dict:
        """Carrega um projeto .md do disco."""
        if not os.path.isfile(path):
            return {"status": "erro", "mensagem": f"Arquivo não encontrado: {path}"}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            with self._lock:
                self.project_path = path
                self.project_data = data
                self.bay_cache.clear()
                # Uma chave "graph" eventualmente presente no .md é mantida
                # intacta em project_data (preservada no próximo save pelo
                # serializer), sem reconstruir estrutura em memória.
                self.last_known_mtime = self._file_snapshot(path)
            bays = len(data.get("bays", {}))
            log.info("Projeto carregado: %s (%s bay(s))", path, bays)
            return {"status": "sucesso", "bays": bays}
        except Exception as e:
            log.exception("Erro ao carregar projeto: %s", path)
            return {"status": "erro", "mensagem": str(e)}

    def save_project(self, path: str | None = None) -> dict:
        """Salva o projeto no disco."""
        target = path or self.project_path
        if not target:
            # Cria diretório padrão
            os.makedirs(_PROJECTS_DIR, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            target = os.path.join(_PROJECTS_DIR, f"projeto_{ts}.md")
        try:
            with self._lock:
                self.project_data["last_modified"] = datetime.now(timezone.utc).isoformat()
                # Organiza e limpa antes de gravar: chaves do bay na ordem
                # canônica (bay_type → cable_data) e sem lixo de pontos
                # desmarcados/seccionadoras reduzidas. A versão normalizada
                # substitui o estado em memória, mantendo disco e get_project_data
                # consistentes.
                self.project_data = normalize_project_data(self.project_data)
                atomic_write_json(target, self.project_data)
                self.project_path = target
                self.last_known_mtime = self._file_snapshot(target)
            log.info("Projeto salvo: %s", target)
            return {"status": "sucesso", "path": target}
        except Exception as e:
            log.exception("Erro ao salvar projeto")
            return {"status": "erro", "mensagem": str(e)}

    # ---- Helpers ----

    @staticmethod
    def _file_snapshot(path: str | None) -> tuple[float, int] | None:
        """Retorna (mtime, size) do arquivo ou None se indisponível."""
        if not path:
            return None
        try:
            stat = os.stat(path)
            return (stat.st_mtime, stat.st_size)
        except OSError:
            return None

    # ---- Bays ----

    def get_bay(self, bay_id: str) -> dict | None:
        """Retorna os dados de um bay (ou None)."""
        return self.project_data.get("bays", {}).get(bay_id)

    def set_bay(self, bay_id: str, data: dict) -> None:
        """Grava os dados de um bay no projeto."""
        with self._lock:
            self.project_data.setdefault("bays", {})[bay_id] = data

    def list_bays(self) -> list[dict]:
        """Retorna lista resumida de todos os bays."""
        result = []
        for bay_id, bay_data in self.project_data.get("bays", {}).items():
            result.append({
                "id": bay_id,
                "label": bay_data.get("label", bay_id),
                "template": bay_data.get("template_path", ""),
            })
        return result

    def duplicate_bay(self, source_id: str, new_label: str) -> dict:
        """Duplica um bay existente com um novo ID."""
        source = self.get_bay(source_id)
        if source is None:
            return {"status": "erro", "mensagem": f"Bay '{source_id}' não encontrado"}

        new_id = f"{source_id}-copia-{int(datetime.now(timezone.utc).timestamp())}"
        new_data = copy.deepcopy(source)
        new_data["label"] = new_label
        new_data["created_at"] = datetime.now(timezone.utc).isoformat()

        self.set_bay(new_id, new_data)
        log.info("Bay duplicado: %s → %s (%s)", source_id, new_id, new_label)
        return {
            "status": "sucesso",
            "original_id": source_id,
            "new_id": new_id,
            "new_label": new_label,
        }

    # ---- Cache ----

    def get_cache(self, bay_id: str, key: str) -> Any | None:
        """Retorna um valor do cache de um bay."""
        return self.bay_cache.get(bay_id, {}).get(key)

    def set_cache(self, bay_id: str, key: str, value: Any) -> None:
        """Armazena um valor no cache de um bay."""
        self.bay_cache.setdefault(bay_id, {})[key] = value

    def clear_cache(self, bay_id: str | None = None) -> None:
        """Limpa o cache (de um bay específico ou todos)."""
        if bay_id:
            self.bay_cache.pop(bay_id, None)
        else:
            self.bay_cache.clear()


# Singleton
_state: UniverState | None = None
_state_lock = threading.Lock()


def get_state() -> UniverState:
    """Retorna a instância singleton do UniverState."""
    global _state
    if _state is None:
        with _state_lock:
            if _state is None:
                _state = UniverState()
    return _state
