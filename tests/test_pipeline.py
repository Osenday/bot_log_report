"""Pruebas del proceso completo: raw -> processed -> reporte.

Aquí se comprueba el requisito central de la tarea: que el proceso sea idempotente y que una
reejecución sólo añada los registros que faltan.
"""

import hashlib

import pandas as pd

from src import pipeline
from src.config import COLUMNAS_REPORTE, REPORT_PATH
from src.storage import cargar_reporte, ruta_staging

FECHA = "2026-01-01"

# El log de prueba tiene 13 operaciones: 12 reseteos y una de SAP que debe quedar fuera.
RESETEOS = 12


def hash_reporte() -> str:
    return hashlib.sha256(REPORT_PATH.read_bytes()).hexdigest()


def test_solo_se_reportan_los_reseteos_de_admanager():
    resultado = pipeline.ejecutar(fecha=FECHA)
    assert resultado.total_operaciones == RESETEOS
    assert resultado.total_nuevos == RESETEOS
    assert set(cargar_reporte()["sistema"]) == {"ADManager"}


def test_el_reporte_tiene_las_columnas_pedidas():
    pipeline.ejecutar(fecha=FECHA)
    assert list(cargar_reporte().columns) == COLUMNAS_REPORTE


def test_se_escribe_el_staging_intermedio():
    pipeline.ejecutar(fecha=FECHA)
    assert ruta_staging(FECHA).is_file()


def test_el_proceso_es_idempotente():
    pipeline.ejecutar(fecha=FECHA)
    antes = hash_reporte()

    segunda = pipeline.ejecutar(fecha=FECHA)

    assert segunda.total_nuevos == 0
    assert hash_reporte() == antes


def test_una_reejecucion_solo_agrega_los_registros_que_faltan():
    pipeline.ejecutar(fecha=FECHA)
    completo = cargar_reporte()

    # Simula una carga que se quedó incompleta: se pierden 4 registros.
    parcial = completo.iloc[:-4]
    parcial.to_csv(REPORT_PATH, index=False, encoding="utf-8")

    resultado = pipeline.ejecutar(fecha=FECHA)

    assert resultado.total_nuevos == 4
    recuperado = cargar_reporte()
    assert set(recuperado["id"]) == set(completo["id"])

    # Las filas que ya estaban conservan su updated_at original.
    previas = recuperado[recuperado["id"].isin(parcial["id"])]
    assert set(previas["updated_at"]) == set(parcial["updated_at"])


def test_los_ids_son_deterministas_entre_ejecuciones():
    pipeline.ejecutar(fecha=FECHA)
    primeros = sorted(cargar_reporte()["id"])

    REPORT_PATH.unlink()
    pipeline.ejecutar(fecha=FECHA)

    assert sorted(cargar_reporte()["id"]) == primeros


def test_dry_run_no_escribe_nada():
    resultado = pipeline.ejecutar(fecha=FECHA, dry_run=True)

    assert resultado.total_nuevos == RESETEOS
    assert not REPORT_PATH.exists()
    assert not ruta_staging(FECHA).exists()


def test_el_fixture_cubre_los_ocho_codigos_http():
    pipeline.ejecutar(fecha=FECHA)
    staging = pd.read_csv(ruta_staging(FECHA))

    assert set(staging["status_http"]) == {200, 202, 403, 404, 429, 500, 503, 504}
    assert (staging["resultado_final"] != "").all()


def test_las_tres_causas_del_403_quedan_identificadas():
    pipeline.ejecutar(fecha=FECHA)
    staging = pd.read_csv(ruta_staging(FECHA))
    mensajes = set(staging.loc[staging["status_http"] == 403, "resultado_final"])

    assert len(mensajes) == 3
    assert not any("rechazado por las validaciones" in m for m in mensajes)
