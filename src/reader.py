"""Lectura de los `.log` crudos y agrupación por operación.

Punto crítico del proceso: un registro del log NO equivale a una línea del archivo. Los
bloques `Raw Response: {...}` continúan en líneas sin encabezado, así que un lector línea a
línea perdería justo la información de ADManager que necesita el reporte.

Este módulo sólo reconstruye estructura; no interpreta el contenido de los mensajes.
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

HEADER_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2}T[\d:.]+Z) \| "
    r"(?P<level>\w+) "
    r"\[operation_Id=(?P<operation_id>[0-9a-fA-F]+)\] \| "
    r"(?P<message>.*)$"
)


@dataclass
class LogRecord:
    """Un registro lógico del log: la línea con encabezado más sus continuaciones.

    Campos:
        timestamp (str): marca de tiempo ISO de la línea de encabezado.
        level (str): nivel de log (INFO, ERROR, ...).
        operation_id (str): identificador de la operación del bot.
        message (str): mensaje completo, ya con las líneas de continuación pegadas.
    """

    timestamp: str
    level: str
    operation_id: str
    message: str


@dataclass
class Operation:
    """Todos los registros que comparten un operation_Id, en orden de aparición."""

    operation_id: str
    records: list[LogRecord] = field(default_factory=list)

    @property
    def timestamp(self) -> str:
        """Marca de tiempo de la operación: la del primer registro que la abrió.

        Input:
            Ninguno (propiedad; usa `self.records`).

        Output:
            str: timestamp ISO del primer registro. Lanza `IndexError` si no hay registros.
        """
        return self.records[0].timestamp

    def messages(self) -> list[str]:
        """Devuelve los mensajes de la operación en orden de aparición.

        Es la vista que consumen los parsers, que sólo necesitan el texto.

        Input:
            Ninguno (usa `self.records`).

        Output:
            list[str]: un mensaje por registro lógico.
        """
        return [r.message for r in self.records]

    @property
    def texto_crudo(self) -> str:
        """Reconstruye el texto original de la operación tal como aparece en el `.log`.

        Se usa para inspección manual al depurar un caso concreto.

        Input:
            Ninguno (propiedad; usa `self.records`).

        Output:
            str: los registros concatenados con su encabezado (timestamp, nivel,
            operation_Id).
        """
        return "".join(
            f"{r.timestamp} | {r.level} [operation_Id={r.operation_id}] | {r.message}"
            for r in self.records
        )


def iter_log_records(path: Path) -> Iterator[LogRecord]:
    """Convierte las líneas físicas de un `.log` en registros lógicos multilínea.

    Una línea que hace match con `HEADER_RE` abre un registro nuevo; cualquier otra se
    acumula en el registro abierto. Es un generador para no cargar el archivo completo en
    memoria.

    Input:
        path (Path): ruta al archivo `.log` crudo.

    Output:
        Iterator[LogRecord]: un `LogRecord` por registro lógico, en orden de aparición.
    """
    actual: LogRecord | None = None
    buffer: list[str] = []
    with path.open(encoding="utf-8") as fh:
        for linea in fh:
            m = HEADER_RE.match(linea)
            if m:
                if actual is not None:
                    actual.message = "".join(buffer)
                    yield actual
                actual = LogRecord(m["timestamp"], m["level"], m["operation_id"], "")
                buffer = [m["message"] + "\n"]
            elif actual is not None:
                buffer.append(linea)
    if actual is not None:
        actual.message = "".join(buffer)
        yield actual


def agrupar_operaciones(path: Path) -> dict[str, Operation]:
    """Agrupa los registros de un `.log` por `operation_Id`.

    Cada operación del bot genera varias líneas (entrada, consultas a ADManager, respuesta);
    agruparlas es lo que permite resolver una fila del reporte con todo su contexto. Las
    operaciones pueden no ser consecutivas si se procesan varias al mismo tiempo.

    Input:
        path (Path): ruta al archivo `.log` crudo.

    Output:
        dict[str, Operation]: `operation_id` -> `Operation` con sus registros en orden.
    """
    operaciones: dict[str, Operation] = {}
    for rec in iter_log_records(path):
        operaciones.setdefault(
            rec.operation_id, Operation(rec.operation_id)
        ).records.append(rec)
    return operaciones
