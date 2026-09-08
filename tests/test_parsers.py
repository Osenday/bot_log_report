"""Pruebas de las expresiones regulares que leen los mensajes del log."""

from src.parsers import (
    mensaje_admanager,
    parse_adm_raw,
    parse_consultas_usuario,
    parse_entrada,
)

ENTRADA_DEL_BOT = (
    "HTTP Request: http://apitools.ejemplo.com:8000/v3/users_admin/resetuser"
    "?sAMAccountName_requester=gerencia001&sAMAccountName_target=001000001"
    ' "HTTP/1.1" 404'
)

# Ojo: aquí el status va DENTRO de las comillas y hay método (GET). No es una entrada.
LLAMADA_A_ADMANAGER = 'HTTP Request: GET https://admanager.ejemplo.com/RestAPI/SearchUser?x=1 "HTTP/1.1 200 "'


def bloque_busqueda(sam: str, users_list: str) -> str:
    """Arma un mensaje con el formato multilínea real de una consulta SearchUser."""
    return (
        "ADManagerRawClient.get_users_list_info_from_admanager invoked\n"
        "Params to execute POST to SearchUser: {'domainName': 'ejemplo.com', "
        f"'filter': '(sAMAccountName:equal:{sam})'}}, Raw Response: {users_list}\n"
        "\n"
        ", Raw status_code: 200, Raw reason_phrase: \n"
    )


USUARIO_ENCONTRADO = (
    '{"UsersList":[{"FIRST_NAME":"Ana","LAST_NAME":"Ruiz","OFFICE":"0001"}],"count":1}'
)
USUARIO_NO_ENCONTRADO = '{"UsersList":[],"count":0}'


def test_parse_entrada_extrae_usuarios_y_status():
    datos = parse_entrada(ENTRADA_DEL_BOT)
    assert datos["status"] == 404
    assert datos["solicitante"] == "gerencia001"
    assert datos["target"] == "001000001"
    assert datos["endpoint"].endswith("users_admin/resetuser")


def test_parse_entrada_ignora_las_llamadas_a_admanager():
    assert parse_entrada(LLAMADA_A_ADMANAGER) is None


def test_parse_consultas_usuario_lee_el_bloque_multilinea():
    consultas = parse_consultas_usuario(
        bloque_busqueda("gerencia001", USUARIO_ENCONTRADO)
    )
    assert len(consultas) == 1
    assert consultas[0]["valor"] == "gerencia001"
    assert consultas[0]["usuario"]["FIRST_NAME"] == "Ana"


def test_parse_consultas_usuario_detecta_userslist_vacia():
    # Es lo que distingue los sub-casos del 404.
    consultas = parse_consultas_usuario(
        bloque_busqueda("noexiste", USUARIO_NO_ENCONTRADO)
    )
    assert consultas[0]["usuario"] is None


def test_parse_consultas_usuario_descarta_un_cuerpo_truncado():
    consultas = parse_consultas_usuario(bloque_busqueda("gerencia001", ""))
    assert consultas == []


def test_parse_adm_raw_lee_el_cuerpo():
    mensaje = (
        "ADM-Raw response | status: 200 | body: "
        "[{'statusMessage': 'Password reset successful.', 'status': '1'}]"
    )
    adm = parse_adm_raw(mensaje)
    assert adm["status"] == 200
    assert mensaje_admanager(adm) == "Password reset successful."


def test_parse_adm_raw_lee_la_razon_del_timeout():
    mensaje = "ADM-Raw response | status: 504 | reason: ADM timed out | timeout_type: ReadTimeout"
    adm = parse_adm_raw(mensaje)
    assert adm["status"] == 504
    assert adm["reason"] == "ADM timed out"


def test_parse_adm_raw_ignora_otros_mensajes():
    assert parse_adm_raw(ENTRADA_DEL_BOT) is None


def test_mensaje_admanager_sin_cuerpo_devuelve_cadena_vacia():
    assert mensaje_admanager(None) == ""
    assert mensaje_admanager({"status": 504, "reason": "ADM timed out"}) == ""
