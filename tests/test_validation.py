"""Pruebas de las validaciones de datos que corren dentro del proceso."""

import pytest

from src.transform import tabla_desde_log
from src.validation import (
    AVISO,
    ERROR,
    Hallazgo,
    ValidacionFallida,
    revisar,
    validar_log,
    validar_staging,
)

ENCABEZADO_VALIDO = (
    "2026-01-01T00:00:00.000000Z | INFO [operation_Id=abc123] | "
    "HTTP Request: http://apitools.ejemplo.com:8000/v3/users_admin/resetuser"
    '?sAMAccountName_requester=gerencia001&sAMAccountName_target=001000001 "HTTP/1.1" 200'
)


def escribir_log(tmp_path, contenido: str):
    """Guarda un log de prueba y devuelve su ruta."""
    ruta = tmp_path / "prueba.log"
    ruta.write_text(contenido, encoding="utf-8")
    return ruta


# --- contrato del log de entrada -----------------------------------------


def test_el_log_del_fixture_cumple_el_contrato(log_fixture):
    assert validar_log(log_fixture) == []


def test_log_vacio_es_error(tmp_path):
    hallazgos = validar_log(escribir_log(tmp_path, "\n \n"))
    assert [h.nivel for h in hallazgos] == [ERROR]


def test_log_sin_el_formato_esperado_es_error(tmp_path):
    hallazgos = validar_log(escribir_log(tmp_path, "esto no es un log\notra linea\n"))
    assert [h.nivel for h in hallazgos] == [ERROR]


def test_lineas_sueltas_antes_del_primer_encabezado(tmp_path):
    contenido = f"basura suelta\n{ENCABEZADO_VALIDO}\n"
    hallazgos = validar_log(escribir_log(tmp_path, contenido))
    assert any("sueltas" in h.mensaje for h in hallazgos)


def test_endpoint_desconocido_genera_aviso(tmp_path):
    linea = ENCABEZADO_VALIDO.replace("users_admin/resetuser", "servicio_nuevo/accion")
    hallazgos = validar_log(escribir_log(tmp_path, linea + "\n"))
    assert any("no reconocidos" in h.mensaje for h in hallazgos)


def test_respuesta_truncada_de_admanager_genera_aviso(tmp_path):
    truncado = (
        f"{ENCABEZADO_VALIDO}\n"
        "2026-01-01T00:00:01.000000Z | INFO [operation_Id=abc123] | "
        "ADManagerRawClient.get_users_list_info_from_admanager invoked\n"
        "Params to execute POST to SearchUser: {'domainName': 'ejemplo.com', "
        "'filter': '(sAMAccountName:equal:gerencia001)'}, Raw Response: \n"
        "\n"
        ", Raw status_code: 200, Raw reason_phrase: \n"
    )
    hallazgos = validar_log(escribir_log(tmp_path, truncado))
    assert any("truncadas" in h.mensaje for h in hallazgos)


# --- invariantes de la tabla de salida -----------------------------------


def test_el_staging_del_fixture_cumple_las_invariantes(log_fixture):
    assert validar_staging(tabla_desde_log(log_fixture), "2026-01-01") == []


def test_un_log_sin_resetuser_avisa(log_fixture):
    vacio = tabla_desde_log(log_fixture).iloc[0:0]
    hallazgos = validar_staging(vacio, "2026-01-01")
    assert [h.nivel for h in hallazgos] == [AVISO]


def test_ids_repetidos_son_error(log_fixture):
    staging = tabla_desde_log(log_fixture)
    duplicado = staging.iloc[[0, 0]]
    hallazgos = validar_staging(duplicado, "2026-01-01")
    assert any(h.nivel == ERROR and "repetidos" in h.mensaje for h in hallazgos)


def test_un_codigo_http_desconocido_avisa(log_fixture):
    staging = tabla_desde_log(log_fixture).copy()
    staging.loc[0, "status_http"] = 418
    hallazgos = validar_staging(staging, "2026-01-01")
    assert any("sin regla definida" in h.mensaje for h in hallazgos)


# --- decisión de continuar o detenerse -----------------------------------


def test_los_avisos_no_detienen_el_proceso():
    revisar([Hallazgo(AVISO, "algo menor")], strict=False)


def test_en_modo_strict_un_aviso_detiene_el_proceso():
    with pytest.raises(ValidacionFallida):
        revisar([Hallazgo(AVISO, "algo menor")], strict=True)


def test_un_error_siempre_detiene_el_proceso():
    with pytest.raises(ValidacionFallida):
        revisar([Hallazgo(ERROR, "algo grave")], strict=False)


def test_sin_hallazgos_no_pasa_nada():
    revisar([], strict=True)
