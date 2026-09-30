"""Algoritmos de grafo para roteamento através de redes de equipamentos."""

from backend.core.logging.logger import get_logger

log = get_logger(__name__)


def filter_equipment_in_graph(equipamentos, G):
    """Mantém apenas equipamentos presentes no grafo, logando os removidos."""
    equipamentos_originais = len(equipamentos)
    equipamentos = [e for e in equipamentos if e in G.nodes]
    if equipamentos_originais != len(equipamentos):
        log.warning("Aviso: %s equipamentos foram filtrados por não existirem no grafo", equipamentos_originais - len(equipamentos))
    return equipamentos


def rota_gulosa(G, equipamentos, start_node):
    if start_node not in equipamentos:
        start_node = equipamentos[0]
    visitados = [start_node]
    nao_visitados = set(equipamentos)
    nao_visitados.remove(start_node)
    atual = start_node
    while nao_visitados:
        proximos = [(nbr, G[atual][nbr]['weight']) for nbr in G.neighbors(atual) if nbr in nao_visitados]
        if not proximos:
            break
        prox = min(proximos, key=lambda x: x[1])[0]
        visitados.append(prox)
        nao_visitados.remove(prox)
        atual = prox
    return visitados
