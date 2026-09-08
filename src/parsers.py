"""Expresiones regulares y extracción de datos de los mensajes del log.

Tres patrones cubren todo lo que necesita el reporte:

1. `ENTRY_RE`  — la línea de entrada del bot: trae `solicitante`, `target` y el status final
   de la operación. Se distingue de las llamadas a ADManager porque el status va *fuera* de
   las comillas (`"HTTP/1.1" 404` contra `"HTTP/1.1 200 "`) y porque no lleva método HTTP.
2. `SEARCH_RE` — las consultas `SearchUser`, con su `filter` (qué usuario se buscó) y su
   `Raw Response` en JSON. Una `UsersList` vacía es lo que resuelve los sub-casos del 404.
3. `ADM_RAW_RE` — el bloque `| ADM-Raw response |`, del que salen el mensaje de error del
   503 y la razón del timeout del 504.

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


def parse_entrada(message: str) -> dict | None:
    """Extrae la línea de entrada del bot: endpoint, estatus final y usuarios.

    Es la única línea que trae el status HTTP final de la operación y los dos usuarios
    involucrados, que vienen como parámetros de la query string.

    Input:
        message (str): mensaje de un `LogRecord`.

    Output:
        dict | None: `None` si la línea no es una entrada del bot; si lo es,
        `{'endpoint': str, 'status': int, 'solicitante': str, 'target': str}`.
    """
    m = ENTRY_RE.match(message.strip())
    if not m:
        return None
    url = urlparse(m["url"])
    params = parse_qs(url.query)
    return {
        "endpoint": url.path.lstrip("/"),
        "status": int(m["status"]),
        "solicitante": params.get("sAMAccountName_requester", [""])[0],
        "target": params.get("sAMAccountName_target", [""])[0],
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
