"""Organização e limpeza do projeto .md na gravação (regras puras).

Três responsabilidades, chamadas por ``UniverState.save_project`` antes de
persistir o arquivo em disco:

1. Ordem canônica
As chaves de cada bay seguem esta ordem fixa:
bay_type, measurement_type, voltage_level, sincronizador_enabled, points, point_aliases,
additional, distances, cable_data.
As demais vão ao final. Dentro de points, segue a ordem dos POINT_IDS, com sub-pontos de
seccionadora agrupados após a base. O JSON mantém essa ordem porque a gravação não
reordena chaves.

2. Limpeza de lixo
O .md reflete o estado real da interface:
Sub-pontos de seccionadora além do configurado são removidos.
Referências a pontos desmarcados (selected: false) são eliminadas de additional,
distances e cable_data.
Com sincronizador_enabled: false, referências ao SINCRONIZADOR também são removidas
desses campos.

3. Estrutura do projeto
Nenhuma chave de bay (points, point_aliases, additional, distances, cable_data, …)
pode viver no nível do projeto. Um ``distances`` remanescente no root — lixo que o
estado semeava e o "Aplicar" do dialog de bitolas acabava gravando — é descartado;
as distâncias válidas ficam apenas em ``bays.<id>.distances``.

O grafo de canaletas (``graph``: nodes/edges/diagnostics/stats) é uma chave
canônica de nível de projeto: é validado estruturalmente e preservado para
compatibilidade com .md que já o contenham. A geração/reconstrução do grafo
foi descontinuada — não é mais usada pelo frontend.
"""

from __future__ import annotations

import re

from backend.core.bay.point_order import POINT_IDS
from backend.core.bay.point_rename import (
    is_seccionadora_sub_point,
    seccionadora_sub_point_number,
)

# Ordem canônica das chaves de um bay no .md. Chaves não listadas vão
# ao final, na ordem em que aparecem (nenhuma informação é descartada).
BAY_KEY_ORDER: tuple[str, ...] = (
    "bay_type",
    "measurement_type",
    "voltage_level",
    "sincronizador_enabled",
    "points",
    "point_aliases",
    "additional",
    "distances",
    "cable_data",
)

# Defaults compatíveis com o frontend (bay recém-criado) para chaves
# canônicas ausentes em arquivos antigos.
BAY_KEY_DEFAULTS: dict[str, object] = {
    "bay_type": "",
    "measurement_type": "",
    "voltage_level": "",
    "sincronizador_enabled": True,
    "points": {},
    "point_aliases": {},
    "additional": [],
    "distances": [],
    "cable_data": [],
}

# Ordem canônica das chaves de nível de projeto no .md. Chaves não
# listadas vão ao final, na ordem em que aparecem (nenhuma informação é
# descartada).
PROJECT_KEY_ORDER: tuple[str, ...] = (
    "version",
    "created_at",
    "last_modified",
    "point_aliases_default",
    "bays",
    "bay_order",
    "graph",
)

# Chaves que descrevem um bay e NUNCA podem viver no nível do projeto.
# ``distances`` era semeada no root pelo estado e gravada pelo "Aplicar"
# do dialog de bitolas; aqui ela é descartada para garantir que a
# estrutura do .md tenha as distâncias apenas em ``bays.<id>.distances``.
PROJECT_FORBIDDEN_KEYS: frozenset[str] = frozenset(BAY_KEY_ORDER)

# Ordem canônica das chaves de uma entrada dentro de ``points``.
_POINT_KEY_ORDER: tuple[str, ...] = (
    "selected",
    "phases",
    "extra_distance",
    "coordinates",
    "default_name",
    "is_seccionadora_point",
)

_SUBPOINT_RE = re.compile(r"^(.+)-(\d+)$")
_CANONICAL_SECC_RE = re.compile(r"^SECCIONADORA-(\d+)$")

# Alias canônico: PAINEL é a CASA DE COMANDO (mesma regra do point_order).
_POINT_ALIASES: dict[str, str] = {"PAINEL": "CASA DE COMANDO"}

# Pseudo-ponto controlado pela flag do bay (não existe em ``points``).
SINCRONIZADOR_ID = "SINCRONIZADOR"


# --- Validação do grafo de canaletas -----------------------------------------


def _sanitize_graph(graph: object) -> dict | None:
    """Valida o payload do grafo (``project_data["graph"]``) sem alterá-lo.

    O grafo de canaletas vive no nível do projeto com o formato
    {version, nodes, edges, diagnostics, stats}. Estruturalmente válido é
    qualquer dict com ``nodes``/``edges`` como listas (lista vazia = grafo
    sem canaletas, também válido).

    Retorna o payload intacto quando válido, ``None`` quando corrompido —
    neste caso a chave é descartada (não vale a pena persistir lixo).
    """
    if not isinstance(graph, dict):
        return None
    if not isinstance(graph.get("nodes"), list) or not isinstance(
        graph.get("edges"), list
    ):
        return None
    return graph


# --- Resolução de referências a pontos ---------------------------------------


def _entry_for_canonical(points: dict, canonical: str) -> dict | None:
    """Entrada de ponto de um id canônico (chave direta ou via default_name)."""
    for key, info in points.items():
        if not isinstance(info, dict):
            continue
        default_name = str(info.get("default_name") or key)
        if key == canonical or default_name == canonical:
            return info
    return None


def _is_selected(info: dict | None) -> bool:
    return bool(info and info.get("selected"))


def _is_seccionadora_selected(points: dict) -> bool:
    """SECCIONADORA conta como selecionada se QUALQUER sub-ponto estiver.

    A entrada-pai ``SECCIONADORA`` fica sempre ``selected: false``
    (placeholder v2.0) — quem carrega a seleção são os filhos ``-N``.
    """
    for key, info in points.items():
        if isinstance(info, dict) and is_seccionadora_sub_point(str(key), info):
            if _is_selected(info):
                return True
    return False

def _seccionadora_entry_by_number(points: dict, number: int) -> dict | None:
    """Sub-ponto de seccionadora pelo NÚMERO da instância (ignora o apelido da chave)."""
    for key, info in points.items():
        if (
            isinstance(info, dict)
            and is_seccionadora_sub_point(str(key), info)
            and seccionadora_sub_point_number(str(key), info) == number
        ):
            return info
    return None


def _status_of(points: dict, canonical: str) -> tuple[str, str | None]:
    """Status de um id canônico considerando a regra da SECCIONADORA.

    Entrada ausente no ``points`` NÃO é desmarcação — só um
    ``selected: false`` explícito (gravado pelo "Aplicar" do dialog)
    significa desmarcado. Ausente → ``unknown`` (preservar).
    """
    if canonical == "SECCIONADORA":
        return (
            ("selected", canonical)
            if _is_seccionadora_selected(points)
            else ("deselected", canonical)
        )
    info = _entry_for_canonical(points, canonical)
    if info is None:
        return ("unknown", canonical)
    return ("selected", canonical) if _is_selected(info) else ("deselected", canonical)


def resolve_point_reference(
    name: str,
    points: dict,
    sincronizador_enabled: bool,
) -> tuple[str, str | None]:
    """Classifica um nome vindo de additional/distances/cable_data.

    Retorna ``(status, canonical)``:

    - ``"selected"``   — resolve a um ponto atualmente marcado;
    - ``"deselected"`` — resolve a um ponto conhecido porém desmarcado
      (ou sub-ponto de seccionadora que não existe mais no ``points``);
    - ``"unknown"``    — não é um ponto do catálogo (TC, TP, COSTURA,
      texto vazio, …) e não deve ser julgado aqui.
    """
    if not name:
        return ("unknown", None)

    # Alias canônico (PAINEL → CASA DE COMANDO).
    alias = _POINT_ALIASES.get(name)
    if alias:
        return _status_of(points, alias)

    # Pseudo-ponto governado pela flag do bay.
    if name == SINCRONIZADOR_ID:
        if sincronizador_enabled:
            return ("selected", SINCRONIZADOR_ID)
        return ("deselected", SINCRONIZADOR_ID)

    # Chave exata no ``points`` (inclui renomeados e sub-pontos -N).
    info = points.get(name)
    if isinstance(info, dict):
        canonical = str(info.get("default_name") or name)
        if is_seccionadora_sub_point(name, info):
            if _is_selected(info):
                return ("selected", canonical)
            return ("deselected", canonical)
        return _status_of(points, canonical)

    # Id canônico direto (a entrada pode viver sob chave renomeada).
    if any(
        isinstance(p, dict) and str(p.get("default_name") or k) == name
        for k, p in points.items()
    ):
        return _status_of(points, name)

        # Check for seccionadora instance by number (ignore key)
    m_inst = _CANONICAL_SECC_RE.match(name)
    if m_inst:
        entry = _seccionadora_entry_by_number(points, int(m_inst.group(1)))
        if entry is not None:
            return ("selected" if _is_selected(entry) else "deselected", "SECCIONADORA")
        return ("deselected", "SECCIONADORA")  # instância realmente removida (trim)
# Sub-ponto "base-N" sem entrada própria: se o base é um ponto
    # conhecido, o sub-ponto foi removido (trim de seccionadora) → lixo.
    m = _SUBPOINT_RE.match(name)
    if m:
        base = m.group(1) or ""
        base_status, base_canonical = resolve_point_reference(
            base,
            points,
            sincronizador_enabled,
        )
        if base_status != "unknown":
            return ("deselected", base_canonical)
    return ("unknown", None)


def _find_point_info(name: str, points: dict) -> dict | None:
    """Busca a entrada de um ponto por chave exata, default_name ou alias canônico."""
    if not name or not isinstance(points, dict):
        return None
    info = points.get(name)
    if isinstance(info, dict):
        return info
    for k, p in points.items():
        if isinstance(p, dict) and str(p.get("default_name") or k) == name:
            return p
    alias = _POINT_ALIASES.get(name)
    if alias:
        return _find_point_info(alias, points)
    # Check for seccionadora instance by number (ignore key)
    m_inst = _CANONICAL_SECC_RE.match(name)
    if m_inst:
        return _seccionadora_entry_by_number(points, int(m_inst.group(1)))
    return None


def _clean_additional(rows: list, points: dict, sincronizador_enabled: bool) -> list:
    """Remove linhas cujo ``nome`` aponta para ponto desmarcado e sincroniza coordenadas.

    Linhas com ``nome`` vazio também são lixo (``additional`` deriva de
    points — cada linha representa um ponto com coordenadas).
    """
    cleaned: list = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        nome = str(row.get("nome") or "")
        status, _ = resolve_point_reference(nome, points, sincronizador_enabled)
        if status != "deselected" and bool(nome):
            row_copy = dict(row)
            point_info = _find_point_info(nome, points)
            if isinstance(point_info, dict):
                coords = point_info.get("coordinates")
                if isinstance(coords, list) and len(coords) >= 2:
                    row_copy["coordenadas"] = f"{coords[0]}, {coords[1]}"
                elif coords is None:
                    row_copy["coordenadas"] = ""
            cleaned.append(row_copy)
    return cleaned


def _clean_pair_rows(rows: list, points: dict, sincronizador_enabled: bool) -> list:
    """Remove linhas com endpoint apontando para ponto desmarcado.

    ``distances`` usa ``origem``/``destino``; ``cable_data`` usa
    ``origin``/``destination``. A linha é descartada quando QUALQUER
    lado resolve a um ponto conhecido e desmarcado. Lados desconhecidos
    (equipamentos do banco, ex.: TC/TP/COSTURA) preservam a linha; linha
    totalmente vazia é mantida (placeholder de nova linha da UI).
    """
    cleaned: list = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        origem = str(row.get("origem") or row.get("origin") or "")
        destino = str(row.get("destino") or row.get("destination") or "")
        status_origem, _ = resolve_point_reference(
            origem, points, sincronizador_enabled
        )
        status_destino, _ = resolve_point_reference(
            destino, points, sincronizador_enabled
        )
        if status_origem == "deselected" or status_destino == "deselected":
            continue  # Referência a ponto removido → lixo.
        cleaned.append(row)
    return cleaned


# --- Trim de seccionadoras ---------------------------------------------------


def _count_selected_seccionadoras(points: dict) -> int:
    """Quantidade de sub-pontos de seccionadora selecionados (alvo)."""
    count = 0
    for key, info in points.items():
        if isinstance(info, dict) and is_seccionadora_sub_point(str(key), info):
            if _is_selected(info):
                count += 1
    return count


def _trim_seccionadora_sub_points(points: dict, target_count: int) -> dict:
    """Mantém apenas os N primeiros sub-pontos de seccionadora (por número).

    Ex.: arquivo tem SECCIONADORA-1..3 e a interface ajusta para 2 →
    SECCIONADORA-3 sai; 1 e 2 ficam preservados com seus dados. Sem
    sub-pontos selecionados, nenhum é removido (nada indica redução).
    """
    target = max(target_count, 0)
    if target == 0:
        return points
    numbered: dict[str, int] = {}
    for key, info in points.items():
        if not isinstance(info, dict) or not is_seccionadora_sub_point(str(key), info):
            continue
        num = seccionadora_sub_point_number(str(key), info)
        if num is None:
            continue
        numbered[str(key)] = num
    ordered = sorted(numbered.items(), key=lambda kv: kv[1])
    to_remove = {key for key, _ in ordered[target:]}
    if not to_remove:
        return points
    return {key: info for key, info in points.items() if key not in to_remove}


# --- Ordenação ---------------------------------------------------------------


def ordered_bay_dict(bay: dict) -> dict:
    """Reconstrói o bay com as chaves na ordem canônica do .md."""
    ordered: dict = {}
    for key in BAY_KEY_ORDER:
        if key in bay:
            ordered[key] = bay[key]
    for key, value in bay.items():
        if key not in ordered:
            ordered[key] = value
    return ordered


def _ordered_point_info(info: dict) -> dict:
    ordered: dict = {}
    for key in _POINT_KEY_ORDER:
        if key in info:
            ordered[key] = info[key]
    for key, value in info.items():
        if key not in ordered:
            ordered[key] = value
    return ordered


def _canonical_base_of(key: str, points: dict) -> str | None:
    """Id canônico do ponto representado pela chave (sub-ponto usa o base)."""
    m = _SUBPOINT_RE.match(key)
    info = points.get(key)
    if not isinstance(info, dict):
        info = None
    default_name = (
        str(info.get("default_name"))
        if info is not None and info.get("default_name")
        else None
    )
    if m:
        base = m.group(1) or ""
        if default_name and default_name in POINT_IDS:
            return default_name
        base_info = points.get(base)
        base_default = (
            str(base_info.get("default_name"))
            if isinstance(base_info, dict) and base_info.get("default_name")
            else None
        )
        if base_default and base_default in POINT_IDS:
            return base_default
        if base in POINT_IDS:
            return base
        return None
    if default_name and default_name in POINT_IDS:
        return default_name
    return key if key in POINT_IDS else None


def _ordered_points(points: dict) -> dict:
    """Reordena ``points`` na ordem canônica (sub-pontos após a base)."""
    result: dict = {}
    keys = list(points.keys())
    placed: set[str] = set()

    # Índice canônico de cada chave; desconhecidos vão ao final (estável).
    def sort_key(key: str) -> tuple[int, int]:
        canonical = _canonical_base_of(key, points)
        if canonical and canonical in POINT_IDS:
            return (0, POINT_IDS.index(canonical))
        return (1, keys.index(key))

    bases = [k for k in keys if not _SUBPOINT_RE.match(k)]
    subs_by_base: dict[str, list[str]] = {}
    for key in keys:
        m = _SUBPOINT_RE.match(key)
        if m:
            subs_by_base.setdefault(m.group(1) or "", []).append(key)

    for base_key in sorted(bases, key=sort_key):
        if base_key in placed:
            continue
        result[base_key] = _ordered_point_info(points[base_key])
        placed.add(base_key)
        # Sub-pontos cujo sufixo textual casa com ESTA base (chave exata
        # ou canônico renomeado). Rejeitados no trim já saíram do dict.
        base_canonical = _canonical_base_of(base_key, points) or base_key
        related: list[str] = []
        for sub_key, sub_list in subs_by_base.items():
            if (
                sub_key == base_key
                or _canonical_base_of(sub_key, points) == base_canonical
            ):
                related.extend(sub_list)
        for sub_key in sorted(
            related, key=lambda k: int(_SUBPOINT_RE.match(k).group(2) or 0)
        ):
            if sub_key in placed:
                continue
            result[sub_key] = _ordered_point_info(points[sub_key])
            placed.add(sub_key)
    # Segurança: qualquer chave restante (base sem entrada própria).
    for key in keys:
        if key not in placed:
            result[key] = _ordered_point_info(points[key])
    return result


# --- Entrada principal -------------------------------------------------------


def normalize_bay(bay: dict) -> dict:
    """Aplica limpeza + ordenação canônica a um bay (sem mutar o original)."""
    points_raw = bay.get("points")
    points_raw = points_raw if isinstance(points_raw, dict) else {}

    # Backfill instance_number para arquivos antigos, sem mutar o original
    points_raw = {
        k: ({**v, "instance_number": n}
            if isinstance(v, dict)
            and is_seccionadora_sub_point(str(k), v)
            and not isinstance(v.get("instance_number"), int)
            and (n := seccionadora_sub_point_number(str(k), v)) is not None
            else v)
        for k, v in points_raw.items()
    }

    # 1. Trim de seccionadoras: mantém só a quantidade selecionada.
    secc_target = _count_selected_seccionadoras(points_raw)
    points = _trim_seccionadora_sub_points(points_raw, secc_target)

    # 2. Limpeza das listas derivadas (referências a pontos removidos).
    sincronizador_enabled = bool(bay.get("sincronizador_enabled", True))
    additional = bay.get("additional")
    additional = _clean_additional(
        additional if isinstance(additional, list) else [],
        points,
        sincronizador_enabled,
    )
    distances = bay.get("distances")
    distances = _clean_pair_rows(
        distances if isinstance(distances, list) else [],
        points,
        sincronizador_enabled,
    )
    cable_data = bay.get("cable_data")
    cable_data = _clean_pair_rows(
        cable_data if isinstance(cable_data, list) else [],
        points,
        sincronizador_enabled,
    )

    # 3. Reconstrução: chaves canônicas sempre presentes (default quando
    #    ausentes em arquivos antigos), na ordem canônica, points ordenado.
    normalized = dict(bay)
    for key in BAY_KEY_ORDER:
        if key not in normalized:
            normalized[key] = BAY_KEY_DEFAULTS[key]
    normalized["points"] = _ordered_points(points)
    normalized["additional"] = additional
    normalized["distances"] = distances
    normalized["cable_data"] = cable_data
    aliases = bay.get("point_aliases")
    normalized["point_aliases"] = aliases if isinstance(aliases, dict) else {}
    return ordered_bay_dict(normalized)


def _apply_bay_order(bays: dict, bay_order: object) -> dict:
    """Reordena ``bays`` conforme ``bay_order`` (ordem das abas de bay).

    A ordem das chaves de um objeto JSON não é confiável: parsers podem
    reordená-la — no JavaScript (frontend), chaves que parecem número inteiro
    ("2", "10") são ordenadas automaticamente e vêm antes das demais, tanto
    ao gravar quanto ao ler. Por isso o projeto guarda ``bay_order``: o array
    explícito com a ordem das abas escolhida pelo usuário.

    Chaves fora do array (bay recém-criado, arquivo antigo sem o campo) vão
    para o final, preservando a ordem em que já estavam no arquivo.
    """
    if not isinstance(bay_order, list):
        return bays
    ordered: dict = {}
    for key in bay_order:
        if isinstance(key, str) and key in bays and key not in ordered:
            ordered[key] = bays[key]
    for key, value in bays.items():
        if key not in ordered:
            ordered[key] = value
    return ordered


def normalize_project_data(data: dict) -> dict:
    """Normaliza o projeto completo (bays limpos + estrutura canônica).

    O dict original não é mutado. As chaves de nível de projeto seguem
    ``PROJECT_KEY_ORDER`` e chaves desconhecidas são preservadas ao final.
    Chaves de bay (``PROJECT_FORBIDDEN_KEYS``, ex.: ``distances``) que
    tenham vazado para o nível do projeto são descartadas — a estrutura
    canônica vive apenas dentro de ``bays``.
    """
    pending = dict(data)
    bays = data.get("bays")
    if isinstance(bays, dict):
        ordered_bays = _apply_bay_order(bays, data.get("bay_order"))
        pending["bays"] = {
            bay_id: normalize_bay(bay) if isinstance(bay, dict) else bay
            for bay_id, bay in ordered_bays.items()
        }
        # A ordem explícita das abas acompanha as chaves realmente gravadas
        # (bay novo entra no final; chave inexistente sai da lista).
        if isinstance(data.get("bay_order"), list):
            pending["bay_order"] = list(pending["bays"])

    result: dict = {}
    dropped: set[str] = set()
    for key in PROJECT_KEY_ORDER:
        if key not in pending:
            continue
        if key == "graph":
            sanitized = _sanitize_graph(pending[key])
            if sanitized is None:
                dropped.add(key)  # corrompido: não re-adicionar no fallback
            else:
                result[key] = sanitized
            continue
        result[key] = pending[key]
    for key, value in pending.items():
        if key in result or key in dropped or key in PROJECT_FORBIDDEN_KEYS:
            continue
        result[key] = value
    return result
