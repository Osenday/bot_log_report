"""Traducción del código HTTP a un mensaje legible para la columna `resultado_final`.

Un *resolver* por código, registrados en el diccionario `RESOLVERS`. Añadir un código nuevo
es añadir una función y una entrada: no se toca nada más del proceso.

Los códigos 202 y 429 no aparecen en los logs actuales, pero están implementados porque son
parte de la especificación y pueden aparecer cualquier día.

Este módulo NO conoce expresiones regulares: sólo aplica reglas sobre una `OperacionReset`.
"""

from collections.abc import Callable

from .config import OU_BLOQUEADA
from .enrich import OperacionReset
from .normalize import misma_oficina, norm, tiene_privilegios
from .parsers import mensaje_admanager

MENSAJE_403_GENERICO = (
    "El reseteo fue rechazado por las validaciones de acceso del bot."
)


def _resultado_200(op: OperacionReset) -> str:
    """Mensaje del estatus 200: todas las validaciones pasaron y el reseteo se ejecutó.

    Input:
        op (OperacionReset): operación resuelta (no se consulta ningún campo).

    Output:
        str: mensaje legible para la columna `resultado_final`.
    """
    return "Proceso exitoso."


def _resultado_202(op: OperacionReset) -> str:
    """Mensaje del estatus 202: el target es de Corporativo y puede autoresetearse.

    Input:
        op (OperacionReset): operación resuelta (no se consulta ningún campo: el estatus
            del bot ya implica la causa).

    Output:
        str: mensaje legible para la columna `resultado_final`.
    """
    return (
        "El usuario objetivo pertenece a Corporativo, "
        "por lo que puede autoresetear su contraseña sin el bot."
    )


def _resultado_403(op: OperacionReset) -> str:
    """Mensaje del estatus 403, deduciendo cuál de las tres validaciones falló.

    El log no dice qué regla se disparó, así que se evalúan en el orden de la
    especificación: oficinas distintas -> falta de privilegios -> OU bloqueada. Si ninguna
    explica el rechazo se devuelve un mensaje genérico, que en las validaciones sirve como
    alerta de que hay una causa sin modelar.

    Input:
        op (OperacionReset): operación resuelta; usa `oficina`, `descripcion` y `ou_name`.

    Output:
        str: mensaje legible con la causa identificada, o el genérico si no hay ninguna.
    """
    if not misma_oficina(op.solicitante.oficina, op.target.oficina):
        return "El usuario solicitante y el usuario objetivo no pertenecen a la misma oficina."
    if not tiene_privilegios(op.solicitante.descripcion):
        return "El usuario solicitante no es gerente ni administrador de sistemas."
    if norm(op.target.ou_name) == OU_BLOQUEADA:
        return (
            "El usuario objetivo pertenece a la OU 'OAT/Cedis/BY' "
            "y no puede ser reseteado mediante el bot."
        )
    return MENSAJE_403_GENERICO


def _resultado_404(op: OperacionReset) -> str:
    """Mensaje del estatus 404, distinguiendo qué usuario no se encontró en ADManager.

    La distinción sale de la bandera `encontrado`, que a su vez viene de que la `UsersList`
    de la consulta correspondiente llegara vacía.

    Input:
        op (OperacionReset): operación resuelta; usa `solicitante.encontrado` y
            `target.encontrado`.

    Output:
        str: uno de los tres mensajes de la especificación (ninguno / solicitante / target),
        o un genérico si ambos usuarios sí se encontraron.
    """
    falta_solicitante = not op.solicitante.encontrado
    falta_target = not op.target.encontrado
    if falta_solicitante and falta_target:
        return "Ningún usuario se encontró en ADManager."
    if falta_solicitante:
        return "El usuario solicitante no se encontró en ADManager."
    if falta_target:
        return "El usuario objetivo no se encontró en ADManager."
    return "No se encontró la información solicitada en ADManager."


def _resultado_429(op: OperacionReset) -> str:
    """Mensaje del estatus 429: se agotaron los tokens de ADManager.

    Input:
        op (OperacionReset): operación resuelta (no se consulta ningún campo).

    Output:
        str: mensaje legible para la columna `resultado_final`.
    """
    return "No se pudo ejecutar el reseteo: se agotaron los tokens de ADManager."


def _resultado_500(op: OperacionReset) -> str:
    """Mensaje del estatus 500: error inesperado, caso crítico que requiere revisión.

    Input:
        op (OperacionReset): operación resuelta (no se consulta ningún campo).

    Output:
        str: mensaje legible para la columna `resultado_final`.
    """
    return "Ocurrió un error inesperado en el proceso. Caso crítico: requiere revisión."


def _resultado_503(op: OperacionReset) -> str:
    """Mensaje del estatus 503, concatenando el error exacto que devolvió ADManager.

    La especificación pide incluir ese texto; se toma del bloque `| ADM-Raw response |`.

    Input:
        op (OperacionReset): operación resuelta; usa `adm_raw`.

    Output:
        str: mensaje base, más " Respuesta de ADManager: <detalle>" si hay `statusMessage`.
    """
    base = "Ocurrió un error en ADManager y el reseteo no se pudo ejecutar."
    detalle = mensaje_admanager(op.adm_raw)
    return f"{base} Respuesta de ADManager: {detalle}" if detalle else base


def _resultado_504(op: OperacionReset) -> str:
    """Mensaje del estatus 504: timeout (más de 35 s) en la comunicación con ADManager.

    Input:
        op (OperacionReset): operación resuelta (no se consulta ningún campo).

    Output:
        str: mensaje legible para la columna `resultado_final`.
    """
    return (
        "Timeout en la comunicación con ADManager "
        "(más de 35 segundos sin respuesta); se asume que el reseteo no se ejecutó."
    )


RESOLVERS: dict[int, Callable[[OperacionReset], str]] = {
    200: _resultado_200,
    202: _resultado_202,
    403: _resultado_403,
    404: _resultado_404,
    429: _resultado_429,
    500: _resultado_500,
    503: _resultado_503,
    504: _resultado_504,
}


def resolver_resultado(op: OperacionReset) -> str:
    """Despacha la operación al resolver de su código HTTP y devuelve el mensaje humano.

    Añadir un código nuevo es añadir una función y una entrada en `RESOLVERS`: el resto del
    proceso no cambia.

    Input:
        op (OperacionReset): operación resuelta; el despacho se hace por `op.status`.

    Output:
        str: mensaje de la columna `resultado_final`; si el código no tiene resolver
        registrado, un texto explícito de "sin regla de negocio definida".
    """
    resolver = RESOLVERS.get(op.status)
    if resolver is None:
        return f"Estatus HTTP {op.status} sin regla de negocio definida."
    return resolver(op)
