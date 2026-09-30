"""Contrato e adaptação para processar um único bay."""

from typing import Any

from backend.processing.constants import BayData


def process_single_bay(processor: Any, bay: BayData):
    """Processa um bay usando a API individual do processor.

    Centraliza o mapeamento do dicionário persistido para os argumentos de
    ``process_results``; as regras de planilha continuam no processor durante
    a migração incremental.
    """
    kwargs: dict[str, Any] = {}
    if 'point_aliases' in bay:
        kwargs['point_aliases'] = bay['point_aliases']
    if 'cable_data' in bay and bay['cable_data'] is not None:
        kwargs['cable_data'] = bay['cable_data']
    return processor.process_results(
        bay['results'], bay['seccionadora_count'], bay['measurement_type'],
        bay['template_path'], bay['sincronizador_enabled'],
        bay.get('tc_phases', 1), bay.get('tp_phases', 1),
        bay.get('merging_unit_enabled', False), bay['name'],
        **kwargs,
    )


