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
# Sólo se reportan los reseteos de ADManager; /v2/sap/register_user se ignora.
ENDPOINT_OBJETIVO = "users_admin/resetuser"
SISTEMA = "ADManager"
ACCION = "reset_password"

# Endpoints que el bot puede registrar. Uno fuera de esta lista no es un error, pero sí
# algo que hay que revisar: puede ser un servicio nuevo que también deba reportarse.
ENDPOINTS_CONOCIDOS = ("users_admin/resetuser", "sap/register_user")

# Namespace fijo => uuid5 estable entre ejecuciones y entre máquinas.
UUID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "tabla_reporte_bot")

OU_BLOQUEADA = "oat/cedis/by"  # ya normalizada
MARCADOR_CORPORATIVO = "corporativo"  # ya normalizado
PREFIJOS_PRIVILEGIADOS = ("gerente", "admin")
VALORES_NULOS_AD = {"", "-", "<not set>", "none"}

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
