"""Funções utilitárias para formatação de pontos e coordenadas.

Extraído de ui.py para separar lógica de formatação de dados da interface.
"""

PAINEL_ALIAS_POINTS = ('CASA DE COMANDO', 'CABANA')


def get_canonical_name(point_name):
    """Retorna o nome canônico do ponto, aplicando o alias PAINEL.

    'CASA DE COMANDO' e 'CABANA' retornam 'PAINEL'; demais pontos retornam o próprio nome.
    """
    return 'PAINEL' if point_name in PAINEL_ALIAS_POINTS else point_name
