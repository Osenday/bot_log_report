"""Interfaz de línea de comandos: argumentos, logging y resumen en pantalla.

Aísla del resto del proceso todo lo que tiene que ver con la terminal, para que `main.py`
quede reducido a orquestar y `pipeline.py` no sepa nada de `argparse`.
"""

import argparse
import logging

from .config import REPORT_PATH
from .pipeline import ResultadoEjecucion

DESCRIPCION = """
Actualiza la tabla `tabla_reporte_bot` a partir de los logs del bot, tomando en cuenta
únicamente los reseteos de usuarios de ADManager (users_admin/resetuser).

El proceso es idempotente: reejecutar un día ya cargado no duplica ni altera registros.
"""

EJEMPLOS = """
Ejemplos:
  python main.py                                     ejecución diaria (log más reciente)
  python main.py --date 2026-08-30                   reprocesa un día pasado
  python main.py --from 2026-08-29 --to 2026-08-31   recuperación de un rango
  python main.py --all                               carga inicial de todo el histórico
  python main.py --date 2026-08-30 --dry-run         informa sin escribir nada
  python main.py --strict                            no carga nada si hay algún aviso
"""


def construir_parser() -> argparse.ArgumentParser:
    """Define los argumentos que acepta el proceso en la terminal.

    Input:
        Ninguno.

    Output:
        argparse.ArgumentParser: parser configurado con las opciones de selección de fechas
        (`--date`, `--from`, `--to`, `--all`), `--dry-run` y el control de verbosidad.
    """
    parser = argparse.ArgumentParser(
        prog="main.py",
        description=DESCRIPCION,
        epilog=EJEMPLOS,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--date",
        metavar="YYYY-MM-DD",
        help="reprocesa una fecha concreta en lugar del log más reciente",
    )
    parser.add_argument(
        "--from",
        dest="desde",
        metavar="YYYY-MM-DD",
        help="inicio de un rango de fechas a reprocesar (inclusivo)",
    )
    parser.add_argument(
        "--to",
        dest="hasta",
        metavar="YYYY-MM-DD",
        help="fin de un rango de fechas a reprocesar (inclusivo)",
    )
    parser.add_argument(
        "--all",
        dest="todas",
        action="store_true",
        help="procesa todas las fechas disponibles en data/raw/",
    )
    parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="informa cuántos registros se añadirían, sin escribir en disco",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="detiene el proceso ante cualquier aviso de validación, no sólo los errores",
    )

    verbosidad = parser.add_mutually_exclusive_group()
    verbosidad.add_argument(
        "-v", "--verbose", action="store_true", help="muestra el detalle de cada paso"
    )
    verbosidad.add_argument(
        "-q", "--quiet", action="store_true", help="sólo muestra errores"
    )
    return parser


def configurar_logging(verbose: bool = False, quiet: bool = False) -> None:
    """Configura el logging del proceso según la verbosidad pedida.

    Input:
        verbose (bool): baja el nivel a DEBUG y añade el nombre del módulo al formato.
        quiet (bool): sube el nivel a ERROR.

    Output:
        None. Deja configurado el logger raíz.
    """
    if quiet:
        nivel = logging.ERROR
    elif verbose:
        nivel = logging.DEBUG
    else:
        nivel = logging.INFO

    formato = (
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
        if verbose
        else "%(asctime)s | %(levelname)-7s | %(message)s"
    )
    logging.basicConfig(level=nivel, format=formato, datefmt="%Y-%m-%d %H:%M:%S")


def imprimir_resumen(resultado: ResultadoEjecucion) -> None:
    """Imprime el resumen final de la ejecución en un formato legible.

    Input:
        resultado (ResultadoEjecucion): salida de `pipeline.ejecutar()`.

    Output:
        None. Escribe en la salida estándar.
    """
    etiqueta = " (simulación, no se escribió nada)" if resultado.dry_run else ""
    print(f"\nResumen de la ejecución{etiqueta}")
    print(f"{'fecha':<12} {'operaciones':>12} {'nuevos':>8}")
    print("-" * 34)
    for fila in resultado.fechas:
        print(f"{fila.fecha:<12} {fila.operaciones:>12} {fila.nuevos:>8}")
    print("-" * 34)
    print(
        f"{'total':<12} {resultado.total_operaciones:>12} {resultado.total_nuevos:>8}"
    )
    print(f"\nReporte: {REPORT_PATH} ({resultado.total_reporte} filas)")
