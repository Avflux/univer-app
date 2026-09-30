"""Excel workbook geração de relatórios de listas de cabos."""

from typing import Any, Dict, List, Optional, Set, Tuple

from openpyxl.workbook.workbook import Workbook
from openpyxl.worksheet.worksheet import Worksheet

from backend.core.logging.logger import get_logger
from backend.processing.constants import (DATA_COLUMNS,
                                    MEASUREMENT_COSTURA,
                                    BayData, Connection, DistanceMap)
from backend.processing.workflow.graph_utils import filter_equipment_in_graph
from backend.processing.workbook.sheet_styles import (CENTER_ALIGNMENT, HEADER_FILL, HEADER_FONT, THIN_BORDER)
from backend.processing.cables.cable_resolver import CableResolver
from backend.processing.cables.formation_processor import FormationProcessor
from backend.processing.workbook.distance_manager import DistanceManager
from backend.processing.workbook.sheet_builder import SheetBuilder, finalize_sheet
from backend.processing.workbook.cable_totals import aggregate_cable_totals
from backend.processing.workbook.fallback_workbook import create_new_workbook
from backend.processing.workflow.multi_bay_finalizer import (
    append_total_geral_sheet,
    prepare_multi_bay_workbook,
)
from backend.processing.workflow.multi_bay_processor import process_bays
from backend.processing.workflow.single_bay_processor import process_single_bay
from backend.processing.workflow.sheet_routing import redirect_merging_unit
from backend.processing.workflow.tc_tp_processor import parse_winding_number, process_tc_tp_sheet
from backend.processing.workflow.seccionadora_processor import (
    has_other_seccionadora_connections,
    resolve_seccionadora_refs,
)
from backend.processing.workflow.costura_processor import (
    classify_template_rows,
    equipment_from_rows,
    find_matching_row,
    process_costura_sheet,
    process_motores_equipments,
    write_route_pairs,
)
from backend.processing.workflow.caixa_ca_processor import (
    process_caixa_ca_sheet,
    process_caixa_equipment_row,
    process_caixa_seccionadora_row,
)
from backend.processing.workflow.sheet_processor import process_sheet
from backend.processing.workflow.results_processor import (
    create_summary_sheet as create_summary_sheet_flow,
    process_results as process_results_flow,
)
from backend.processing.workbook.total_geral_formatter import is_shielded, standardize_formation

log = get_logger(__name__)


class HeadlessCableCalculator:
    """Calculadora de cabos interna (sem UI). Mantém a formação como está (sem expansão automática)."""

    def __init__(self) -> None:
        self.current_bay = ""
        self.bay_aliases: dict[str, str] = {}
        self.table_results: dict[str, Any] = {}
        self.response_cache: dict[str, Any] = {}

    def process_cable_value(
        self, original_value, has_asterisk, description, sheet_name,
        origin, destination, bay_name=None,
    ) -> List[Any]:
        return [original_value]


class ExcelProcessor:
    def __init__(self):
        self.template_dir = "src/backend/Modules/Sheets"
        self.template_file = None
        self.cable_calculator = HeadlessCableCalculator()
        self.cable_resolver = CableResolver(self.cable_calculator)
        self.distance_manager = DistanceManager()
        self.sheet_builder = SheetBuilder(self._copy_headers)
        self.formation_processor = None

    def _ensure_formation_processor(self) -> None:
        if self.formation_processor is None:
            self.formation_processor = FormationProcessor(self._write_row)

    # --- Orquestração pública -------------------------------------------

    def process_results(self, results_data: List[Connection], seccionadora_count: int = 0,
                        measurement_type: str = MEASUREMENT_COSTURA, template_path: Optional[str] = None,
                        sincronizador_enabled: bool = True, tc_phases: int = 1, tp_phases: int = 1,
                        merging_unit_enabled: bool = False, bay_name: Optional[str] = None,
                        point_aliases: Optional[Dict[str, str]] = None,
                        cable_data: Optional[List[Dict[str, Any]]] = None) -> Workbook:
        """Compatibilidade delegada ao orquestrador ``process_results`` (results_processor)."""
        return process_results_flow(
            self, results_data, seccionadora_count, measurement_type, template_path,
            sincronizador_enabled, tc_phases, tp_phases, merging_unit_enabled, bay_name,
            point_aliases=point_aliases, cable_data=cable_data,
        )


    def process_multiple_bays(self, bay_data: List[BayData]) -> Workbook:
        final_wb, styles, per_bay_callback = prepare_multi_bay_workbook(bay_data)
        def process_bay(bay):
            log.info("==== Processando bay: %s ====", bay['name'])
            return process_single_bay(self, bay)
        process_bays(
            bay_data, sync_cache=self.cable_resolver.sync_cache_with_calculator,
            clear_cache=self.cable_resolver.clear_cache, process_bay=process_bay,
            get_formations=lambda: self.cable_resolver.formations_cache.copy(),
            aggregate_totals=aggregate_cable_totals,
            assemble_bay=lambda bay, wb: per_bay_callback(final_wb, bay),
            finalize=lambda bays: append_total_geral_sheet(final_wb, bays, styles, logger=log),
            reset_results=lambda: setattr(self.cable_calculator, 'table_results', {}),
        )
        return final_wb

    # --- Helpers de orquestração -----------------------------------------

    @staticmethod
    def _build_distance_dict(results_data: List[Connection]) -> DistanceMap:
        """Compatibilidade delegada ao DistanceManager."""
        return DistanceManager.build_distance_dict(results_data)

    @staticmethod
    def _copy_headers(template_sheet: Worksheet, new_sheet: Worksheet, columns: Tuple[str, ...] = DATA_COLUMNS) -> None:
        """Copia a linha de cabeçalho (linha 1) do template para a nova aba."""
        for col in columns:
            new_sheet[f'{col}1'].value = template_sheet[f'{col}1'].value

    def _write_row(self, sheet: Worksheet, row: int, values: List[object]) -> None:
        """Escreve valores nas colunas A-F aplicando aliases em D/E (Origem/Destino)."""
        values = list(values)
        if len(values) >= 5:
            values[3] = self.distance_manager.alias(values[3])
            values[4] = self.distance_manager.alias(values[4])
        for col, value in zip(DATA_COLUMNS, values):
            sheet[f'{col}{row}'].value = value

    def _write_formation_rows(self, new_sheet: Worksheet, new_b_values: List[str], tag: object,
                              description: object, origin: object, destination: object,
                              distance: object, valid_row: int, has_valid_data: bool) -> Tuple[int, bool]:
        """Compatibilidade interna delegada ao FormationProcessor."""
        self._ensure_formation_processor()
        return self.formation_processor.write_formation_rows(
            new_sheet, new_b_values, tag, description, origin, destination,
            distance, valid_row, has_valid_data,
        )

    @staticmethod
    def _resolve_distance(dist_dict: DistanceMap, origin: str, destination: str) -> Optional[float]:
        """Compatibilidade delegada ao DistanceManager."""
        return DistanceManager.resolve_distance(dist_dict, origin, destination)

    @staticmethod
    def _find_distance(results_data: List[Connection], origin: str, destination: str) -> Optional[float]:
        """Compatibilidade delegada ao DistanceManager."""
        return DistanceManager.find_distance(results_data, origin, destination)

    @staticmethod
    def _finalize_sheet(new_sheet: Worksheet, valid_row: int, has_valid_data: bool) -> bool:
        """Compatibilidade delegada a ``finalize_sheet`` (sheet_builder)."""
        return finalize_sheet(new_sheet, valid_row, has_valid_data)

    @staticmethod
    def _has_other_seccionadora_connections(template_sheet: Worksheet) -> bool:
        """Compatibilidade delegada a ``has_other_seccionadora_connections`` (seccionadora_processor)."""
        return has_other_seccionadora_connections(template_sheet)

    @staticmethod
    def _aggregate_cable_totals(workbook: Workbook) -> Dict[str, float]:
        """Compatibilidade delegada a ``aggregate_cable_totals``."""
        return aggregate_cable_totals(workbook)

    @staticmethod
    def _standardize_formation(cable_type: str) -> str:
        return standardize_formation(cable_type)

    @staticmethod
    def _is_shielded(cable_type: str) -> bool:
        return is_shielded(cable_type)

    # --- Aba COSTURA -------------------------------------------------------

    def _process_costura_sheet(self, template_sheet: Worksheet, new_sheet: Worksheet, results_data: List[Connection],
                               secc_number: Optional[int] = None, merging_unit_enabled: bool = False,
                               bay_name: Optional[str] = None) -> bool:
        """Compatibilidade delegada a ``process_costura_sheet`` (costura_processor)."""
        return process_costura_sheet(self, template_sheet, new_sheet, results_data,
                                     secc_number, merging_unit_enabled, bay_name)

    @staticmethod
    def _classify_template_rows(template_sheet: Worksheet, selected_equipment: Set[str]) -> Tuple[List[int], List[int], List[int]]:
        """Compatibilidade delegada a ``classify_template_rows`` (costura_processor)."""
        return classify_template_rows(template_sheet, selected_equipment)

    @staticmethod
    def _equipment_from_rows(template_sheet: Worksheet, rows: List[int]) -> List[str]:
        """Compatibilidade delegada a ``equipment_from_rows`` (costura_processor)."""
        return equipment_from_rows(template_sheet, rows)

    @staticmethod
    def _filter_equipment_in_graph(equipamentos: List[str], G) -> List[str]:
        """Compatibilidade delegada a ``filter_equipment_in_graph`` (graph_utils)."""
        return filter_equipment_in_graph(equipamentos, G)

    @staticmethod
    def _find_matching_row(source_rows: List[int], template_sheet: Worksheet, origem: str, destino: str) -> Optional[int]:
        """Compatibilidade delegada a ``find_matching_row`` (costura_processor)."""
        return find_matching_row(source_rows, template_sheet, origem, destino)

    def _write_route_pairs(self, template_sheet: Worksheet, new_sheet: Worksheet, source_rows: List[int],
                           rota: List[str], dist_dict: DistanceMap, valid_row: int, has_valid_data: bool,
                           pares_escritos: Set[Tuple[str, str]], bay_name: Optional[str]) -> Tuple[int, bool]:
        """Compatibilidade delegada a ``write_route_pairs`` (costura_processor)."""
        return write_route_pairs(self, template_sheet, new_sheet, source_rows, rota, dist_dict,
                                 valid_row, has_valid_data, pares_escritos, bay_name)

    def _process_motores_equipments(self, template_sheet: Worksheet, new_sheet: Worksheet, G,
                                    dist_dict: DistanceMap, linhas_motores: List[int], equipamentos: List[str],
                                    valid_row: int, has_valid_data: bool, pares_escritos_motores: Set[Tuple[str, str]],
                                    bay_name: Optional[str]) -> Tuple[int, bool]:
        """Compatibilidade delegada a ``process_motores_equipments`` (costura_processor)."""
        return process_motores_equipments(self, template_sheet, new_sheet, G, dist_dict, linhas_motores,
                                          equipamentos, valid_row, has_valid_data, pares_escritos_motores, bay_name)

    # --- Aba genérica -----------------------------------------------------

    def _process_sheet(self, template_sheet: Worksheet, new_sheet: Worksheet, results_data: List[Connection],
                       secc_number: Optional[int] = None, measurement_type: str = MEASUREMENT_COSTURA,
                       merging_unit_enabled: bool = False, bay_name: Optional[str] = None) -> bool:
        """Compatibilidade delegada a ``process_sheet`` (sheet_processor)."""
        return process_sheet(self, template_sheet, new_sheet, results_data, secc_number,
                             measurement_type, merging_unit_enabled, bay_name)

    @staticmethod
    def _resolve_seccionadora_refs(cell_d: Optional[str], cell_e: Optional[str],
                                   secc_number: Optional[int], sheet_title: str) -> Tuple[Optional[str], Optional[str]]:
        """Compatibilidade delegada a ``resolve_seccionadora_refs`` (seccionadora_processor)."""
        return resolve_seccionadora_refs(cell_d, cell_e, secc_number, sheet_title)

    @staticmethod
    def _redirect_merging_unit(cell_d: str, cell_e: str, original_b_value: object, sheet_title: str,
                               use_merging_unit: bool) -> Tuple[str, str]:
        """Compatibilidade delegada a ``redirect_merging_unit`` (sheet_routing)."""
        return redirect_merging_unit(cell_d, cell_e, original_b_value, sheet_title, use_merging_unit)

    # --- Aba CAIXA CA ------------------------------------------------------

    def _process_caixa_ca_sheet(self, template_sheet: Worksheet, new_sheet: Worksheet, results_data: List[Connection],
                                secc_number: Optional[int] = None, merging_unit_enabled: bool = False,
                                bay_name: Optional[str] = None) -> bool:
        """Compatibilidade delegada a ``process_caixa_ca_sheet`` (caixa_ca_processor)."""
        return process_caixa_ca_sheet(self, template_sheet, new_sheet, results_data,
                                      secc_number, merging_unit_enabled, bay_name)

    def _process_caixa_seccionadora_row(self, template_sheet: Worksheet, new_sheet: Worksheet, row: int,
                                        has_asterisk: bool, selected_equipment: Set[str], distances_dict: DistanceMap,
                                        seccionadora_count: int, valid_row: int, has_valid_data: bool,
                                        bay_name: Optional[str]) -> Tuple[int, bool]:
        """Compatibilidade delegada a ``process_caixa_seccionadora_row`` (caixa_ca_processor)."""
        return process_caixa_seccionadora_row(
            self, template_sheet, new_sheet, row, has_asterisk, selected_equipment,
            distances_dict, seccionadora_count, valid_row, has_valid_data, bay_name,
        )

    def _process_caixa_equipment_row(self, template_sheet: Worksheet, new_sheet: Worksheet, row: int,
                                     has_asterisk: bool, distances_dict: DistanceMap, cell_e: str,
                                     valid_row: int, has_valid_data: bool, bay_name: Optional[str]) -> Tuple[int, bool]:
        """Compatibilidade delegada a ``process_caixa_equipment_row`` (caixa_ca_processor)."""
        return process_caixa_equipment_row(
            self, template_sheet, new_sheet, row, has_asterisk, distances_dict,
            cell_e, valid_row, has_valid_data, bay_name,
        )

    # --- Abas TC/TP --------------------------------------------------------

    @staticmethod
    def _parse_winding_number(cell_d: Optional[str], winding_prefix: str) -> Optional[int]:
        """Compatibilidade delegada a ``parse_winding_number`` (tc_tp_processor)."""
        return parse_winding_number(cell_d, winding_prefix)

    def _process_tc_tp_sheet(self, template_sheet: Worksheet, new_sheet: Worksheet, results_data: List[Connection],
                             equipment_type: str, num_phases: int, merging_unit_enabled: bool = False,
                             bay_name: Optional[str] = None) -> bool:
        """Compatibilidade delegada a ``process_tc_tp_sheet`` (tc_tp_processor)."""
        return process_tc_tp_sheet(self, template_sheet, new_sheet, results_data, equipment_type,
                                   num_phases, merging_unit_enabled, bay_name)

    # --- Fallback sem template ----------------------------------------------

    @staticmethod
    def _create_new_workbook(results_data: List[Connection]) -> Workbook:
        """Compatibilidade delegada a ``create_new_workbook`` (fallback_workbook)."""
        return create_new_workbook(results_data)

    # --- Abas de resumo ------------------------------------------------------

    @staticmethod
    def _summary_styles() -> Dict[str, object]:
        return {
            'HEADER_FONT': HEADER_FONT,
            'HEADER_FILL': HEADER_FILL,
            'THIN_BORDER': THIN_BORDER,
            'CENTER_ALIGNMENT': CENTER_ALIGNMENT,
        }

    def _create_summary_sheet(self, workbook: Workbook) -> None:
        """Compatibilidade delegada a ``create_summary_sheet`` (results_processor)."""
        create_summary_sheet_flow(self, workbook)

