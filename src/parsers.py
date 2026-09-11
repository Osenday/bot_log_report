"""Expresiones regulares y extracción de datos de los mensajes del log.

Cinco patrones cubren todo lo que necesita el reporte:

1. `ENTRY_RE`  — la línea de entrada del bot: trae `solicitante`, `target` y el status final
   de la operación. Se distingue de las llamadas a ADManager porque el status va *fuera* de
   las comillas (`"HTTP/1.1" 404` contra `"HTTP/1.1 200 "`) y porque no lleva método HTTP.
   Sirve igual para los dos endpoints: sólo cambian los nombres de los parámetros.
2. `SEARCH_RE` — las consultas `SearchUser`, con su `filter` (qué usuario se buscó) y su
   `Raw Response` en JSON. Una `UsersList` vacía es lo que resuelve los sub-casos del 404.
3. `ADM_RAW_RE` — el bloque `| ADM-Raw response |`, del que salen el mensaje de error del
   503 y la razón del timeout del 504.
4. `SAP_RE`    — la respuesta de SAP al alta de un usuario, que dice en texto si el usuario
   ya existía (estatus 208).
5. `TICKET_RE` — las llamadas a ProactivaNet, que dicen si el ticket de control se creó y
   si llegó a cerrarse (los dos sub-casos del 202 en el alta).

Este módulo NO conoce reglas de negocio: sólo extrae texto y lo convierte en estructuras de
Python.
"""

import ast
import json
import re
from urllib.parse import parse_qs, urlparse

ENTRY_RE = re.compile(
    r"^HTTP Request: (?P<url>https?://\S+) \"HTTP/1\.1\" (?P<status>\d{3})\s*$"
)

SEARCH_RE = re.compile(
    r"'filter': '\((?P<campo>sAMAccountName|employeeID):equal:(?P<valor>[^)]*)\)'\},"
    r"\s*Raw Response:\s*(?P<body>.*?),\s*Raw status_code:",
    re.S,
)

ADM_RAW_RE = re.compile(
    r"^ADM-Raw response \| status: (?P<status>\d+) \| (?P<resto>.*)$", re.S
)

SAP_RE = re.compile(r"SAP raw response:\s*(?P<body>\{.*\})\s*$", re.S)

TICKET_RE = re.compile(
    r"ProactivanetRawClient,\s*method\s*=\s*(?P<metodo>\w+),\s*url\s*=\s*(?P<url>[^,]+),"
)

# Cada endpoint nombra distinto a los mismos dos usuarios: el reseteo los manda como
# `sAMAccountName_*` y el alta como `requester_username` / `target_employee_id`. Se busca
# en orden y gana el primero que venga en la URL.
PARAMS_SOLICITANTE = ("sAMAccountName_requester", "requester_username")
PARAMS_TARGET = ("sAMAccountName_target", "target_employee_id")


def _primer_parametro(params: dict[str, list[str]], nombres: tuple[str, ...]) -> str:
    """Devuelve el valor del primer parámetro de la lista que venga en la query string.

    Input:
        params (dict[str, list[str]]): resultado de `parse_qs()` sobre la query.
        nombres (tuple[str, ...]): nombres a probar, en orden de preferencia.

    Output:
        str: el primer valor encontrado, o `''` si no viene ninguno de los nombres.
    """
    for nombre in nombres:
        valores = params.get(nombre)
        if valores:
            return valores[0]
    return ""


def parse_entrada(message: str) -> dict | None:
    """Extrae la línea de entrada del bot: endpoint, estatus final y usuarios.

    Es la única línea que trae el status HTTP final de la operación y los dos usuarios
    involucrados, que vienen como parámetros de la query string. `tratamiento` y `puesto`
    sólo los manda el alta de usuarios; en un reseteo quedan vacíos.

    Input:
        message (str): mensaje de un `LogRecord`.

    Output:
        dict | None: `None` si la línea no es una entrada del bot; si lo es,
        `{'endpoint': str, 'status': int, 'solicitante': str, 'target': str,
        'tratamiento': str, 'puesto': str}`.
    """
    m = ENTRY_RE.match(message.strip())
    if not m:
        return None
    url = urlparse(m["url"])
    params = parse_qs(url.query)
    return {
        "endpoint": url.path.lstrip("/"),
        "status": int(m["status"]),
        "solicitante": _primer_parametro(params, PARAMS_SOLICITANTE),
        "target": _primer_parametro(params, PARAMS_TARGET),
        "tratamiento": _primer_parametro(params, ("treatment",)),
        "puesto": _primer_parametro(params, ("job",)),
    }


def parse_sap(message: str) -> dict | None:
    """Extrae la respuesta de SAP al alta de un usuario.

    SAP no usa códigos propios: dice en el texto de `Mensaje` si el alta se hizo o si el
    usuario ya existía. El cuerpo viene como literal de Python y envuelto en una clave cuyo
    nombre puede cambiar (`MT_RespAltaUsrResetPwd`), así que se toma el primer diccionario
    que haya dentro.

    Input:
        message (str): mensaje de un `LogRecord`.

    Output:
        dict | None: `None` si el mensaje no trae respuesta de SAP o no se pudo evaluar; si
        la trae, `{'estatus': str, 'mensaje': str}`.
    """
    m = SAP_RE.search(message)
    if not m:
        return None
    try:
        body = ast.literal_eval(m["body"].strip())
    except (ValueError, SyntaxError):
        return None
    if not isinstance(body, dict):
        return None
    interno = next((v for v in body.values() if isinstance(v, dict)), {})
    return {
        "estatus": str(interno.get("Estatus", "")).strip(),
        "mensaje": str(interno.get("Mensaje", "")).strip(),
    }


def parse_ticket(message: str) -> dict | None:
    """Extrae una llamada a ProactivaNet, de donde sale el estado del ticket de control.

    El alta crea un ticket (`POST incidents`) y después lo escala, resuelve y cierra
    (`PUT incidents/<id>/close`). Que falte alguno de esos pasos es lo que distingue los
    dos sub-casos del estatus 202.

    Input:
        message (str): mensaje de un `LogRecord`.

    Output:
        dict | None: `None` si el mensaje no es una llamada a ProactivaNet; si lo es,
        `{'metodo': str, 'url': str, 'code': str}`, donde `code` es el folio del ticket
        (`REQ 2026-378990`) o `''` si la respuesta no lo trae.
    """
    m = TICKET_RE.search(message)
    if not m:
        return None
    code = re.search(r"'Code':\s*'(?P<code>[^']*)'", message)
    return {
        "metodo": m["metodo"].strip().upper(),
        "url": m["url"].strip(),
        "code": code["code"].strip() if code else "",
    }


def parse_consultas_usuario(message: str) -> list[dict]:
    """Extrae las consultas `SearchUser` hechas a ADManager dentro de un mensaje.

    Una `UsersList` vacía es justamente lo que permite distinguir los sub-casos del 404
    (no se encontró el solicitante, el target o ninguno).

    Input:
        message (str): mensaje de un `LogRecord` (puede contener varias consultas).

    Output:
        list[dict]: una entrada por consulta, con
        `{'campo': str, 'valor': str, 'usuario': dict | None}`; `usuario` es el primer
        elemento de `UsersList` o `None` si la búsqueda no arrojó resultados. Las consultas
        cuyo cuerpo no es JSON válido se omiten.
    """
    resultados = []
    for m in SEARCH_RE.finditer(message):
        try:
            body = json.loads(m["body"].strip())
        except json.JSONDecodeError:
            continue
        usuarios = body.get("UsersList") or []
        resultados.append(
            {
                "campo": m["campo"],
                "valor": m["valor"],
                "usuario": usuarios[0] if usuarios else None,
            }
        )
    return resultados


def parse_adm_raw(message: str) -> dict | None:
    """Extrae el bloque `| ADM-Raw response |` con la respuesta cruda de ADManager.

    De aquí salen el mensaje de error exacto del 503 y la razón del timeout del 504. El
    cuerpo viene como literal de Python (no JSON), por eso se evalúa con `ast.literal_eval`.

    Input:
        message (str): mensaje de un `LogRecord`.

    Output:
        dict | None: `None` si el mensaje no es un bloque ADM-Raw; si lo es,
        `{'status': int, 'resto': str}` más las claves opcionales `'body'` (objeto de
        Python, o `None` si no se pudo evaluar) y `'reason'` (str).
    """
    m = ADM_RAW_RE.match(message.strip())
    if not m:
        return None
    resto = m["resto"]
    info: dict = {"status": int(m["status"]), "resto": resto}
    body_m = re.match(r"body:\s*(?P<body>.*)$", resto, re.S)
    if body_m:
        try:
            info["body"] = ast.literal_eval(body_m["body"].strip())
        except (ValueError, SyntaxError):
            info["body"] = None
    reason_m = re.search(r"reason:\s*(?P<reason>[^|]+)", resto)
    if reason_m:
        info["reason"] = reason_m["reason"].strip()
    return info


def mensaje_admanager(adm: dict | None) -> str:
    """Obtiene el `statusMessage` exacto que devolvió ADManager.

    La especificación exige concatenarlo al mensaje final del estatus 503. El cuerpo puede
    venir como lista de dicts o como dict suelto, así que se contemplan ambas formas.

    Input:
        adm (dict | None): resultado de `parse_adm_raw()`, o `None`.

    Output:
        str: el `statusMessage` sin espacios sobrantes, o cadena vacía si no hay tal campo.
    """
    body = (adm or {}).get("body")
    if isinstance(body, list) and body and isinstance(body[0], dict):
        return str(body[0].get("statusMessage", "")).strip()
    if isinstance(body, dict):
        return str(body.get("statusMessage", "")).strip()
    return ""
