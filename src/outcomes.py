"""Traducción del código HTTP a un mensaje legible para la columna `resultado_final`.

Un *resolver* por código, registrados en un diccionario. Añadir un código nuevo es añadir
una función y una entrada: no se toca nada más del proceso.

Hay una tabla por endpoint, porque los dos servicios reutilizan los mismos códigos con otro
significado: un 403 del reseteo habla de la OU bloqueada y uno del alta, del puesto que se
pidió dar de alta.

- `RESOLVERS`          — reseteo de contraseñas (`users_admin/resetuser`).
- `RESOLVERS_REGISTER` — alta de usuarios en SAP (`sap/register_user`).

Varios códigos no aparecen en los logs actuales (202 y 429 en el reseteo; 202, 401, 500 y
503 en el alta), pero están implementados porque son parte de la especificación y pueden
aparecer cualquier día.

Este módulo NO conoce expresiones regulares: sólo aplica reglas sobre una `OperacionReset`.
"""

from collections.abc import Callable

from .config import (
    ENDPOINT_REGISTER,
    MARCADOR_USUARIO_EXISTENTE,
    OU_BLOQUEADA,
    PUESTO_GERENTE,
    PUESTO_SUBGERENTE,
    PUESTOS_EXCLUSIVOS_SORIANA,
)
from .enrich import OperacionReset
from .normalize import (
    es_city_club,
    es_corporativo,
    es_gerente,
    es_numero_empleado,
    es_subgerente,
    misma_oficina,
    norm,
    tiene_privilegios,
    tratamiento_valido,
)
from .parsers import mensaje_admanager

MENSAJE_403_GENERICO = (
    "El reseteo fue rechazado por las validaciones de acceso del bot."
)

MENSAJE_403_REGISTER_GENERICO = (
    "El alta fue rechazada por las validaciones de acceso del bot."
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


# --- Alta de usuarios en SAP (sap/register_user) -------------------------
# El alta reutiliza los códigos HTTP con otro significado, así que tiene su propia tabla de
# resolvers. Las dos conviven y `resolver_resultado()` elige según el endpoint de la fila.


def _registro_200(op: OperacionReset) -> str:
    """Mensaje del estatus 200 del alta: el usuario se registró y el ticket quedó cerrado.

    Input:
        op (OperacionReset): operación resuelta (no se consulta ningún campo).

    Output:
        str: mensaje legible para la columna `resultado_final`.
    """
    return (
        "El usuario target fue registrado exitosamente, "
        "se creó el ticket control y se cerró."
    )


def _registro_202(op: OperacionReset) -> str:
    """Mensaje del estatus 202 del alta, distinguiendo hasta dónde llegó el ticket.

    El alta sí se hizo; lo que falló fue el ticket de control. Que exista un `POST incidents`
    en el log es lo que separa "no se pudo crear" de "se creó pero no cerró".

    Input:
        op (OperacionReset): operación resuelta; usa `ticket_creado`.

    Output:
        str: uno de los dos mensajes del estatus 202.
    """
    if not op.ticket_creado:
        return (
            "El usuario target fue registrado exitosamente, "
            "pero no fue posible crear el ticket control."
        )
    return (
        "El usuario target fue registrado exitosamente, "
        "se creó el ticket control pero no pudo cerrarse."
    )


def _registro_208(op: OperacionReset) -> str:
    """Mensaje del estatus 208 del alta: el usuario ya estaba dado de alta en SAP.

    SAP no manda un código propio: lo dice en el texto de su respuesta ("El usuario ya
    existe en el sistema, favor de revisar."). Cuando esa respuesta no lo confirma se anexa
    tal cual, para que quede a la vista por qué el bot resolvió un 208.

    Input:
        op (OperacionReset): operación resuelta; usa `sap`.

    Output:
        str: mensaje legible para la columna `resultado_final`.
    """
    base = "El usuario target ya existe en el ambiente ECC ECP de SAP."
    mensaje = str((op.sap or {}).get("mensaje", "")).strip()
    if mensaje and MARCADOR_USUARIO_EXISTENTE not in norm(mensaje):
        return f"{base} Respuesta de SAP: {mensaje}"
    return base


def _registro_400(op: OperacionReset) -> str:
    """Mensaje del estatus 400 del alta, deduciendo cuál de los dos parámetros vino mal.

    Se revisan en el orden de la especificación: primero el número de empleado y después el
    tratamiento.

    Input:
        op (OperacionReset): operación resuelta; usa `target.sam` y `tratamiento`.

    Output:
        str: la causa identificada, o un genérico si ambos parámetros parecen correctos.
    """
    if not es_numero_empleado(op.target.sam):
        return "El número de empleado no es numérico."
    if not tratamiento_valido(op.tratamiento):
        return "El tratamiento no es señor ni señora."
    return "Los datos de la solicitud no son válidos."


def _registro_401(op: OperacionReset) -> str:
    """Mensaje del estatus 401 del alta: el solicitante no tiene un puesto que lo autorice.

    Input:
        op (OperacionReset): operación resuelta; usa `solicitante.descripcion`.

    Output:
        str: mensaje legible para la columna `resultado_final`.
    """
    return "El usuario solicitante no es gerente ni administrador de sistemas."


def _conflicto_de_puesto(op: OperacionReset) -> str:
    """Identifica cuál de los tres conflictos entre el puesto pedido y los datos reales hubo.

    El puesto pedido llega en el parámetro `job` de la URL; el que el usuario ya tiene está
    en el campo DESCRIPTION de ADManager.

    Input:
        op (OperacionReset): operación resuelta; usa `puesto`, `solicitante.ou_name` y
            `target.descripcion`.

    Output:
        str: el detalle del conflicto, o `''` si ninguno de los tres explica el rechazo.
    """
    puesto = norm(op.puesto)
    if (
        not es_city_club(op.solicitante.ou_name)
        and puesto in PUESTOS_EXCLUSIVOS_SORIANA
    ):
        return (
            "el solicitante no pertenece a City Club "
            "y solicitó el alta de un puesto exclusivo de Soriana."
        )
    if puesto == PUESTO_GERENTE and not es_gerente(op.target.descripcion):
        return (
            "se solicitó el alta de un gerente y el usuario target "
            "no es gerente de acuerdo con ADManager."
        )
    if puesto == PUESTO_SUBGERENTE and not es_subgerente(op.target.descripcion):
        return (
            "se solicitó el alta de un subgerente y el usuario target "
            "no es subgerente de acuerdo con ADManager."
        )
    return ""


def _registro_403(op: OperacionReset) -> str:
    """Mensaje del estatus 403 del alta, deduciendo cuál validación de acceso falló.

    Se evalúan en el orden de la especificación: solicitante de OAT -> oficinas distintas ->
    conflicto con el puesto solicitado. Si ninguna explica el rechazo se devuelve un
    genérico, que en las validaciones sirve como alerta de una causa sin modelar.

    Input:
        op (OperacionReset): operación resuelta; usa las oficinas, la OU del solicitante y
            el puesto pedido.

    Output:
        str: mensaje legible con la causa identificada, o el genérico si no hay ninguna.
    """
    if es_corporativo(op.solicitante.oficina):
        return (
            "El usuario solicitante es OAT, "
            "por lo que no tiene permitido ejecutar este proceso."
        )
    if not misma_oficina(op.solicitante.oficina, op.target.oficina):
        return "Los usuarios no pertenecen a la misma oficina."
    conflicto = _conflicto_de_puesto(op)
    if conflicto:
        return f"Conflicto con el puesto solicitado: {conflicto}"
    return MENSAJE_403_REGISTER_GENERICO


def _registro_404(op: OperacionReset) -> str:
    """Mensaje del estatus 404 del alta, distinguiendo qué usuario no existe.

    El solicitante se busca por `sAMAccountName` y el objetivo por `employeeID`; en ambos
    casos la bandera `encontrado` viene de que la `UsersList` llegara vacía.

    Input:
        op (OperacionReset): operación resuelta; usa `solicitante.encontrado` y
            `target.encontrado`.

    Output:
        str: cuál de los dos usuarios no se encontró.
    """
    falta_solicitante = not op.solicitante.encontrado
    falta_target = not op.target.encontrado
    if falta_solicitante and falta_target:
        return "No existe el usuario solicitante ni el usuario target."
    if falta_solicitante:
        return "No existe el usuario solicitante."
    if falta_target:
        return "No existe el usuario target."
    return "No se encontró la información solicitada en ADManager."


def _registro_500(op: OperacionReset) -> str:
    """Mensaje del estatus 500 del alta: error sin causa identificable en el log.

    Input:
        op (OperacionReset): operación resuelta (no se consulta ningún campo).

    Output:
        str: mensaje legible para la columna `resultado_final`.
    """
    return "Error desconocido."


def _registro_503(op: OperacionReset) -> str:
    """Mensaje del estatus 503 del alta: el bot validó todo bien y SAP fue quien falló.

    Input:
        op (OperacionReset): operación resuelta (no se consulta ningún campo).

    Output:
        str: mensaje legible para la columna `resultado_final`.
    """
    return (
        "Todas las validaciones fueron exitosas, "
        "pero el servicio del lado de SAP falló."
    )


RESOLVERS_REGISTER: dict[int, Callable[[OperacionReset], str]] = {
    200: _registro_200,
    202: _registro_202,
    208: _registro_208,
    400: _registro_400,
    401: _registro_401,
    403: _registro_403,
    404: _registro_404,
    500: _registro_500,
    503: _registro_503,
}

# Qué tabla de resolvers le toca a cada endpoint. Un endpoint que no esté aquí usa la del
# reseteo, que es la que existía antes de que el proceso reportara dos servicios.
RESOLVERS_POR_ENDPOINT: dict[str, dict[int, Callable[[OperacionReset], str]]] = {
    ENDPOINT_REGISTER: RESOLVERS_REGISTER,
}


def resolvers_de(endpoint: str) -> dict[int, Callable[[OperacionReset], str]]:
    """Devuelve la tabla de resolvers que le corresponde a un endpoint.

    Input:
        endpoint (str): endpoint del que salió la operación.

    Output:
        dict[int, Callable[[OperacionReset], str]]: `RESOLVERS_REGISTER` para el alta de
        usuarios, `RESOLVERS` para todo lo demás.
    """
    return RESOLVERS_POR_ENDPOINT.get(endpoint, RESOLVERS)


def resolver_resultado(op: OperacionReset) -> str:
    """Despacha la operación al resolver de su código HTTP y devuelve el mensaje humano.

    El mismo código significa cosas distintas en cada endpoint, así que primero se elige la
    tabla por `op.endpoint` y después la función por `op.status`. Añadir un código nuevo es
    añadir una función y una entrada en la tabla que toque: el resto del proceso no cambia.

    Input:
        op (OperacionReset): operación resuelta; el despacho se hace por `op.endpoint` y
            `op.status`.

    Output:
        str: mensaje de la columna `resultado_final`; si el código no tiene resolver
        registrado, un texto explícito de "sin regla de negocio definida".
    """
    resolver = resolvers_de(op.endpoint).get(op.status)
    if resolver is None:
        return f"Estatus HTTP {op.status} sin regla de negocio definida."
    return resolver(op)
