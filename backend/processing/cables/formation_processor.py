"""Escrita de formações de cabos em linhas de planilhas."""

from typing import Callable, List, Tuple


class FormationProcessor:
    """Escreve as linhas expandidas de uma formação de cabo."""

    def __init__(self, write_row: Callable):
        self._write_row = write_row

    def write_formation_rows(
        self,
        sheet,
        values: List[str],
        tag,
        description,
        origin,
        destination,
        distance,
        valid_row: int,
        has_valid_data: bool,
    ) -> Tuple[int, bool]:
        """Escreve cada formação e retorna a próxima linha e o estado dos dados."""
        for index, value in enumerate(values):
            row = valid_row + index
            self._write_row(
                sheet,
                row,
                [tag, value, description, origin, destination, distance],
            )
            has_valid_data = True
        return valid_row + max(len(values), 1), has_valid_data


