"""Constantes de negocio, rutas y esquema de salida del proceso.

Es el único lugar donde viven los valores que el negocio puede querer cambiar: el endpoint
que se reporta, las reglas de ADManager, la zona horaria y las columnas del reporte.
Ningún otro módulo debe llevar estos valores incrustados: cambiar una regla debe ser
cambiar una constante aquí.
"""

import os
import uuid
from pathlib import Path

# --- Rutas ---------------------------------------------------------------
# La raíz se deduce de la ubicación de este archivo (src/config.py -> raíz del proyecto),
# de modo que el proceso funciona sin importar desde qué directorio se invoque. La variable
# de entorno BOT_LOG_REPORT_ROOT permite apuntar a otro árbol, útil para pruebas.
PROJECT_ROOT = Path(
    os.environ.get("BOT_LOG_REPORT_ROOT", Path(__file__).resolve().parents[1])
)

RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
REPORTS_DIR = PROJECT_ROOT / "reports"
REPORT_PATH = REPORTS_DIR / "tabla_reporte_bot.csv"

PATRON_LOG = "*.log"
PREFIJO_STAGING = "resetuser_"
FORMATO_FECHA = "%Y-%m-%d"

# --- Reglas de negocio ---------------------------------------------------
# Los dos servicios del bot que se pueden reportar. Cuál de ellos entra en la tabla lo
# decide quien ejecuta el proceso con `--endpoint`; por defecto sólo los reseteos, que es
# el comportamiento con el que se construyó el reporte histórico.
ENDPOINT_RESET = "users_admin/resetuser"
ENDPOINT_REGISTER = "sap/register_user"

# Nombre anterior del endpoint de reseteo. Se conserva porque `enrich.enriquecer()` lo usa
# como valor por omisión cuando nadie le pasa una selección.
ENDPOINT_OBJETIVO = ENDPOINT_RESET

SISTEMA = "ADManager"
ACCION = "reset_password"

# Etiquetas que acepta `--endpoint` en la terminal.
SELECCION_RESET = "reset_user"
SELECCION_REGISTER = "register_user"
SELECCION_TODOS = "todos"
SELECCION_POR_DEFECTO = SELECCION_RESET

# Qué endpoints del log entran al reporte con cada etiqueta.
ENDPOINTS_POR_SELECCION = {
    SELECCION_RESET: (ENDPOINT_RESET,),
    SELECCION_REGISTER: (ENDPOINT_REGISTER,),
    SELECCION_TODOS: (ENDPOINT_RESET, ENDPOINT_REGISTER),
}

# Cada selección escribe su propio staging: así reprocesar un día con otra selección no
# pisa el archivo intermedio de la anterior.
PREFIJOS_STAGING = {
    SELECCION_RESET: PREFIJO_STAGING,
    SELECCION_REGISTER: "registeruser_",
    SELECCION_TODOS: "operaciones_",
}

# Columnas `accion` y `sistema` del reporte, según el endpoint que originó la fila.
ACCIONES = {ENDPOINT_RESET: ACCION, ENDPOINT_REGISTER: "alta_usuario"}
SISTEMAS = {ENDPOINT_RESET: SISTEMA, ENDPOINT_REGISTER: "SAP"}

# Endpoints que el bot puede registrar. Uno fuera de esta lista no es un error, pero sí
# algo que hay que revisar: puede ser un servicio nuevo que también deba reportarse.
ENDPOINTS_CONOCIDOS = (ENDPOINT_RESET, ENDPOINT_REGISTER)

# Namespace fijo => uuid5 estable entre ejecuciones y entre máquinas.
UUID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "tabla_reporte_bot")

OU_BLOQUEADA = "oat/cedis/by"  # ya normalizada
MARCADOR_CORPORATIVO = "corporativo"  # ya normalizado
PREFIJOS_PRIVILEGIADOS = ("gerente", "admin")
VALORES_NULOS_AD = {"", "-", "<not set>", "none"}

# --- Reglas propias del alta de usuarios (sap/register_user) -------------
# Todos estos valores están ya normalizados (minúsculas y sin acentos), porque las
# comparaciones pasan antes por `normalize.norm()`: "señor" normalizado es "senor".
TRATAMIENTOS_VALIDOS = ("senor", "senora")

# El solicitante pertenece a City Club si su OU de ADManager lo dice: en los logs la OU es
# "OAT/Tiendas/City Club".
MARCADOR_CITY_CLUB = "city club"

# Puestos que sólo existen en Soriana, así que un solicitante que no sea de City Club no
# puede darlos de alta. Es una lista de negocio: ampliarla aquí no toca el resto del código.
PUESTOS_EXCLUSIVOS_SORIANA = ("supervisor mermas", "recibo tienda")

# El puesto que se pide en la URL (`job`) contra el que ya tiene el usuario objetivo en
# ADManager. El puesto real vive en DESCRIPTION ("Gerente Tienda", "Subgerente"), no en
# OFFICE, que es el número de tienda ("0113").
PUESTO_GERENTE = "gerente tienda"
PUESTO_SUBGERENTE = "subgerente tienda"
PREFIJO_GERENTE = "gerente"
PREFIJO_SUBGERENTE = "subgerente"

# SAP no devuelve un código propio cuando el usuario ya estaba dado de alta: lo dice en el
# texto de su respuesta ("El usuario ya existe en el sistema, favor de revisar.").
MARCADOR_USUARIO_EXISTENTE = "ya existe"

# ADManager es inconsistente con OFFICE: en los logs existe la misma oficina escrita como
# "Cedis 5687 Salinas" y como "Cedis Salinas 5687". Con este flag en True se tratan como
# iguales, pero el bot NO lo hace así: devolvió 403 para justamente ese par (operación
# 56a6ad8c62501c3a1b170d67785f458b). Como la tabla debe explicar la decisión que tomó el
# bot, se deja en False.
COMPARAR_OFICINA_POR_TOKENS = False

# Zona horaria de la columna `updated_at` (momento de carga de cada registro).
ZONA_HORARIA = "America/Mexico_City"

# --- Esquema de salida ---------------------------------------------------
COLUMNAS_REPORTE = [
    "id",
    "updated_at",
    "timestamp",
    "operation_id",
    "solicitante",
    "target",
    "accion",
    "sistema",
    "nombre_solicitante",
    "nombre_target",
    "oficina_solicitante",
    "oficina_target",
    "resultado_final",
]

# El staging no lleva updated_at (para ser determinista) y sí lleva status_http (para
# depurar y para las validaciones de cobertura).
COLUMNAS_STAGING = [c for c in COLUMNAS_REPORTE if c != "updated_at"] + ["status_http"]
