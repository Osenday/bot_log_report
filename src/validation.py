"""Validaciones de datos que corren dentro del proceso, en cada ejecución.

No confundir con `tests/`: aquellos comprueban que el *código* es correcto con datos fijos
y conocidos; estas comprueban que los *datos de hoy* son los esperados. Si un test falla,
se corrige el código; si falla una validación de aquí, hay que revisar el log de entrada.

Hay dos grupos:

- `validar_log()`      — contrato de la entrada: ¿el `.log` tiene la estructura acordada?
- `validar_staging()`  — invariantes de la salida: ¿la tabla resultante es coherente?

Cada uno devuelve una lista de `Hallazgo`. `revisar()` los registra y decide si el proceso
puede continuar. Las validaciones corren SIEMPRE antes de escribir en disco, para que un
log defectuoso no deje el reporte a medias.
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .config import (
    ENDPOINTS_CONOCIDOS,
    ENDPOINTS_POR_SELECCION,
    SELECCION_POR_DEFECTO,
)
from .outcomes import (
    MENSAJE_403_GENERICO,
    MENSAJE_403_REGISTER_GENERICO,
    resolvers_de,
)
from .parsers import SEARCH_RE, parse_entrada
from .reader import HEADER_RE, agrupar_operaciones

logger = logging.getLogger(__name__)

ERROR = "ERROR"  # el proceso se detiene sin escribir nada
AVISO = "AVISO"  # se registra y el proceso continúa


class ValidacionFallida(Exception):
    """Los datos no cumplen el contrato y el proceso no debe escribir nada."""


@dataclass(frozen=True)
class Hallazgo:
    """Un problema detectado en los datos.

    Campos:
        nivel (str): `ERROR` (detiene el proceso) o `AVISO` (sólo se registra).
        mensaje (str): descripción legible de lo que se encontró.
    """

    nivel: str
    mensaje: str


def validar_log(path: Path) -> list[Hallazgo]:
    """Comprueba que un `.log` siga la estructura acordada con el equipo del bot.

    Revisa que el archivo tenga contenido y encabezados reconocibles, que no haya líneas
    sueltas antes del primer registro, que cada operación tenga exactamente una línea de
    entrada, que los endpoints sean los conocidos y que las respuestas de ADManager vengan
    completas (un log truncado deja cuerpos JSON que no parsean).

    Input:
        path (Path): ruta al archivo `.log` crudo.

    Output:
        list[Hallazgo]: vacía si el log cumple el contrato.
    """
    hallazgos: list[Hallazgo] = []
    lineas = path.read_text(encoding="utf-8").splitlines()

    if not any(linea.strip() for linea in lineas):
        return [Hallazgo(ERROR, f"El log {path.name} está vacío")]

    # Líneas sueltas antes del primer encabezado: no pertenecen a ninguna operación.
    huerfanas = 0
    hay_encabezado = False
    for linea in lineas:
        if HEADER_RE.match(linea):
            hay_encabezado = True
        elif not hay_encabezado and linea.strip():
            huerfanas += 1

    if not hay_encabezado:
        return [
            Hallazgo(
                ERROR,
                f"El log {path.name} no tiene ninguna línea con el formato esperado",
            )
        ]
    if huerfanas:
        hallazgos.append(
            Hallazgo(AVISO, f"{huerfanas} líneas sueltas antes del primer encabezado")
        )

    sin_entrada = 0
    con_varias_entradas = 0
    endpoints_nuevos: set[str] = set()
    cuerpos_truncados = 0

    for operacion in agrupar_operaciones(path).values():
        entradas = [
            e for e in (parse_entrada(r.message) for r in operacion.records) if e
        ]
        if not entradas:
            sin_entrada += 1
        elif len(entradas) > 1:
            con_varias_entradas += 1

        for entrada in entradas:
            if not entrada["endpoint"].endswith(ENDPOINTS_CONOCIDOS):
                endpoints_nuevos.add(entrada["endpoint"])

        for rec in operacion.records:
            for m in SEARCH_RE.finditer(rec.message):
                try:
                    json.loads(m["body"].strip())
                except json.JSONDecodeError:
                    cuerpos_truncados += 1

    if sin_entrada:
        hallazgos.append(
            Hallazgo(AVISO, f"{sin_entrada} operaciones sin línea de entrada del bot")
        )
    if con_varias_entradas:
        hallazgos.append(
            Hallazgo(
                AVISO,
                f"{con_varias_entradas} operaciones con más de una línea de entrada",
            )
        )
    if endpoints_nuevos:
        hallazgos.append(
            Hallazgo(
                AVISO,
                f"Endpoints no reconocidos: {', '.join(sorted(endpoints_nuevos))}",
            )
        )
    if cuerpos_truncados:
        hallazgos.append(
            Hallazgo(
                AVISO,
                f"{cuerpos_truncados} respuestas de ADManager truncadas o ilegibles "
                "(los usuarios afectados quedan como 'no encontrado')",
            )
        )
    return hallazgos


def validar_staging(
    staging: pd.DataFrame, fecha: str, seleccion: str = SELECCION_POR_DEFECTO
) -> list[Hallazgo]:
    """Comprueba que la tabla producida para un día sea coherente antes de guardarla.

    Input:
        staging (pd.DataFrame): tabla de staging de un día.
        fecha (str): fecha procesada, sólo para los mensajes.
        seleccion (str): endpoints que se pidieron reportar; decide contra qué reglas de
            negocio se comprueba la cobertura de códigos HTTP.

    Output:
        list[Hallazgo]: vacía si la tabla cumple todas las invariantes.
    """
    if staging.empty:
        return [
            Hallazgo(
                AVISO,
                f"{fecha}: el log no contiene ninguna operación de {seleccion}",
            )
        ]

    hallazgos: list[Hallazgo] = []

    if not staging["id"].is_unique:
        repetidos = staging["id"].duplicated().sum()
        hallazgos.append(
            Hallazgo(ERROR, f"{fecha}: {repetidos} ids repetidos en la tabla")
        )

    sin_resultado = int((staging["resultado_final"] == "").sum())
    if sin_resultado:
        hallazgos.append(
            Hallazgo(ERROR, f"{fecha}: {sin_resultado} filas sin resultado_final")
        )

    # Un código nuevo significa una regla de negocio que todavía no está implementada. Cada
    # endpoint tiene su propia tabla de códigos, así que se comprueba contra la unión de las
    # que entraron en esta selección.
    codigos_conocidos: set[int] = set()
    for endpoint in ENDPOINTS_POR_SELECCION.get(seleccion, ()):
        codigos_conocidos |= set(resolvers_de(endpoint))
    desconocidos = sorted(set(staging["status_http"]) - codigos_conocidos)
    if desconocidos:
        hallazgos.append(
            Hallazgo(
                AVISO,
                f"{fecha}: códigos HTTP sin regla definida: "
                f"{', '.join(str(c) for c in desconocidos)}",
            )
        )

    # Un 403 sin causa identificada apunta a una validación del bot que no modelamos.
    genericos = int(
        staging["resultado_final"]
        .isin([MENSAJE_403_GENERICO, MENSAJE_403_REGISTER_GENERICO])
        .sum()
    )
    if genericos:
        hallazgos.append(
            Hallazgo(
                AVISO, f"{fecha}: {genericos} operaciones 403 sin causa identificada"
            )
        )

    # Si el reseteo tuvo éxito, ADManager devolvió a los dos usuarios: faltar datos es
    # señal de que el log llegó incompleto.
    exitosas = staging[staging["status_http"] == 200]
    incompletas = exitosas[
        (exitosas["nombre_solicitante"] == "") | (exitosas["nombre_target"] == "")
    ]
    if len(incompletas):
        hallazgos.append(
            Hallazgo(
                AVISO,
                f"{fecha}: {len(incompletas)} operaciones exitosas sin datos completos "
                "de ADManager",
            )
        )
    return hallazgos


def revisar(hallazgos: list[Hallazgo], strict: bool = False) -> None:
    """Registra los hallazgos y detiene el proceso si alguno lo justifica.

    Input:
        hallazgos (list[Hallazgo]): resultado de `validar_log()` o `validar_staging()`.
        strict (bool): si es `True`, cualquier aviso también detiene el proceso. Útil en la
            ejecución automatizada, donde se prefiere no cargar nada antes que cargar datos
            dudosos.

    Output:
        None. Lanza `ValidacionFallida` si hay hallazgos que impiden continuar.
    """
    for hallazgo in hallazgos:
        if hallazgo.nivel == ERROR:
            logger.error(hallazgo.mensaje)
        else:
            logger.warning(hallazgo.mensaje)

    bloqueantes = hallazgos if strict else [h for h in hallazgos if h.nivel == ERROR]
    if bloqueantes:
        detalle = "; ".join(h.mensaje for h in bloqueantes)
        raise ValidacionFallida(detalle)
