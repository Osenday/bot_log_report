"""Pruebas del alta de usuarios en SAP (`sap/register_user`).

Cubren las tres piezas que añadió el endpoint: la lectura de sus parámetros, sus reglas de
negocio (que reutilizan los códigos HTTP con otro significado) y la selección de qué
servicio entra en el reporte.

Los mensajes se comprueban por fragmentos y no por igualdad exacta, para que un ajuste de
redacción no rompa la prueba de la regla.
"""

import pandas as pd
import pytest

from src import pipeline
from src.config import ENDPOINT_REGISTER, ENDPOINT_RESET
from src.enrich import OperacionReset, Usuario
from src.outcomes import RESOLVERS_REGISTER, resolver_resultado
from src.parsers import parse_entrada, parse_sap, parse_ticket
from src.storage import cargar_reporte, ruta_staging
from src.transform import endpoints_de, tabla_desde_log

FECHA = "2026-01-01"

# El fixture tiene 12 reseteos y 3 entradas de alta (una de ellas con el formato antiguo,
# sin los parámetros de usuario, que se conserva a propósito como caso límite).
RESETEOS = 12
ALTAS = 3

ENTRADA_ALTA = (
    "HTTP Request: http://apitools.ejemplo.com:8000/v2/sap/register_user"
    "?requester_username=gerencia001&target_employee_id=001000011"
    '&treatment=señora&job=Cons.Internos+Tienda "HTTP/1.1" 200'
)

GERENTE = Usuario(
    "gerencia001", True, "Ana Ruiz", "0001", "Gerente Tienda", "OAT/Tiendas/BackOffice"
)
CAJERO = Usuario("001000011", True, "Luis Paz", "0001", "Cajero", "Tienda/POS/Usuarios")


def alta(status, solicitante=GERENTE, target=CAJERO, **extra):
    """Arma una operación de alta mínima para probar un resolver."""
    return OperacionReset(
        operation_id="prueba",
        timestamp="2026-01-01T00:00:00Z",
        status=status,
        solicitante=solicitante,
        target=target,
        endpoint=ENDPOINT_REGISTER,
        **extra,
    )


# --- lectura de la línea de entrada --------------------------------------


def test_la_entrada_del_alta_trae_los_dos_usuarios():
    datos = parse_entrada(ENTRADA_ALTA)

    assert datos["endpoint"].endswith(ENDPOINT_REGISTER)
    assert datos["status"] == 200
    assert datos["solicitante"] == "gerencia001"
    assert datos["target"] == "001000011"


def test_la_entrada_del_alta_trae_el_tratamiento_y_el_puesto():
    datos = parse_entrada(ENTRADA_ALTA)

    assert datos["tratamiento"] == "señora"
    assert datos["puesto"] == "Cons.Internos Tienda"


def test_la_entrada_del_reseteo_sigue_leyendose_igual():
    linea = (
        "HTTP Request: http://apitools.ejemplo.com:8000/v3/users_admin/resetuser"
        '?sAMAccountName_requester=gerencia001&sAMAccountName_target=001000001 "HTTP/1.1" 200'
    )
    datos = parse_entrada(linea)

    assert datos["solicitante"] == "gerencia001"
    assert datos["target"] == "001000001"
    assert datos["tratamiento"] == ""
    assert datos["puesto"] == ""


def test_se_lee_la_respuesta_de_sap():
    mensaje = (
        "SAP input: Ambiente='ECC' Opcion='03', SAP raw response: "
        "{'MT_RespAltaUsrResetPwd': {'Estatus': 'S', "
        "'Mensaje': 'El usuario ya existe en el sistema, favor de revisar.'}}"
    )
    assert parse_sap(mensaje) == {
        "estatus": "S",
        "mensaje": "El usuario ya existe en el sistema, favor de revisar.",
    }


def test_una_linea_sin_respuesta_de_sap_no_se_confunde():
    assert parse_sap("ADManagerRawClient.get_users_list_info invoked") is None


def test_se_lee_la_creacion_del_ticket():
    mensaje = (
        "ProactivanetRawClient, method = POST, url = incidents, "
        "proactivanet_raw_response: {'Code': 'REQ 2026-000001', 'Status': 'New'}"
    )
    ticket = parse_ticket(mensaje)

    assert ticket["metodo"] == "POST"
    assert ticket["url"] == "incidents"
    assert ticket["code"] == "REQ 2026-000001"


def test_se_lee_el_cierre_del_ticket():
    mensaje = (
        "ProactivanetRawClient, method = PUT, url = incidents/ticket-0001/close, "
        "proactivanet_raw_response: {'Code': 'REQ 2026-000001', 'Status': 'Closed'}"
    )
    ticket = parse_ticket(mensaje)

    assert ticket["metodo"] == "PUT"
    assert ticket["url"].endswith("/close")


# --- reglas de negocio del alta ------------------------------------------


def test_los_codigos_de_la_especificacion_tienen_resolver():
    assert set(RESOLVERS_REGISTER) == {200, 202, 208, 400, 401, 403, 404, 500, 503}


def test_200_menciona_el_ticket_cerrado():
    mensaje = resolver_resultado(alta(200))

    assert "registrado exitosamente" in mensaje
    assert "se creó el ticket control y se cerró" in mensaje


def test_202_con_ticket_creado_pero_sin_cerrar():
    mensaje = resolver_resultado(alta(202, ticket_creado=True))

    assert "se creó el ticket control pero no pudo cerrarse" in mensaje


def test_202_sin_ticket_creado():
    mensaje = resolver_resultado(alta(202, ticket_creado=False))

    assert "no fue posible crear el ticket control" in mensaje


def test_208_dice_que_el_usuario_ya_existe():
    sap = {"estatus": "E", "mensaje": "El usuario ya existe en el sistema."}
    mensaje = resolver_resultado(alta(208, sap=sap))

    assert mensaje == "El usuario target ya existe en el ambiente ECC ECP de SAP."


def test_208_anexa_la_respuesta_de_sap_cuando_no_la_confirma():
    sap = {"estatus": "E", "mensaje": "Error de conexión con el mandante."}
    mensaje = resolver_resultado(alta(208, sap=sap))

    assert "Respuesta de SAP: Error de conexión con el mandante." in mensaje


def test_400_por_numero_de_empleado_no_numerico():
    no_numerico = Usuario("Caphum165", encontrado=False)
    mensaje = resolver_resultado(alta(400, target=no_numerico, tratamiento="señor"))

    assert mensaje == "El número de empleado no es numérico."


def test_400_por_tratamiento_invalido():
    mensaje = resolver_resultado(alta(400, tratamiento="licenciado"))

    assert mensaje == "El tratamiento no es señor ni señora."


@pytest.mark.parametrize("tratamiento", ["señor", "señora", "SEÑORA", "Señor"])
def test_los_tratamientos_validos_no_disparan_el_400(tratamiento):
    mensaje = resolver_resultado(alta(400, tratamiento=tratamiento))

    assert "tratamiento" not in mensaje


def test_401_por_falta_de_privilegios():
    cajero = Usuario("caja001", True, "Sol Diaz", "0001", "Cajero General")
    mensaje = resolver_resultado(alta(401, solicitante=cajero))

    assert "no es gerente ni administrador de sistemas" in mensaje


def test_403_por_solicitante_de_oat():
    oat = Usuario("oat001", True, "Ivo Rey", "Corporativo", "Gerente Tienda")
    mensaje = resolver_resultado(alta(403, solicitante=oat))

    assert "es OAT" in mensaje


def test_403_por_oficinas_distintas():
    otra_oficina = Usuario("001000099", True, "Eva Lima", "0002", "Cajero")
    mensaje = resolver_resultado(alta(403, target=otra_oficina))

    assert mensaje == "Los usuarios no pertenecen a la misma oficina."


def test_403_por_puesto_exclusivo_de_soriana():
    mensaje = resolver_resultado(alta(403, puesto="Supervisor Mermas"))

    assert "Conflicto con el puesto solicitado" in mensaje
    assert "no pertenece a City Club" in mensaje


def test_un_solicitante_de_city_club_si_puede_pedir_ese_puesto():
    de_city_club = Usuario(
        "gerencia001",
        True,
        "Ana Ruiz",
        "0001",
        "Gerente Tienda",
        "OAT/Tiendas/City Club",
    )
    mensaje = resolver_resultado(
        alta(403, solicitante=de_city_club, puesto="Supervisor Mermas")
    )

    assert "City Club" not in mensaje


def test_403_por_alta_de_gerente_a_quien_no_lo_es():
    mensaje = resolver_resultado(alta(403, puesto="Gerente Tienda"))

    assert "Conflicto con el puesto solicitado" in mensaje
    assert "no es gerente" in mensaje


def test_403_por_alta_de_subgerente_a_quien_no_lo_es():
    mensaje = resolver_resultado(alta(403, puesto="Subgerente Tienda"))

    assert "no es subgerente" in mensaje


def test_un_subgerente_no_cuenta_como_gerente():
    subgerente = Usuario("001000011", True, "Luis Paz", "0001", "Subgerente De Tienda")
    gerente = resolver_resultado(alta(403, target=subgerente, puesto="Gerente Tienda"))
    suyo = resolver_resultado(alta(403, target=subgerente, puesto="Subgerente Tienda"))

    assert "no es gerente" in gerente
    assert "Conflicto" not in suyo


def test_403_sin_causa_identificada_cae_en_el_generico():
    mensaje = resolver_resultado(alta(403, puesto="Recibo Tienda"))

    # El puesto es exclusivo de Soriana, así que ese sí se identifica; uno que no lo sea
    # y no toque ninguna otra regla es el que queda sin causa.
    assert "Conflicto" in mensaje
    assert "rechazada por las validaciones" in resolver_resultado(
        alta(403, puesto="Cons.Internos Tienda")
    )


def test_404_distingue_cual_usuario_no_existe():
    perdido = Usuario("noexiste", encontrado=False)

    assert resolver_resultado(alta(404, solicitante=perdido)) == (
        "No existe el usuario solicitante."
    )
    assert resolver_resultado(alta(404, target=perdido)) == (
        "No existe el usuario target."
    )


def test_500_es_un_error_desconocido():
    assert resolver_resultado(alta(500)) == "Error desconocido."


def test_503_culpa_al_servicio_de_sap():
    mensaje = resolver_resultado(alta(503))

    assert "validaciones fueron exitosas" in mensaje
    assert "SAP falló" in mensaje


def test_las_reglas_del_reseteo_no_se_aplican_al_alta():
    en_cedis = Usuario("001000011", True, "Ivo Rey", "0001", "Cajero", "OAT/Cedis/BY")
    mensaje = resolver_resultado(alta(403, target=en_cedis, puesto="Gerente Tienda"))

    # La OU bloqueada es una regla del reseteo; el alta debe resolver por el puesto.
    assert "OAT/Cedis/BY" not in mensaje
    assert "no es gerente" in mensaje


def test_el_mismo_codigo_significa_cosas_distintas_en_cada_endpoint():
    reseteo = OperacionReset(
        operation_id="prueba",
        timestamp="2026-01-01T00:00:00Z",
        status=200,
        solicitante=GERENTE,
        target=CAJERO,
        endpoint=ENDPOINT_RESET,
    )

    assert resolver_resultado(reseteo) == "Proceso exitoso."
    assert resolver_resultado(alta(200)) != "Proceso exitoso."


# --- selección de endpoints ----------------------------------------------


def test_cada_etiqueta_resuelve_a_sus_endpoints():
    assert endpoints_de("reset_user") == (ENDPOINT_RESET,)
    assert endpoints_de("register_user") == (ENDPOINT_REGISTER,)
    assert set(endpoints_de("todos")) == {ENDPOINT_RESET, ENDPOINT_REGISTER}


def test_una_etiqueta_desconocida_se_rechaza():
    with pytest.raises(ValueError, match="Selección de endpoint desconocida"):
        endpoints_de("otro_servicio")


def test_por_omision_solo_se_leen_los_reseteos(log_fixture):
    assert len(tabla_desde_log(log_fixture)) == RESETEOS


def test_la_seleccion_del_alta_deja_fuera_los_reseteos(log_fixture):
    staging = tabla_desde_log(log_fixture, "register_user")

    assert len(staging) == ALTAS
    assert set(staging["sistema"]) == {"SAP"}
    assert set(staging["accion"]) == {"alta_usuario"}


def test_la_seleccion_todos_suma_los_dos_servicios(log_fixture):
    staging = tabla_desde_log(log_fixture, "todos")

    assert len(staging) == RESETEOS + ALTAS
    assert set(staging["sistema"]) == {"ADManager", "SAP"}


def test_el_alta_del_fixture_se_resuelve_con_sus_datos_de_admanager(log_fixture):
    staging = tabla_desde_log(log_fixture, "register_user")
    fila = staging[staging["target"] == "001000011"].iloc[0]

    assert fila["solicitante"] == "gerencia001"
    assert fila["nombre_solicitante"] == "NombreGer ApellidoGer"
    assert fila["oficina_solicitante"] == "0001"
    assert fila["nombre_target"] == "NombreEmp11 ApellidoEmp11"
    assert fila["oficina_target"] == "0001"


def test_el_403_del_fixture_se_explica_por_el_puesto(log_fixture):
    staging = tabla_desde_log(log_fixture, "register_user")
    fila = staging[staging["status_http"] == 403].iloc[0]

    assert "Conflicto con el puesto solicitado" in fila["resultado_final"]


def test_el_pipeline_carga_el_alta_de_punta_a_punta():
    resultado = pipeline.ejecutar(fecha=FECHA, seleccion="register_user")

    assert resultado.total_operaciones == ALTAS
    assert resultado.seleccion == "register_user"
    assert set(cargar_reporte()["sistema"]) == {"SAP"}


def test_cada_seleccion_escribe_su_propio_staging():
    pipeline.ejecutar(fecha=FECHA, seleccion="register_user")

    assert ruta_staging(FECHA, "register_user").is_file()
    assert not ruta_staging(FECHA, "reset_user").exists()


def test_cargar_los_dos_servicios_no_duplica_los_ya_cargados():
    pipeline.ejecutar(fecha=FECHA, seleccion="reset_user")
    segunda = pipeline.ejecutar(fecha=FECHA, seleccion="todos")

    # Los reseteos ya estaban: sólo entran las altas.
    assert segunda.total_operaciones == RESETEOS + ALTAS
    assert segunda.total_nuevos == ALTAS

    reporte = cargar_reporte()
    assert len(reporte) == RESETEOS + ALTAS
    assert reporte["id"].is_unique


def test_el_reporte_mezclado_conserva_las_columnas_de_siempre():
    pipeline.ejecutar(fecha=FECHA, seleccion="todos")
    reporte = cargar_reporte()

    assert set(reporte["accion"]) == {"reset_password", "alta_usuario"}
    assert not (reporte["resultado_final"] == "").any()
    assert isinstance(reporte, pd.DataFrame)
