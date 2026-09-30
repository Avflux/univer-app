"""Gerenciamento de cache e resolução de formações de cabos."""

from typing import Any, Dict, List, Set, Tuple

from backend.core.logging.logger import get_logger
from backend.core.utils.point_utils import get_canonical_name

log = get_logger(__name__)


class CableResolver:
    """Gerencia cache de formações de cabos e integração com a calculadora interna.
    
    Responsabilidades:
    - Manter cache de formações de cabos já resolvidas
    - Gerar chaves únicas para cache baseadas em origem/destino/bay
    - Sincronizar cache com resultados da calculadora de cabos ou cable_data do .md
    - Resolver valores de cabo com ou sem asterisco (expansão automática / duplicatas)
    
    Attributes:
        cable_calculator: Calculadora de cabos interna (ex.: ``HeadlessCableCalculator``).
        formations_cache: Cache {chave: lista_de_formações} para evitar
            reprocessamento.
    """
    
    def __init__(self, cable_calculator):
        """Inicializa o resolvedor de cabos.
        
        Args:
            cable_calculator: Calculadora de cabos interna (sem UI).
        """
        self.cable_calculator = cable_calculator
        self.formations_cache: Dict[str, List[str]] = {}
        self._custom_cable_groups: Dict[Tuple[str, str, str, str], List[str]] = {}
        self._bay_has_cable_data: Set[str] = set()
    
    def clear_cache(self):
        """Limpa o cache de formações (usado ao iniciar novo bay)."""
        self.formations_cache = {}
        self._custom_cable_groups = {}
        self._bay_has_cable_data = set()
    
    def load_bay_cable_data(self, bay_name: str, cable_data: List[Dict[str, Any]]) -> None:
        """Carrega a lista de cabos definida no cable_data do bay (.md).

        Permite que múltiplos cabos para a mesma conexão (mesmo id ou duplicados via '+')
        sejam mapeados e escritos como linhas individuais na planilha final.

        Os nomes dos pontos são normalizados para nomes canônicos (via
        ``get_canonical_name``) para garantir correspondência com as
        colunas D/E do template, mesmo quando o usuário renomeou pontos.
        """
        if not cable_data:
            return
        bay = bay_name or ""
        self._bay_has_cable_data.add(bay)
        for cable in cable_data:
            if not isinstance(cable, dict):
                continue
            nova_bitola = str(cable.get("bitola") or cable.get("novaBitola") or "")
            funcao = str(cable.get("funcao") or "").strip()
            origem = str(cable.get("origin") or cable.get("origem") or "").strip()
            destino = str(cable.get("destination") or cable.get("destino") or "").strip()
            # Normaliza nomes para canônicos (PAINEL, DISJUNTOR, etc.)
            # para bater com os nomes usados nas colunas D/E do template.
            origem_canon = get_canonical_name(origem)
            destino_canon = get_canonical_name(destino)
            points = sorted([origem_canon, destino_canon])
            key = (funcao, points[0], points[1], bay)
            if key not in self._custom_cable_groups:
                self._custom_cable_groups[key] = []
            self._custom_cable_groups[key].append(nova_bitola)

    def get_formation_key(self, original_value, description, origin, destination, bay_name=None):
        """Gera chave única para cache de formação de cabo.
        
        A chave garante que dois cabos com mesma formação mas origens/destinos
        diferentes (ou bays diferentes) tenham entradas separadas no cache.
        Os pontos são ordenados para normalização (TC1->DJ1 = DJ1->TC1).
        
        Args:
            original_value: Valor original da célula B (formação do template).
            description: Descrição/função do cabo (célula C).
            origin: Ponto de origem.
            destination: Ponto de destino.
            bay_name: Nome do bay (opcional, usa current_bay do calculator se None).
            
        Returns:
            String no formato "valor|desc|ponto1|ponto2|bay".
        """
        origin = origin or ""
        destination = destination or ""
        points = sorted([origin, destination])
        bay = bay_name or getattr(self.cable_calculator, 'current_bay', "") or ""
        return f"{original_value}|{description}|{points[0]}|{points[1]}|{bay}"
    
    def sync_cache_with_calculator(self):
        """Sincroniza cache local com os resultados da calculadora de cabos.
        
        Copia entradas de `table_results` e `response_cache` da calculadora
        para o cache local, evitando reprocessamento de valores já calculados.
        """
        log.debug("Sincronizando cache com valores mais recentes da calculadora de cabos...")
        
        if hasattr(self.cable_calculator, 'table_results') and self.cable_calculator.table_results:
            for key, values in self.cable_calculator.table_results.items():
                if values:
                    log.debug("Sincronizando cache para chave %s: %s", key, values)
                    self.formations_cache[key] = values
        
        if hasattr(self.cable_calculator, 'response_cache'):
            for key, values in self.cable_calculator.response_cache.items():
                if values and key not in self.formations_cache:
                    log.debug("Sincronizando cache para chave %s: %s", key, values)
                    self.formations_cache[key] = values
    
    def process_cable_value(self, original_value, has_asterisk, description, sheet_name, 
                           origin, destination, bay_name=None):
        """Resolve o valor de cabo (com expansão automática / duplicatas de cable_data)."""
        origin = origin or ""
        destination = destination or ""
        # Normaliza nomes para canônicos para bater com as chaves
        # geradas por load_bay_cable_data (que também normaliza).
        origin_canon = get_canonical_name(origin)
        destination_canon = get_canonical_name(destination)
        points = sorted([origin_canon, destination_canon])
        bay = bay_name or getattr(self.cable_calculator, 'current_bay', "") or ""
        desc = str(description or "").strip()
        custom_key = (desc, points[0], points[1], bay)

        # Se o bay possui cable_data configurado:
        if bay in self._bay_has_cable_data:
            if custom_key in self._custom_cable_groups:
                return self._custom_cable_groups[custom_key]
            # Linha com asterisco sem correspondência no cable_data:
            # usa o valor original do template como fallback ao invés de
            # retornar [] (que causaria linha vazia na planilha).
            return [original_value]

        cache_key = self.get_formation_key(original_value, description, origin, destination, bay_name)
        
        # Processamento com asterisco (expansão automática)
        if has_asterisk and original_value:
            values = self.cable_calculator.process_cable_value(
                original_value, has_asterisk, description, sheet_name, origin, destination, bay_name
            )
            self.formations_cache[cache_key] = values
            return values
        
        # Cache local
        if cache_key in self.formations_cache:
            return self.formations_cache[cache_key]
        
        # Cache da calculadora (table_results)
        if hasattr(self.cable_calculator, 'table_results') and self.cable_calculator.table_results:
            if cache_key in self.cable_calculator.table_results:
                values = self.cable_calculator.table_results[cache_key]
                self.formations_cache[cache_key] = values
                return values
        
        # Cache da calculadora (response_cache)
        if hasattr(self.cable_calculator, 'response_cache') and cache_key in self.cable_calculator.response_cache:
            custom_values = self.cable_calculator.response_cache[cache_key]
            self.formations_cache[cache_key] = custom_values
            return custom_values
        
        # Fallback: retorna valor original
        return [original_value]
    
    def resolve_tc_tp_cable_value(self, cell_b, cell_c, cell_d, cell_e, sheet_title, has_asterisk, bay_name):
        """Resolve formação para abas TC/TP (assinatura diferente de process_cable_value)."""
        return self.process_cable_value(
            cell_b, has_asterisk, cell_c, sheet_title, cell_d, cell_e, bay_name
        )

