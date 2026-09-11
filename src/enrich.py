"""Resolución de una operación cruda en los datos que necesita el reporte.

Une las piezas que extrajo `parsers` con los registros que agrupó `reader`: localiza la
línea de entrada, indexa las consultas a ADManager y resuelve quién es el solicitante y
quién el target. Aquí se aplica también el filtro de endpoint, así que de este módulo sólo
salen las operaciones de los endpoints que se pidieron reportar.
"""

from dataclasses import dataclass

from .config import ENDPOINT_OBJETIVO
from .normalize import es_valor_nulo, norm
from .parsers import (
    parse_adm_raw,
    parse_consultas_usuario,
    parse_entrada,
    parse_sap,
    parse_ticket,
)
from .reader import Operation


@dataclass
class Usuario:
    """Datos de un usuario de ADManager ya normalizados para el reporte.

    Campos:
        sam (str): `sAMAccountName` tal como lo mandó el bot.
        encontrado (bool): `False` si ADManager no devolvió al usuario (caso 404).
        nombre_completo (str): FIRST_NAME + LAST_NAME.
        oficina (str): campo OFFICE.
        descripcion (str): campo DESCRIPTION (base de la validación de privilegios).
        ou_name (str): campo OU_NAME (base de la regla de la OU bloqueada).
    """

    sam: str
    encontrado: bool = False
    nombre_completo: str = ""
    oficina: str = ""
    descripcion: str = ""
    ou_name: str = ""


@dataclass
class OperacionReset:
    """Una operación del bot ya resuelta y lista para volverse una fila del reporte.

    Nació para `users_admin/resetuser` y conserva el nombre; los campos que sólo usa el alta
    de usuarios (`sap/register_user`) van al final y traen valor por omisión, de modo que
    una operación de reseteo se construye igual que antes.

    Campos:
        operation_id (str): identificador único de la operación en el log.
        timestamp (str): marca de tiempo de la línea de entrada del bot.
        status (int): código HTTP final devuelto por el bot.
        solicitante (Usuario): usuario que pidió la operación.
        target (Usuario): usuario sobre el que se iba a operar.
        adm_raw (dict | None): respuesta cruda de ADManager, necesaria para el 503/504.
        endpoint (str): endpoint del que salió la operación; decide qué reglas de negocio
            se le aplican y qué `accion` y `sistema` lleva la fila.
        tratamiento (str): parámetro `treatment` del alta ("señor" / "señora").
        puesto (str): parámetro `job` del alta, el puesto que se pidió dar de alta.
        sap (dict | None): respuesta de SAP al alta (`{'estatus', 'mensaje'}`).
        ticket_creado (bool): `True` si se llegó a crear el ticket de control.
        ticket_cerrado (bool): `True` si ese ticket llegó a cerrarse.
    """

    operation_id: str
    timestamp: str
    status: int
    solicitante: Usuario
    target: Usuario
    adm_raw: dict | None = None
    endpoint: str = ENDPOINT_OBJETIVO
    tratamiento: str = ""
    puesto: str = ""
    sap: dict | None = None
    ticket_creado: bool = False
    ticket_cerrado: bool = False


def _campo(datos: dict, clave: str) -> str:
    """Lee un campo de ADManager tratando sus marcadores de "sin dato" como cadena vacía.

    Input:
        datos (dict): diccionario del usuario devuelto por ADManager.
        clave (str): nombre del campo (`OFFICE`, `DESCRIPTION`, `OU_NAME`, ...).

    Output:
        str: el valor sin espacios sobrantes, o `''` si falta o es un valor nulo de AD.
    """
    valor = datos.get(clave, "")
    return "" if es_valor_nulo(valor) else str(valor).strip()


def construir_usuario(sam: str, datos: dict | None) -> Usuario:
    """Construye un `Usuario` a partir de la respuesta de ADManager.

    Input:
        sam (str): `sAMAccountName` del usuario, tal como lo mandó el bot.
        datos (dict | None): diccionario devuelto por ADManager, o `None` si no se encontró.

    Output:
        Usuario: con `encontrado=False` y los demás campos vacíos si `datos` es `None`; en
        caso contrario, con nombre, oficina, descripción y OU ya normalizados.
    """
    if not datos:
        return Usuario(sam=sam, encontrado=False)
    nombre = " ".join(
        p for p in (_campo(datos, "FIRST_NAME"), _campo(datos, "LAST_NAME")) if p
    )
    return Usuario(
        sam=sam,
        encontrado=True,
        nombre_completo=nombre,
        oficina=_campo(datos, "OFFICE"),
        descripcion=_campo(datos, "DESCRIPTION"),
        ou_name=_campo(datos, "OU_NAME"),
    )


def indexar_usuarios(operacion: Operation) -> dict[str, dict | None]:
    """Construye un índice de los usuarios consultados dentro de una operación.

    Las consultas aparecen en orden variable y a veces se buscan por `employeeID` en lugar
    de `sAMAccountName`, así que se indexa tanto el valor buscado como el
    `SAM_ACCOUNT_NAME` devuelto. Un hallazgo nunca se pisa con un `None`.

    Input:
        operacion (Operation): operación cruda agrupada por `operation_Id`.

    Output:
        dict[str, dict | None]: clave normalizada -> datos del usuario, o `None` si esa
        búsqueda no encontró a nadie.
    """
    indice: dict[str, dict | None] = {}
    for message in operacion.messages():
        for consulta in parse_consultas_usuario(message):
            clave = norm(consulta["valor"])
            usuario = consulta["usuario"]
            # Un hallazgo posterior nunca se pisa con un None anterior (ni al revés).
            if clave not in indice or (indice[clave] is None and usuario is not None):
                indice[clave] = usuario
            if usuario:
                indice[norm(usuario.get("SAM_ACCOUNT_NAME", ""))] = usuario
    return indice


def enriquecer(
    operacion: Operation, endpoints: tuple[str, ...] = (ENDPOINT_OBJETIVO,)
) -> OperacionReset | None:
    """Resuelve una operación cruda del log en una `OperacionReset` completa.

    Recorre los registros para localizar la línea de entrada, el último bloque ADM-Raw, la
    respuesta de SAP y el rastro del ticket de control, y aplica el filtro de endpoint: sólo
    las operaciones de los endpoints pedidos llegan al reporte.

    Input:
        operacion (Operation): operación cruda agrupada por `operation_Id`.
        endpoints (tuple[str, ...]): endpoints que se quieren reportar. Por omisión sólo el
            reseteo de ADManager, que es el comportamiento histórico del proceso.

    Output:
        OperacionReset | None: `None` si la operación no tiene línea de entrada o su
        endpoint no es de los pedidos; en caso contrario, la operación con ambos usuarios
        resueltos.
    """
    entrada = None
    timestamp = operacion.timestamp
    adm_raw = None
    sap = None
    ticket_creado = False
    ticket_cerrado = False
    for rec in operacion.records:
        if entrada is None:
            candidata = parse_entrada(rec.message)
            if candidata is not None:
                entrada, timestamp = candidata, rec.timestamp
        adm = parse_adm_raw(rec.message)
        if adm is not None:
            adm_raw = adm
        respuesta_sap = parse_sap(rec.message)
        if respuesta_sap is not None:
            sap = respuesta_sap
        ticket = parse_ticket(rec.message)
        if ticket is not None and ticket["url"].startswith("incidents"):
            if ticket["metodo"] == "POST":
                ticket_creado = True
            elif ticket["metodo"] == "PUT" and ticket["url"].endswith("/close"):
                ticket_cerrado = True
    if entrada is None:
        return None

    endpoint = next(
        (e for e in endpoints if entrada["endpoint"].endswith(e)),
        None,
    )
    if endpoint is None:
        return None

    indice = indexar_usuarios(operacion)
    return OperacionReset(
        operation_id=operacion.operation_id,
        timestamp=timestamp,
        status=entrada["status"],
        solicitante=construir_usuario(
            entrada["solicitante"], indice.get(norm(entrada["solicitante"]))
        ),
        target=construir_usuario(
            entrada["target"], indice.get(norm(entrada["target"]))
        ),
        adm_raw=adm_raw,
        endpoint=endpoint,
        tratamiento=entrada["tratamiento"],
        puesto=entrada["puesto"],
        sap=sap,
        ticket_creado=ticket_creado,
        ticket_cerrado=ticket_cerrado,
    )
