"""Gerenciamento de dados de bay independente da interface gráfica.

Contém:
- Constantes de definição de pontos (``DEFAULT_POINTS``)
- Helpers puros de dados de bay (``parse_seccionadora_points``,
  ``get_pending_extra_distances``)
"""

from backend.core.utils.point_utils import get_canonical_name

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

DEFAULT_POINTS = {
    'CASA DE COMANDO': {'point': None, 'alias': 'PAINEL', 'extra_distance': 0.0},
    'CABANA': {'point': None, 'alias': 'PAINEL', 'extra_distance': 0.0},
    'CAIXA TC': {'point': None, 'phases': 1, 'extra_distance': 0.0},
    'CAIXA TP': {'point': None, 'phases': 1, 'extra_distance': 0.0},
    'TRANSFORMADOR': {'point': None, 'extra_distance': 0.0},
    'REATOR': {'point': None, 'extra_distance': 0.0},
    'CAPACITOR': {'point': None, 'extra_distance': 0.0},
    'CAIXA DE DISTRIBUIÇÃO CA': {'point': None, 'extra_distance': 0.0},
    'DISJUNTOR': {'point': None, 'extra_distance': 0.0},
    'MERGING UNIT': {'point': None, 'extra_distance': 0.0},
    'SECCIONADORA': {'point': None, 'count': 1, 'points': {}, 'extra_distance': 0.0},
}

# ---------------------------------------------------------------------------
# Helpers de dados de bay
# ---------------------------------------------------------------------------


def parse_seccionadora_points(seccionadora_points_data):
    """Parseia dados de pontos de seccionadora (novo e antigo formato).

    Args:
        seccionadora_points_data: Dict do projeto.

    Returns:
        tuple: (new_format_points, count)
            new_format_points: dict { 'SECCIONADORA-N': (x, y), ... }
            count: número total de pontos
    """
    new_format = {}
    old_format = []

    for key, value in seccionadora_points_data.items():
        if key.startswith('SECCIONADORA-'):
            if isinstance(value, (list, tuple)) and len(value) >= 2:
                new_format[key] = (value[0], value[1])
        else:
            # Formato antigo: {'x': [x, y, ...]} ou {'x': y}
            if isinstance(value, (list, tuple)) and len(value) >= 2:
                old_format.append((float(key), value[0], value[1]))
            else:
                old_format.append((float(key), float(value), 0.0))

    old_format.sort(key=lambda p: p[0])

    existing = [int(k.split('-')[1]) for k in new_format if k.split('-')[1].isdigit()]
    next_idx = max(existing, default=0) + 1

    for _, x, y in old_format:
        new_format[f'SECCIONADORA-{next_idx}'] = (x, y)
        next_idx += 1

    return new_format, len(new_format)


def get_pending_extra_distances(bay_data):
    """Extrai valores de Add Distância pendentes de dados carregados.

    Lê a chave ``extra_distance``. Para compatibilidade com saves
    antigos, se a chave não existir mas ``add_distance`` estiver
    presente, absorve o valor legado e remove ``add_distance`` in-place
    — assim o próximo ``save`` já sai com a chave nova.

    Args:
        bay_data: Dict carregado do projeto.

    Returns:
        dict: {nome_canônico: valor_float}
    """
    pending = {}
    for point_name, point_data in bay_data.get('points', {}).items():
        if not isinstance(point_data, dict):
            continue
        # Migração: add_distance (legado) -> extra_distance.
        if 'extra_distance' not in point_data and 'add_distance' in point_data:
            point_data['extra_distance'] = point_data.pop('add_distance')
        if 'extra_distance' not in point_data:
            continue
        try:
            value = float(point_data['extra_distance'] or 0.0)
        except (TypeError, ValueError):
            value = 0.0
        canonical = get_canonical_name(point_name)
        if canonical not in pending:  # primeira ocorrência vence
            pending[canonical] = value
    return pending