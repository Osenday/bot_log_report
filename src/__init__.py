"""Proceso de actualización de la tabla `tabla_reporte_bot` a partir de los logs del bot.

Arquitectura de tres capas:

    data/raw/<fecha>.log
            |  parseo determinista (sin reloj, sin estado)
    data/processed/resetuser_<fecha>.csv          -> staging
            |  upsert idempotente por `id`
    reports/tabla_reporte_bot.csv                 -> tabla final

Módulos, en orden de dependencia (cada uno sólo importa de los anteriores):

    config      constantes de negocio, rutas y esquema de salida
    normalize   normalización de texto y comparaciones de negocio
    discovery   qué archivo `.log` procesar
    reader      líneas físicas -> registros lógicos -> operaciones
    parsers     expresiones regulares; no conoce reglas de negocio
    enrich      operación cruda -> usuarios resueltos; aplica el filtro de endpoint
    outcomes    código HTTP -> mensaje legible; no conoce expresiones regulares
    transform   operaciones -> tabla de staging
    storage     escritura atómica y upsert idempotente
    validation  contrato del log de entrada e invariantes de la tabla de salida
    pipeline    orquestación; el único que conoce el orden de los pasos
    cli         argumentos, logging y resumen en pantalla

El punto de entrada es `main.py`, en la raíz del proyecto.
"""

from . import (
    cli,
    config,
    discovery,
    enrich,
    normalize,
    outcomes,
    parsers,
    pipeline,
    reader,
    storage,
    transform,
    validation,
)

__all__ = [
    "cli",
    "config",
    "discovery",
    "enrich",
    "normalize",
    "outcomes",
    "parsers",
    "pipeline",
    "reader",
    "storage",
    "transform",
    "validation",
]
