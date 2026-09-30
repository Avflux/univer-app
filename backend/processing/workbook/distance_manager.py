"""Gerenciamento de aliases de pontos e resolução de distâncias."""

import re

from backend.processing.constants import Connection, DistanceMap


class DistanceManager:
    """Gerencia aliases de pontos e resolução de distâncias entre equipamentos.

    Responsabilidades:
    - Manter mapeamento de nomes canônicos para aliases customizados
    - Resolver distâncias bidirecionais entre pares de pontos
    - Construir dicionários de distâncias a partir de dados de conexão

    Attributes:
        point_aliases: Dicionário {nome_canônico: nome_customizado} definido
            pelo usuário na aba DistCad, usado para exibição nas colunas D/E.
    """

    def __init__(self, point_aliases: dict[str, str] | None = None):
        """Inicializa o gerenciador de distâncias.

        Args:
            point_aliases: Mapeamento opcional de nomes canônicos para aliases
                customizados. Padrão é dicionário vazio.
        """
        self.point_aliases = point_aliases or {}

    def alias(self, name: object) -> object:
        """Resolve o alias customizado de um ponto (canônico -> custom).

        Aplicado apenas na escrita das colunas D/E do Excel. O cache de
        bitolas continua usando o nome canônico como chave.

        Args:
            name: Nome canônico do ponto ou None.

        Returns:
            Alias customizado se existir, ou o nome original.
        """
        if not name:
            return name
        text = str(name)
        direct_alias = self.point_aliases.get(text)
        if direct_alias:
            return direct_alias
        match = re.fullmatch(r"SECCIONADORA-(\d+)", text)
        if match:
            base_alias = self.point_aliases.get("SECCIONADORA")
            if base_alias:
                return f"{base_alias}-{match.group(1)}"
        return name

    @staticmethod
    def resolve_distance(
        dist_dict: DistanceMap, origin: str, destination: str
    ) -> float | None:
        """Busca a distância em qualquer direção (origem->destino ou destino->origem).

        Args:
            dist_dict: Dicionário bidirecional {(ponto_a, ponto_b): distância}.
            origin: Nome do ponto de origem.
            destination: Nome do ponto de destino.

        Returns:
            Distância entre os pontos, ou None se não encontrada.
        """
        direct_key = (origin, destination)
        reverse_key = (destination, origin)
        if direct_key in dist_dict:
            return dist_dict[direct_key]
        return dist_dict.get(reverse_key)

    @staticmethod
    def find_distance(
        results_data: list[Connection], origin: str, destination: str
    ) -> float | None:
        """Procura a distância da conexão em results_data, em qualquer direção.

        Nota: os valores de distância em results_data são sempre floats
        (produtores usam fallback 0.0), então None significa apenas "não
        encontrado" — os chamadores tratam None/0 como linha inválida.

        Args:
            results_data: Lista de tuplas (origem, destino, distância).
            origin: Nome do ponto de origem.
            destination: Nome do ponto de destino.

        Returns:
            Distância entre os pontos, ou None se não encontrada.
        """
        for result_origin, result_dest, distance in results_data:
            if (origin == result_origin and destination == result_dest) or (
                origin == result_dest and destination == result_origin
            ):
                return distance
        return None

    @staticmethod
    def build_distance_dict(results_data: list[Connection]) -> DistanceMap:
        """Constrói dicionário bidirecional origem<->destino -> distância.

        Args:
            results_data: Lista de tuplas (origem, destino, distância).

        Returns:
            Dicionário com entradas para ambas as direções:
            {(origem, destino): dist, (destino, origem): dist}.
        """
        dist: DistanceMap = {}
        for o, d, v in results_data:
            dist[(o, d)] = v
            dist[(d, o)] = v
        return dist
