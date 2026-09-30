import copy
import json
import os
from threading import RLock

from backend.core.utils.atomic_io import atomic_write_json

# Config interno do app — lido em toda execução.
_BUNDLED_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "config.json"
)


def _user_config_path():
    """Caminho do config.json do usuário em %LOCALAPPDATA%\\NEXUS."""
    base = os.environ.get("LOCALAPPDATA") or os.path.join(
        os.path.expanduser("~"), "AppData", "Local"
    )
    return os.path.join(base, "NEXUS", "config.json")


# Resolvido uma única vez no import (ambiente não muda durante a execução).
_USER_CONFIG_PATH = _user_config_path()

# Chaves persistidas no config do usuário; o restante vive no config interno.
_USER_ONLY_KEYS = ("last_directory",)

# Defaults usados quando o config interno não estiver disponível.
_DEFAULTS = {
    "app_name": "Univer",
    "version": "0.0.4",
    "language": "Python",
    "os": "Windows",
    "license": "MIT",
    "logging": {
        "level": "INFO",
        "log_dir": "logs",
        "log_file": "univer.log",
        "max_bytes": 1048576,
        "backup_count": 5,
        "console": True,
        "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        "datefmt": "%Y-%m-%d %H:%M:%S",
    },
}

_cache = None
_lock = RLock()


class ConfigError(RuntimeError):
    """Erro ao carregar o config.json."""


def get_config_path():
    """Caminho do config.json do usuário em %LOCALAPPDATA%\\NEXUS."""
    return _USER_CONFIG_PATH


def _read_bundled_config():
    """Lê o config interno. Retorna defaults se ausente; levanta ConfigError se inválido."""
    if not os.path.exists(_BUNDLED_CONFIG_PATH):
        # Cópia profunda: _load mescla chaves do usuário em dicts aninhados.
        return copy.deepcopy(_DEFAULTS)
    try:
        with open(_BUNDLED_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise ConfigError(f"Falha ao ler {_BUNDLED_CONFIG_PATH}: {e}") from e
    if not isinstance(data, dict):
        raise ConfigError(
            f"Conteúdo de {_BUNDLED_CONFIG_PATH} deve ser um objeto JSON."
        )
    # Config interno prevalece; defaults preenchem chaves ausentes.
    merged = copy.deepcopy(_DEFAULTS)
    merged.update(data)
    return merged


def _read_user_config_lenient():
    """Lê o config do usuário sem lançar; devolve ``{}`` se ausente/corrompido."""
    try:
        with open(_USER_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _user_payload_from(data):
    """Extrai de ``data`` apenas as chaves persistidas no config do usuário."""
    payload = {}
    if isinstance(data, dict) and "last_directory" in data:
        payload["last_directory"] = data["last_directory"]
    return payload


def _write_user_config(payload):
    """Grava ``payload`` (apenas chaves de usuário) no config do usuário."""
    atomic_write_json(_USER_CONFIG_PATH, payload)


def _ensure_user_config():
    """Cria o config do usuário na primeira execução e migra configs antigos.

    Configs legados que copiavam o template inteiro são reescritos mantendo
    apenas last_directory. Nunca lança.
    """
    if not os.path.exists(_USER_CONFIG_PATH):
        try:
            _write_user_config({"last_directory": ""})
        except OSError:
            pass
        return
    data = _read_user_config_lenient()
    clean = _user_payload_from(data) or {"last_directory": ""}
    if data != clean:
        try:
            _write_user_config(clean)
        except OSError:
            pass


def _load():
    global _cache
    if _cache is not None:
        return _cache
    with _lock:
        if _cache is not None:
            return _cache

        # 1) Variáveis do app: config interno (src/core/config.json).
        data = _read_bundled_config()

        # 2) Chaves do usuário: last_directory.
        _ensure_user_config()
        user_data = _read_user_config_lenient()
        if "last_directory" in user_data:
            data["last_directory"] = user_data["last_directory"]

        _cache = data
        return _cache


def reload_config():
    global _cache
    with _lock:
        _cache = None


def get_config():
    # Cópia profunda: evita que mutações externas corrompam o cache.
    return copy.deepcopy(_load())


def get(key):
    return _load()[key]


def get_app_name():
    return _load()["app_name"]


def get_version():
    """Versão do aplicativo (lida do config interno ``src/core/config.json``)."""
    return _load()["version"]


def get_last_directory():
    """Retorna o último diretório usado para abrir/salvar; "" se nenhum."""
    return _load().get("last_directory", "") or ""


def set_last_directory(path):
    """Persiste o diretório de ``path`` como último local de abertura/salvamento.

    Aceita caminho de arquivo (usa o pai) ou diretório. Retorna o diretório
    salvo, ou "" se inválido. Falhas de escrita são silenciadas.
    """
    if not path:
        return ""
    directory = path if os.path.isdir(path) else os.path.dirname(os.path.abspath(path))
    if not directory or not os.path.isdir(directory):
        return ""
    directory = os.path.normpath(directory)
    try:
        save_config({"last_directory": directory})
    except OSError:
        return ""
    return directory


def save_config(updates):
    """Atualiza o config do usuário com ``updates`` e recarrega o cache.

    Só persiste last_directory. Variáveis do app vivem no config interno e
    não podem ser gravadas aqui.

    Raises:
        ConfigError: se ``updates`` contiver chaves não permitidas.
    """
    global _cache
    with _lock:
        current = copy.deepcopy(_load())
        _apply_user_updates(current, updates)
        _write_user_config(_user_payload_from(current))
        _cache = current
    return current


def _apply_user_updates(current, updates):
    """Valida e aplica ``updates`` sobre ``current`` em memória."""
    unknown = set(updates) - set(_USER_ONLY_KEYS)
    if unknown:
        raise ConfigError(
            "save_config: chaves não persistíveis no config do usuário: "
            f"{sorted(unknown)}. Variáveis do app ficam no config interno."
        )
    for key, value in updates.items():
        if value is None:
            continue
        if key == "last_directory":
            current["last_directory"] = value
