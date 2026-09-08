"""Descubrimiento de los archivos `.log` de entrada.

Resuelve qué día procesar: el más reciente en la ejecución diaria normal, o una fecha o
rango concretos cuando hay que reprocesar por una corrección. Es el único módulo que sabe
cómo se nombran los archivos crudos.
"""

from datetime import datetime
from pathlib import Path

from .config import FORMATO_FECHA, PATRON_LOG, RAW_DIR


def validar_fecha(texto: str) -> str:
    """Valida que una fecha venga en formato `YYYY-MM-DD` y la devuelve normalizada.

    Input:
        texto (str): fecha tal como la escribió el usuario en la terminal.

    Output:
        str: la fecha en formato `YYYY-MM-DD`.
        Lanza `ValueError` con un mensaje explícito si el formato no es válido.
    """
    try:
        return datetime.strptime(texto, FORMATO_FECHA).strftime(FORMATO_FECHA)
    except ValueError as exc:
        raise ValueError(
            f"Fecha inválida '{texto}': se esperaba el formato YYYY-MM-DD"
        ) from exc


def fechas_disponibles() -> list[str]:
    """Lista las fechas con log disponible, deducidas del nombre de cada archivo.

    `Path.stem` devuelve el nombre sin extensión, que en este proyecto es directamente la
    fecha (`2026-09-01.log` -> `2026-09-01`). El orden alfabético coincide con el
    cronológico gracias al formato ISO.

    Input:
        Ninguno. Lee `RAW_DIR` con el patrón `PATRON_LOG`.

    Output:
        list[str]: fechas `YYYY-MM-DD` ordenadas de más antigua a más reciente.
    """
    return sorted(p.stem for p in RAW_DIR.glob(PATRON_LOG))


def ruta_log(fecha: str) -> Path:
    """Devuelve la ruta del `.log` crudo de una fecha concreta, validando que exista.

    Input:
        fecha (str): fecha en formato `YYYY-MM-DD`.

    Output:
        Path: ruta a `data/raw/<fecha>.log`.
        Lanza `FileNotFoundError` (con la lista de fechas disponibles) si no existe.
    """
    ruta = RAW_DIR / f"{fecha}.log"
    if not ruta.is_file():
        disponibles = ", ".join(fechas_disponibles()) or "ninguna"
        raise FileNotFoundError(
            f"No existe el log de {fecha}. Fechas disponibles: {disponibles}"
        )
    return ruta


def fecha_mas_reciente() -> str:
    """Devuelve la última fecha disponible: la entrada de la ejecución diaria normal.

    Input:
        Ninguno. Se apoya en `fechas_disponibles()`.

    Output:
        str: fecha `YYYY-MM-DD` del log más reciente.
        Lanza `FileNotFoundError` si no hay ningún `.log` en `RAW_DIR`.
    """
    fechas = fechas_disponibles()
    if not fechas:
        raise FileNotFoundError(f"No hay archivos {PATRON_LOG} en {RAW_DIR}")
    return fechas[-1]


def fechas_en_rango(desde: str | None = None, hasta: str | None = None) -> list[str]:
    """Lista las fechas disponibles dentro de un rango cerrado `[desde, hasta]`.

    Los extremos son opcionales: sin `desde` empieza en la primera fecha disponible y sin
    `hasta` termina en la última. La comparación es alfabética, que en formato ISO equivale
    a la cronológica.

    Input:
        desde (str | None): límite inferior `YYYY-MM-DD`, inclusivo.
        hasta (str | None): límite superior `YYYY-MM-DD`, inclusivo.

    Output:
        list[str]: fechas disponibles dentro del rango, en orden cronológico.
        Lanza `ValueError` si el rango está invertido y `FileNotFoundError` si ningún log
        cae dentro.
    """
    disponibles = fechas_disponibles()
    if not disponibles:
        raise FileNotFoundError(f"No hay archivos {PATRON_LOG} en {RAW_DIR}")

    inicio = validar_fecha(desde) if desde else disponibles[0]
    fin = validar_fecha(hasta) if hasta else disponibles[-1]
    if inicio > fin:
        raise ValueError(f"Rango invertido: --from {inicio} es posterior a --to {fin}")

    fechas = [f for f in disponibles if inicio <= f <= fin]
    if not fechas:
        raise FileNotFoundError(
            f"No hay logs entre {inicio} y {fin}. "
            f"Fechas disponibles: {', '.join(disponibles)}"
        )
    return fechas
