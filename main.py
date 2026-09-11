"""Punto de entrada del proceso diario de actualización de `tabla_reporte_bot`.

Este archivo sólo orquesta: interpreta los argumentos, lanza el proceso y presenta el
resultado. Toda la lógica vive en los módulos de `src/`.

Uso:
    python main.py                                     ejecución diaria (log más reciente)
    python main.py --endpoint register_user            reporta las altas de usuarios en SAP
    python main.py --endpoint todos                    reporta los dos servicios
    python main.py --date 2026-08-30                   reprocesa un día pasado
    python main.py --from 2026-08-29 --to 2026-08-31   recuperación de un rango
    python main.py --all                               carga inicial de todo el histórico
    python main.py --date 2026-08-30 --dry-run         informa sin escribir nada
    python main.py --strict                            no carga nada si hay algún aviso
"""

import sys

from src import pipeline
from src.cli import configurar_logging, construir_parser, imprimir_resumen
from src.validation import ValidacionFallida


def main(argv: list[str] | None = None) -> int:
    """Ejecuta el proceso completo de principio a fin.

    Input:
        argv (list[str] | None): argumentos de la terminal; `None` usa `sys.argv`.

    Output:
        int: código de salida del proceso. `0` si terminó bien, `1` si los argumentos o los
        archivos de entrada no eran válidos, `2` si los datos no pasaron las validaciones.
    """
    args = construir_parser().parse_args(argv)
    configurar_logging(verbose=args.verbose, quiet=args.quiet)

    try:
        resultado = pipeline.ejecutar(
            fecha=args.date,
            desde=args.desde,
            hasta=args.hasta,
            todas=args.todas,
            dry_run=args.dry_run,
            strict=args.strict,
            seleccion=args.seleccion,
        )
    except ValidacionFallida as exc:
        print(f"Validación fallida, no se escribió nada: {exc}", file=sys.stderr)
        return 2
    except (ValueError, FileNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    imprimir_resumen(resultado)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
