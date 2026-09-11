"""Construcción de la tabla de staging a partir de un `.log`.

Produce la capa `data/processed/`: una fila por operación de los endpoints que se hayan
pedido (`reset_user`, `register_user` o `todos`). Es **determinista** por diseño — no
contiene `updated_at` ni ningún valor derivado del reloj —, así que regenerarla con el mismo
log de entrada produce siempre el mismo resultado byte a byte.
"""

import uuid
from collections.abc import Iterator
from pathlib import Path

import pandas as pd

from .config import (
    ACCION,
    ACCIONES,
    COLUMNAS_STAGING,
    ENDPOINTS_POR_SELECCION,
    SELECCION_POR_DEFECTO,
    SISTEMA,
    SISTEMAS,
    UUID_NAMESPACE,
)
from .enrich import OperacionReset, enriquecer
from .outcomes import resolver_resultado
from .reader import agrupar_operaciones


def endpoints_de(seleccion: str = SELECCION_POR_DEFECTO) -> tuple[str, ...]:
    """Traduce la etiqueta que se pidió en la terminal a los endpoints que hay que leer.

    Input:
        seleccion (str): `reset_user`, `register_user` o `todos`.

    Output:
        tuple[str, ...]: endpoints correspondientes.
        Lanza `ValueError` si la etiqueta no es una de las tres.
    """
    if seleccion not in ENDPOINTS_POR_SELECCION:
        opciones = ", ".join(sorted(ENDPOINTS_POR_SELECCION))
        raise ValueError(
            f"Selección de endpoint desconocida: {seleccion} (use {opciones})"
        )
    return ENDPOINTS_POR_SELECCION[seleccion]


def operaciones_reset(
    path: Path, seleccion: str = SELECCION_POR_DEFECTO
) -> Iterator[OperacionReset]:
    """Recorre un `.log` y emite sólo las operaciones de los endpoints pedidos.

    Input:
        path (Path): ruta al archivo `.log` crudo.
        seleccion (str): `reset_user`, `register_user` o `todos`. Por omisión sólo los
            reseteos de ADManager, que es el comportamiento histórico del proceso.

    Output:
        Iterator[OperacionReset]: una operación resuelta por cada operación del archivo
        cuyo endpoint esté en la selección; el resto se descarta.
    """
    endpoints = endpoints_de(seleccion)
    for operacion in agrupar_operaciones(path).values():
        op = enriquecer(operacion, endpoints)
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
        "accion": ACCIONES.get(op.endpoint, ACCION),
        "sistema": SISTEMAS.get(op.endpoint, SISTEMA),
        "nombre_solicitante": op.solicitante.nombre_completo,
        "nombre_target": op.target.nombre_completo,
        "oficina_solicitante": op.solicitante.oficina,
        "oficina_target": op.target.oficina,
        "resultado_final": resolver_resultado(op),
        "status_http": op.status,
    }


def tabla_desde_log(path: Path, seleccion: str = SELECCION_POR_DEFECTO) -> pd.DataFrame:
    """Procesa un `.log` completo y devuelve su tabla de staging.

    Determinista: mismo log de entrada y misma selección, mismo DataFrame de salida, byte
    por byte.

    Input:
        path (Path): ruta al archivo `.log` crudo.
        seleccion (str): `reset_user`, `register_user` o `todos`.

    Output:
        pd.DataFrame: una fila por operación de los endpoints pedidos, con las columnas
        `COLUMNAS_STAGING` y ordenada por (`timestamp`, `operation_id`).
    """
    filas = [operacion_a_fila(op) for op in operaciones_reset(path, seleccion)]
    df = pd.DataFrame(filas, columns=COLUMNAS_STAGING)
    return df.sort_values(["timestamp", "operation_id"]).reset_index(drop=True)
