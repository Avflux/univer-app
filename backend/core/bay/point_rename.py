"""Renomeação em cascata de pontos em um bay (.md) — regra de domínio.

Tradução de ``renamePointsInBayData`` (frontend) para o backend:

- atualiza o dicionário ``points`` do bay (renomeia chaves e fixa
  ``default_name`` no canônico);
- renomeia os sub-pontos de seccionadora com o novo base + sufixo ``-N``;
- garante que todos os pontos do ``POINTS`` existam no objeto;
- propaga os novos nomes para ``additional``, ``distances`` e
  ``cable_data`` (incluindo a ``cache_key``, que embute origem/destino).

A UI envia ``labels`` (id canônico → novo nome, vazio restaura o
canônico) e recebe o bay atualizado via ``set_project_data``/recarga.

``labels`` é um *override parcial*: apenas os pontos presentes no mapa
são renomeados; os demais mantêm o alias já salvo em ``point_aliases``
(ou o canônico). Isso isola a renomeação de um ponto e preserva as
renomeações anteriores — inclusive no "Aplicar Tudo", em que o mesmo
mapa é enviado a bays com aliases diferentes.
"""

from __future__ import annotations

import re

from backend.core.bay.point_order import POINT_IDS, POINT_LABELS
from backend.core.utils.point_utils import get_canonical_name

_SUBPOINT_RE = re.compile(r"^(.+)-(\d+)$")


def is_seccionadora_sub_point(key: str, info: dict | None) -> bool:
    """True se a entrada é um sub-ponto de seccionadora (SECCIONADORA-N).

    Detecta pelo default_name + sufixo numérico, não pelo prefixo literal
    (o base pode ter sido renomeado, ex.: ``xxx-1``).
    """
    if (
        key != "SECCIONADORA"
        and isinstance(info, dict)
        and isinstance(info.get("instance_number"), int)
    ):
        return True
    m = _SUBPOINT_RE.match(str(key))
    if not m:
        return False
    if info and isinstance(info.get("default_name"), str):
        default_name = info["default_name"]
    else:
        default_name = key
    base = "SECCIONADORA" if default_name == "SECCIONADORA" else (m.group(1) or "")
    return base == "SECCIONADORA"


def seccionadora_sub_point_number(key: str, info: dict | None) -> int | None:
    """Retorna o número ``-N`` de um sub-ponto de seccionadora, ou None."""
    if not is_seccionadora_sub_point(key, info):
        return None
    if isinstance(info, dict) and isinstance(info.get("instance_number"), int):
        return int(info["instance_number"])
    m = re.search(r"-(\d+)$", str(key))
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def _non_empty(value: object) -> str:
    """Devolve o valor como string não-vazia, ou o canônico dado por fallback."""
    return str(value or "")


def _new_name_for(label: object, canonical: str) -> str:
    text = _non_empty(label).strip()
    return text if text else canonical


def merge_point_aliases(old_aliases: dict, labels: dict) -> dict[str, str]:
    """Combina os aliases salvos com as edições parciais do usuário.

    ``labels`` é um override parcial (``id canônico → novo nome``): pontos
    ausentes mantêm o alias atual (ou o canônico) e um valor vazio restaura
    o nome canônico. Sem isso, renomear um único ponto reverteria todos os
    outros ao nome padrão (bug de reversão da US de renomeação).
    """
    merged: dict[str, str] = {}
    for pid, value in old_aliases.items():
        text = str(value or "").strip()
        if text:
            merged[str(pid)] = text
    for pid, value in labels.items():
        text = str(value or "").strip()
        if text:
            merged[str(pid)] = text
        else:
            merged.pop(str(pid), None)
    return merged


def rename_points_in_bay(
    bay: dict,
    labels: dict[str, str],
) -> None:
    """Renomeia os pontos de um bay em cascata (mutação in-place).

    Args:
        bay: Dict do bay (.md). Mutado em lugar: ``point_aliases``,
            ``points``, ``additional``, ``distances`` e ``cable_data``.
        labels: Mapa ``id canônico → novo nome`` (valores vazios restauram
            o nome canônico). É um *override parcial*: pontos ausentes do
            mapa preservam o alias já salvo em ``point_aliases``.
    """
    old_aliases = bay.get("point_aliases")
    old_aliases = old_aliases if isinstance(old_aliases, dict) else {}
    # Preserva os aliases dos pontos não citados neste rename (em vez de
    # revertê-los ao canônico) — a renomeação afeta só o ponto enviado.
    effective_labels = merge_point_aliases(old_aliases, labels)
    bay["point_aliases"] = effective_labels

    # Novo nome base da SECCIONADORA neste rename (vazio → canônico).
    secc_new_base = _new_name_for(effective_labels.get("SECCIONADORA"), "SECCIONADORA")

    # 1. Atualiza o dicionário "points"
    points = bay.get("points")
    points = points if isinstance(points, dict) else {}
    updated_points: dict[str, dict] = {}
    point_renames: dict[str, str] = {}

    for key, info in points.items():
        if not isinstance(info, dict):
            continue

        # Sub-pontos de seccionadora: renomeia TODOS (preservando o sufixo).
        if is_seccionadora_sub_point(key, info):
            num = seccionadora_sub_point_number(key, info)
            if num is not None:
                instance_id = f"SECCIONADORA-{num}"
                instance_base = _new_name_for(
                    effective_labels.get(instance_id),
                    secc_new_base,
                )
                if effective_labels.get(instance_id):
                    # User provided a custom label for this instance; ensure it ends with -{num}
                    if not instance_base.endswith(f"-{num}"):
                        instance_name = f"{instance_base}-{num}"
                    else:
                        instance_name = instance_base
                else:
                    instance_name = f"{instance_base}-{num}"
                point_renames[key] = instance_name
                point_renames[f"SECCIONADORA-{num}"] = instance_name
                info["instance_number"] = num
                updated_points[instance_name] = info
                continue

        orig_id = info.get("default_name")
        if not (isinstance(orig_id, str) and orig_id):
            orig_id = key

        # Descobre o id canônico: o próprio id, o label humano, o alias
        # antigo ou a chave atual podem identificar o ponto.
        canonical = None
        for pid in POINT_IDS:
            old_alias = old_aliases.get(pid)
            if (
                pid == orig_id
                or POINT_LABELS.get(pid) == orig_id
                or (old_alias and old_alias == orig_id)
                or pid == key
                or POINT_LABELS.get(pid) == key
                or (old_alias and old_alias == key)
            ):
                canonical = pid
                break
        if canonical is not None:
            orig_id = canonical

        new_name = _new_name_for(effective_labels.get(orig_id), orig_id)
        info["default_name"] = orig_id
        updated_points[new_name] = info

    # Garante que todos os pontos do POINTS existam no objeto
    for pid in POINT_IDS:
        has_point = any(
            isinstance(p, dict) and p.get("default_name") == pid
            for p in updated_points.values()
        )
        if not has_point:
            new_name = _new_name_for(effective_labels.get(pid), pid)
            updated_points[new_name] = {
                "selected": False,
                "phases": 1,
                "extra_distance": 0.0,
                "coordinates": None,
                "default_name": pid,
            }

    bay["points"] = updated_points

    # Mapa nome canônico (inclui o alias do banco, ex.: "PAINEL" para
    # CASA DE COMANDO/CABANA) → nome atual no bay. O banco e os templates
    # usam nomes canônicos; as linhas salvas em ``distances``, ``cable_data``
    # e ``additional`` podem contê-los e precisam acompanhar a renomeação.
    current_name_by_canonical: dict[str, str] = {}
    for display_name, info in updated_points.items():
        default_name = info.get("default_name") if isinstance(info, dict) else None
        if not isinstance(default_name, str) or not default_name:
            default_name = display_name
        # Só propaga pontos efetivamente renomeados (chave ≠ canônico):
        # sem isso uma renomeação qualquer reescreveria também os nomes
        # canônicos de pontos que o usuário não tocou.
        if display_name == default_name:
            continue
        canonical = get_canonical_name(default_name)
        current = current_name_by_canonical.get(canonical)
        # Um ponto selecionado tem prioridade sobre os placeholders
        # (selected=False) criados para completar os POINT_IDS.
        if current is None or (isinstance(info, dict) and info.get("selected")):
            current_name_by_canonical[canonical] = display_name

    # --- Helpers de resolução de nomes (para as listas abaixo) ----------

    def resolve_sub_point_rename(name: str) -> str | None:
        m = _SUBPOINT_RE.match(name)
        if not m:
            return None
        base, num = m.group(1), m.group(2)
        instance_id = f"SECCIONADORA-{num}"
        old_instance_name = old_aliases.get(instance_id)
        if old_instance_name and base == old_instance_name.removesuffix(f"-{num}"):
            instance_base = _new_name_for(
                effective_labels.get(instance_id), secc_new_base
            )
            return (
                instance_base
                if instance_base.endswith(f"-{num}")
                else f"{instance_base}-{num}"
            )
        for pid in POINT_IDS:
            old_alias = old_aliases.get(pid)
            base_matches = (
                base == pid
                or base == POINT_LABELS.get(pid)
                or (old_alias and base == old_alias)
            )
            if not base_matches:
                continue
            new_base = _new_name_for(effective_labels.get(pid), pid)
            instance_base = _new_name_for(effective_labels.get(instance_id), new_base)
            updated = (
                instance_base
                if instance_base.endswith(f"-{num}")
                else f"{instance_base}-{num}"
            )
            return None if updated == name else updated
        return None

    def resolve_point_name(name: str) -> str:
        if not name:
            return name
        if name in point_renames:
            return point_renames[name]
        sub = resolve_sub_point_rename(name)
        if sub:
            return sub
        for pid in POINT_IDS:
            new_name = _new_name_for(effective_labels.get(pid), pid)
            old_alias = old_aliases.get(pid)
            if (
                name == pid
                or name == POINT_LABELS.get(pid)
                or (old_alias and name == old_alias)
            ):
                return new_name
        # Nome canônico que não é um id de POINT_IDS (ex.: "PAINEL" para
        # CASA DE COMANDO/CABANA): resolve pelo nome atual do ponto.
        return current_name_by_canonical.get(get_canonical_name(name), name)

    # 2. Atualiza a lista "additional"
    additional = bay.get("additional")
    if isinstance(additional, list):
        renamed: list[dict] = []
        for row in additional:
            if not isinstance(row, dict):
                renamed.append(row)  # type: ignore[arg-type]
                continue
            row_nome = str(row.get("nome") or "")
            updated = resolve_point_name(row_nome)
            if updated == row_nome:
                renamed.append(row)
            else:
                copied = dict(row)
                copied["nome"] = updated
                renamed.append(copied)
        bay["additional"] = renamed

    # 3. Atualiza a lista "distances"
    distances = bay.get("distances")
    if isinstance(distances, list):
        renamed_dist: list[dict] = []
        for row in distances:
            if not isinstance(row, dict):
                renamed_dist.append(row)  # type: ignore[arg-type]
                continue
            # PAINEL é o alias canônico de CASA DE COMANDO/CABANA no banco.
            # Outra ferramenta já grava "PAINEL" no campo origem das
            # distâncias; a lista de cabos depende desse valor exato para
            # gerar a lista correta. Não devemos sobrescrevê-lo ao renomear
            # o ponto — apenas propagamos renomeações de ORIGEM quando o
            # valor NÃO é "PAINEL".
            raw_origem = str(row.get("origem") or "")
            origem = resolve_point_name(raw_origem)
            destino = resolve_point_name(str(row.get("destino") or ""))
            copied = dict(row)
            if raw_origem == "PAINEL":
                copied["origem"] = "PAINEL"
            else:
                copied["origem"] = origem
            copied["destino"] = destino
            renamed_dist.append(copied)
        bay["distances"] = renamed_dist

    # 4. Atualiza a lista "cable_data" — inclui os pontos embutidos na
    #    cache_key ("bitola|funcao|origem|destino|bay").
    cable_data = bay.get("cable_data")
    if isinstance(cable_data, list):
        renamed_cables: list[dict] = []
        for cable in cable_data:
            if not isinstance(cable, dict):
                renamed_cables.append(cable)  # type: ignore[arg-type]
                continue
            origin = resolve_point_name(str(cable.get("origin") or ""))
            destination = resolve_point_name(str(cable.get("destination") or ""))
            updated = dict(cable)
            updated["origin"] = origin
            updated["destination"] = destination

            cache_key = str(cable.get("cache_key") or "")
            if cache_key:
                parts = cache_key.split("|")
                if len(parts) >= 4:
                    resolved_origin = resolve_point_name(parts[2])
                    resolved_destination = resolve_point_name(parts[3])
                    if resolved_origin != parts[2] or resolved_destination != parts[3]:
                        parts[2] = resolved_origin
                        parts[3] = resolved_destination
                        updated["cache_key"] = "|".join(parts)
            renamed_cables.append(updated)
        bay["cable_data"] = renamed_cables
