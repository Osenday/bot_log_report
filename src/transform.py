"""Construcción de la tabla de staging a partir de un `.log`.

Produce la capa `data/processed/`: una fila por operación `resetuser`. Es **determinista**
por diseño — no contiene `updated_at` ni ningún valor derivado del reloj —, así que
regenerarla con el mismo log de entrada produce siempre el mismo resultado byte a byte.
"""

import uuid
from collections.abc import Iterator
from pathlib import Path

import pandas as pd

from .config import ACCION, COLUMNAS_STAGING, SISTEMA, UUID_NAMESPACE
from .enrich import OperacionReset, enriquecer
from .outcomes import resolver_resultado
from .reader import agrupar_operaciones


def operaciones_reset(path: Path) -> Iterator[OperacionReset]:
    """Recorre un `.log` y emite sólo sus operaciones de reseteo de ADManager.

    Input:
        path (Path): ruta al archivo `.log` crudo.

    Output:
        Iterator[OperacionReset]: una operación resuelta por cada `users_admin/resetuser`
        del archivo; el resto (por ejemplo `sap/register_user`) se descarta.
    """
    for operacion in agrupar_operaciones(path).values():
        op = enriquecer(operacion)
        if op is not None:
            yield op


def operacion_a_fila(op: OperacionReset) -> dict:
    """Convierte una `OperacionReset` en la fila de staging correspondiente.

    El `id` se calcula como `uuid5(UUID_NAMESPACE, operation_id)`: un UUID válido, único por
    registro y determinista (a diferencia de `uuid4`), que es lo que hace posible el upsert
    idempotente. La fila no lleva `updated_at`, porque el staging no depende del reloj.

    Input:
        op (OperacionReset): operación resuelta.

    Output:
        dict: una fila con las claves de `COLUMNAS_STAGING` (incluido `status_http`).
    """
    return {
        "id": str(uuid.uuid5(UUID_NAMESPACE, op.operation_id)),
        "timestamp": op.timestamp,
        "operation_id": op.operation_id,
        "solicitante": op.solicitante.sam,
        "target": op.target.sam,
        "accion": ACCION,
        "sistema": SISTEMA,
        "nombre_solicitante": op.solicitante.nombre_completo,
        "nombre_target": op.target.nombre_completo,
        "oficina_solicitante": op.solicitante.oficina,
        "oficina_target": op.target.oficina,
        "resultado_final": resolver_resultado(op),
        "status_http": op.status,
    }


def tabla_desde_log(path: Path) -> pd.DataFrame:
    """Procesa un `.log` completo y devuelve su tabla de staging.

    Determinista: mismo log de entrada, mismo DataFrame de salida, byte por byte.

    Input:
        path (Path): ruta al archivo `.log` crudo.

    Output:
        pd.DataFrame: una fila por operación `resetuser`, con las columnas
        `COLUMNAS_STAGING` y ordenada por (`timestamp`, `operation_id`).
    """
    filas = [operacion_a_fila(op) for op in operaciones_reset(path)]
    df = pd.DataFrame(filas, columns=COLUMNAS_STAGING)
    return df.sort_values(["timestamp", "operation_id"]).reset_index(drop=True)
