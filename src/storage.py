"""Persistencia: escritura atómica, staging en disco y upsert idempotente del reporte.

Es el único módulo que escribe archivos. El upsert es el corazón del requisito de
idempotencia: el reporte sólo crece, y las filas ya cargadas conservan su `updated_at`
original porque se descartan por completo antes de concatenar.
"""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from .config import (
    COLUMNAS_REPORTE,
    PREFIJO_STAGING,
    PROCESSED_DIR,
    REPORT_PATH,
    ZONA_HORARIA,
)


def escribir_csv_atomico(df: pd.DataFrame, destino: Path) -> Path:
    """Escribe un DataFrame a CSV de forma atómica: primero `.tmp` y luego rename.

    Así el archivo final nunca queda a medias si la ejecución se interrumpe.

    Input:
        df (pd.DataFrame): tabla a escribir.
        destino (Path): ruta final del CSV (su directorio se crea si falta).

    Output:
        Path: la misma ruta `destino`, ya con el archivo completo.
    """
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_name(destino.name + ".tmp")
    df.to_csv(tmp, index=False, encoding="utf-8")
    tmp.replace(destino)
    return destino


def ruta_staging(fecha: str) -> Path:
    """Devuelve la ruta del CSV de staging que corresponde a una fecha.

    Input:
        fecha (str): fecha en formato `YYYY-MM-DD`.

    Output:
        Path: `data/processed/resetuser_<fecha>.csv` (puede no existir todavía).
    """
    return PROCESSED_DIR / f"{PREFIJO_STAGING}{fecha}.csv"


def guardar_staging(df: pd.DataFrame, fecha: str) -> Path:
    """Persiste la tabla de staging de un día en `data/processed/`.

    Input:
        df (pd.DataFrame): tabla de staging producida por `transform.tabla_desde_log()`.
        fecha (str): fecha en formato `YYYY-MM-DD`.

    Output:
        Path: la ruta donde quedó escrito el CSV.
    """
    return escribir_csv_atomico(df, ruta_staging(fecha))


def cargar_reporte() -> pd.DataFrame:
    """Carga el reporte acumulado desde disco, o uno vacío si aún no existe.

    Todo se lee como `str` para que ids y timestamps no muten de tipo entre ejecuciones.

    Input:
        Ninguno. Lee `REPORT_PATH`.

    Output:
        pd.DataFrame: el reporte con las columnas `COLUMNAS_REPORTE` y sin valores `NaN`
        (los faltantes quedan como cadena vacía).
    """
    if REPORT_PATH.is_file():
        return pd.read_csv(REPORT_PATH, dtype=str).fillna("")
    return pd.DataFrame(columns=COLUMNAS_REPORTE, dtype=str)


def filas_nuevas(staging: pd.DataFrame, ids_conocidos: set[str]) -> pd.DataFrame:
    """Filtra de una tabla de staging las filas que todavía no están en el reporte.

    Separar este cálculo de la escritura es lo que permite que `--dry-run` informe qué
    pasaría sin tocar el disco.

    Input:
        staging (pd.DataFrame): tabla de staging de uno o varios días.
        ids_conocidos (set[str]): ids que ya existen en el reporte.

    Output:
        pd.DataFrame: subconjunto de `staging` cuyo `id` no aparece en `ids_conocidos`.
    """
    return staging[~staging["id"].isin(ids_conocidos)].copy()


def marca_de_tiempo(ahora: datetime | None = None) -> str:
    """Genera el valor de `updated_at` para los registros que se cargan en esta ejecución.

    Input:
        ahora (datetime | None): momento a usar; `None` toma la hora actual en
            `ZONA_HORARIA`. Parametrizado para poder hacer pruebas reproducibles.

    Output:
        str: marca de tiempo ISO-8601 con resolución de segundos y desplazamiento horario.
    """
    return (ahora or datetime.now(ZoneInfo(ZONA_HORARIA))).isoformat(timespec="seconds")


def upsert_reporte(
    staging: pd.DataFrame, ahora: datetime | None = None
) -> tuple[pd.DataFrame, int]:
    """Añade al reporte sólo las filas cuyo `id` aún no existe, y lo reescribe.

    Es el corazón de la idempotencia: las filas ya cargadas se descartan por completo, así
    que conservan su `updated_at` original y una reejecución no puede duplicar ni alterar
    datos. Sólo las filas nuevas reciben la marca de tiempo de esta ejecución.

    Input:
        staging (pd.DataFrame): tabla de staging de uno o varios días.
        ahora (datetime | None): marca de tiempo a usar como `updated_at`; `None` toma la
            hora actual en `ZONA_HORARIA`.

    Output:
        tuple[pd.DataFrame, int]: el reporte resultante y cuántas filas nuevas se añadieron.
        Si no hay filas nuevas devuelve `(reporte, 0)` y no toca el archivo.
    """
    reporte = cargar_reporte()
    nuevos = filas_nuevas(staging, set(reporte["id"]))
    if nuevos.empty:
        return reporte, 0

    nuevos["updated_at"] = marca_de_tiempo(ahora)
    final = pd.concat([reporte, nuevos[COLUMNAS_REPORTE]], ignore_index=True)
    final = (
        final[COLUMNAS_REPORTE].sort_values(["timestamp", "id"]).reset_index(drop=True)
    )
    escribir_csv_atomico(final, REPORT_PATH)
    return final, len(nuevos)
