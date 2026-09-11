"""Orquestación del proceso completo: raw -> processed -> reporte.

Es el único módulo que conoce el orden de los pasos. Todo lo demás son piezas que él
compone, de modo que cambiar el flujo (añadir una capa, reordenar) se hace aquí y no se
esparce por el resto del código.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .config import SELECCION_POR_DEFECTO
from .discovery import fecha_mas_reciente, fechas_en_rango, ruta_log, validar_fecha
from .storage import cargar_reporte, filas_nuevas, guardar_staging, upsert_reporte
from .transform import endpoints_de, tabla_desde_log
from .validation import revisar, validar_log, validar_staging

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResultadoFecha:
    """Lo que ocurrió al procesar el log de un día.

    Campos:
        fecha (str): fecha procesada, `YYYY-MM-DD`.
        operaciones (int): operaciones de los endpoints pedidos encontradas en el log.
        nuevos (int): filas que se añadieron (o se añadirían) al reporte.
        staging (Path | None): ruta del CSV de staging escrito; `None` en `--dry-run`.
    """

    fecha: str
    operaciones: int
    nuevos: int
    staging: Path | None = None


@dataclass
class ResultadoEjecucion:
    """Resumen de una ejecución completa del proceso.

    Campos:
        fechas (list[ResultadoFecha]): detalle por día, en orden cronológico.
        total_reporte (int): filas que tiene (o tendría) el reporte al terminar.
        dry_run (bool): `True` si no se escribió nada en disco.
        seleccion (str): endpoints que se reportaron (`reset_user`, `register_user` o
            `todos`).
    """

    fechas: list[ResultadoFecha] = field(default_factory=list)
    total_reporte: int = 0
    dry_run: bool = False
    seleccion: str = SELECCION_POR_DEFECTO

    @property
    def total_operaciones(self) -> int:
        """Operaciones leídas en todos los días procesados.

        Input:
            Ninguno (propiedad; agrega `self.fechas`).

        Output:
            int: suma de `operaciones` de cada día.
        """
        return sum(r.operaciones for r in self.fechas)

    @property
    def total_nuevos(self) -> int:
        """Registros nuevos añadidos al reporte en toda la ejecución.

        Input:
            Ninguno (propiedad; agrega `self.fechas`).

        Output:
            int: suma de `nuevos` de cada día.
        """
        return sum(r.nuevos for r in self.fechas)


def resolver_fechas(
    fecha: str | None = None,
    desde: str | None = None,
    hasta: str | None = None,
    todas: bool = False,
) -> list[str]:
    """Traduce las opciones de la terminal a la lista concreta de fechas a procesar.

    Las cuatro formas son excluyentes entre sí; sin ninguna, se toma el log más reciente,
    que es el comportamiento de la ejecución diaria normal.

    Input:
        fecha (str | None): una fecha concreta a reprocesar.
        desde (str | None): inicio de un rango, inclusivo.
        hasta (str | None): fin de un rango, inclusivo.
        todas (bool): procesar todas las fechas disponibles.

    Output:
        list[str]: fechas `YYYY-MM-DD` en orden cronológico.
        Lanza `ValueError` si se combinan opciones incompatibles y `FileNotFoundError` si
        no hay logs que procesar.
    """
    if fecha and (desde or hasta or todas):
        raise ValueError("--date no se puede combinar con --from, --to ni --all")
    if todas and (desde or hasta):
        raise ValueError("--all no se puede combinar con --from ni --to")

    if todas:
        return fechas_en_rango()
    if desde or hasta:
        return fechas_en_rango(desde, hasta)
    if fecha:
        fecha_valida = validar_fecha(fecha)
        ruta_log(fecha_valida)  # valida que el archivo exista antes de seguir
        return [fecha_valida]
    return [fecha_mas_reciente()]


def preparar_staging(
    fecha: str, strict: bool = False, seleccion: str = SELECCION_POR_DEFECTO
) -> pd.DataFrame:
    """Lee el log de un día, lo valida y construye su tabla de staging (sin escribirla).

    Las validaciones corren aquí, antes de cualquier escritura: primero el contrato del log
    de entrada y después las invariantes de la tabla resultante.

    Input:
        fecha (str): fecha en formato `YYYY-MM-DD`.
        strict (bool): si es `True`, cualquier aviso detiene el proceso.
        seleccion (str): `reset_user`, `register_user` o `todos`.

    Output:
        pd.DataFrame: tabla de staging del día.
        Lanza `ValidacionFallida` si los datos no permiten continuar.
    """
    path = ruta_log(fecha)
    revisar(validar_log(path), strict)
    staging = tabla_desde_log(path, seleccion)
    revisar(validar_staging(staging, fecha, seleccion), strict)
    return staging


def procesar_fecha(
    fecha: str, strict: bool = False, seleccion: str = SELECCION_POR_DEFECTO
) -> ResultadoFecha:
    """Ejecuta el proceso completo de un día: valida, escribe staging y hace el upsert.

    Input:
        fecha (str): fecha en formato `YYYY-MM-DD`.
        strict (bool): si es `True`, cualquier aviso de validación detiene el proceso.
        seleccion (str): `reset_user`, `register_user` o `todos`.

    Output:
        ResultadoFecha: operaciones leídas, registros nuevos y ruta del staging escrito.
    """
    staging = preparar_staging(fecha, strict, seleccion)
    destino = guardar_staging(staging, fecha, seleccion)
    _, nuevos = upsert_reporte(staging)
    logger.info(
        "%s: %d operaciones de %s, %d registros nuevos",
        fecha,
        len(staging),
        seleccion,
        nuevos,
    )
    return ResultadoFecha(fecha, len(staging), nuevos, destino)


def simular_fecha(
    fecha: str,
    ids_conocidos: set[str],
    strict: bool = False,
    seleccion: str = SELECCION_POR_DEFECTO,
) -> ResultadoFecha:
    """Calcula qué añadiría el proceso para un día, sin escribir nada en disco.

    `ids_conocidos` se va acumulando entre días para que la simulación de un rango no cuente
    dos veces un mismo registro. Las validaciones también corren aquí, así que `--dry-run`
    sirve para revisar un log antes de cargarlo.

    Input:
        fecha (str): fecha en formato `YYYY-MM-DD`.
        ids_conocidos (set[str]): ids ya presentes en el reporte o ya contados en esta
            simulación. **Se modifica in situ** con los ids nuevos de este día.
        strict (bool): si es `True`, cualquier aviso de validación detiene el proceso.
        seleccion (str): `reset_user`, `register_user` o `todos`.

    Output:
        ResultadoFecha: operaciones leídas y registros que se añadirían (`staging=None`).
    """
    staging = preparar_staging(fecha, strict, seleccion)
    nuevos = filas_nuevas(staging, ids_conocidos)
    ids_conocidos.update(nuevos["id"])
    logger.info(
        "%s: %d operaciones de %s, %d registros nuevos (simulado)",
        fecha,
        len(staging),
        seleccion,
        len(nuevos),
    )
    return ResultadoFecha(fecha, len(staging), len(nuevos))


def ejecutar(
    fecha: str | None = None,
    desde: str | None = None,
    hasta: str | None = None,
    todas: bool = False,
    dry_run: bool = False,
    strict: bool = False,
    seleccion: str = SELECCION_POR_DEFECTO,
) -> ResultadoEjecucion:
    """Punto de entrada del proceso: resuelve las fechas y las procesa en orden.

    Input:
        fecha (str | None): una fecha concreta a reprocesar.
        desde (str | None): inicio de un rango, inclusivo.
        hasta (str | None): fin de un rango, inclusivo.
        todas (bool): procesar todas las fechas disponibles.
        dry_run (bool): informar qué pasaría sin escribir nada en disco.
        strict (bool): si es `True`, cualquier aviso de validación detiene el proceso.
        seleccion (str): qué endpoints reportar: `reset_user`, `register_user` o `todos`.

    Output:
        ResultadoEjecucion: detalle por día y totales de la ejecución.
        Propaga `ValueError` y `FileNotFoundError` de la resolución de fechas, y
        `ValidacionFallida` si los datos no cumplen el contrato.
    """
    endpoints_de(seleccion)  # valida la selección antes de tocar ningún archivo
    fechas = resolver_fechas(fecha, desde, hasta, todas)
    logger.info("Fechas a procesar: %s", ", ".join(fechas))
    logger.info("Endpoints a reportar: %s", ", ".join(endpoints_de(seleccion)))

    resultado = ResultadoEjecucion(dry_run=dry_run, seleccion=seleccion)
    if dry_run:
        ids_conocidos = set(cargar_reporte()["id"])
        base = len(ids_conocidos)
        resultado.fechas = [
            simular_fecha(f, ids_conocidos, strict, seleccion) for f in fechas
        ]
        resultado.total_reporte = base + resultado.total_nuevos
    else:
        resultado.fechas = [procesar_fecha(f, strict, seleccion) for f in fechas]
        resultado.total_reporte = len(cargar_reporte())
    return resultado
