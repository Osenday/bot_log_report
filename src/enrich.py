"""Resolución de una operación cruda en los datos que necesita el reporte.

Une las piezas que extrajo `parsers` con los registros que agrupó `reader`: localiza la
línea de entrada, indexa las consultas a ADManager y resuelve quién es el solicitante y
quién el target. Aquí se aplica también el filtro de endpoint, así que nada que no sea un
`users_admin/resetuser` sale de este módulo.
"""

from dataclasses import dataclass

from .config import ENDPOINT_OBJETIVO
from .normalize import es_valor_nulo, norm
from .parsers import parse_adm_raw, parse_consultas_usuario, parse_entrada
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
    """Una operación `users_admin/resetuser` ya resuelta y lista para volverse una fila.

    Campos:
        operation_id (str): identificador único de la operación en el log.
        timestamp (str): marca de tiempo de la línea de entrada del bot.
        status (int): código HTTP final devuelto por el bot.
        solicitante (Usuario): usuario que pidió el reseteo.
        target (Usuario): usuario al que se le iba a resetear la contraseña.
        adm_raw (dict | None): respuesta cruda de ADManager, necesaria para el 503/504.
    """

    operation_id: str
    timestamp: str
    status: int
    solicitante: Usuario
    target: Usuario
    adm_raw: dict | None = None


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


def enriquecer(operacion: Operation) -> OperacionReset | None:
    """Resuelve una operación cruda del log en una `OperacionReset` completa.

    Recorre los registros para localizar la línea de entrada y el último bloque ADM-Raw, y
    aplica el filtro de endpoint: sólo los `users_admin/resetuser` llegan al reporte.

    Input:
        operacion (Operation): operación cruda agrupada por `operation_Id`.

    Output:
        OperacionReset | None: `None` si la operación no tiene línea de entrada o no es un
        reseteo de ADManager; en caso contrario, la operación con ambos usuarios resueltos.
    """
    entrada = None
    timestamp = operacion.timestamp
    adm_raw = None
    for rec in operacion.records:
        if entrada is None:
            candidata = parse_entrada(rec.message)
            if candidata is not None:
                entrada, timestamp = candidata, rec.timestamp
        adm = parse_adm_raw(rec.message)
        if adm is not None:
            adm_raw = adm
    if entrada is None or not entrada["endpoint"].endswith(ENDPOINT_OBJETIVO):
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
    )
