"""Configuración común de las pruebas.

Las pruebas nunca tocan `data/` ni `reports/`: trabajan sobre un árbol temporal que contiene
un único log sintético (`fixtures/2026-01-01.log`) con un caso por cada código HTTP.

`BOT_LOG_REPORT_ROOT` se define ANTES de importar `src`, porque `src/config.py` resuelve las
rutas en el momento de importarse. pytest carga este archivo antes que los módulos de
prueba, así que este es el único punto donde se puede hacer.
"""

import os
import shutil
import tempfile
from pathlib import Path

import pytest

FECHA = "2026-01-01"
FIXTURES = Path(__file__).parent / "fixtures"

RAIZ_TEMPORAL = Path(tempfile.mkdtemp(prefix="bot_log_report_pruebas_"))
(RAIZ_TEMPORAL / "data" / "raw").mkdir(parents=True)
shutil.copy(FIXTURES / f"{FECHA}.log", RAIZ_TEMPORAL / "data" / "raw")
os.environ["BOT_LOG_REPORT_ROOT"] = str(RAIZ_TEMPORAL)


@pytest.fixture(scope="session", autouse=True)
def borrar_arbol_temporal():
    """Elimina el árbol de pruebas cuando termina la sesión.

    Input:
        Ninguno (fixture de sesión, automática).

    Output:
        None.
    """
    yield
    shutil.rmtree(RAIZ_TEMPORAL, ignore_errors=True)


@pytest.fixture(autouse=True)
def salidas_limpias():
    """Deja cada prueba con el reporte y el staging vacíos, antes y después.

    Input:
        Ninguno (fixture automática en cada prueba).

    Output:
        None.
    """
    from src.config import PROCESSED_DIR, REPORT_PATH

    def limpiar():
        REPORT_PATH.unlink(missing_ok=True)
        if PROCESSED_DIR.is_dir():
            for archivo in PROCESSED_DIR.glob("*.csv"):
                archivo.unlink()

    limpiar()
    yield
    limpiar()


@pytest.fixture
def log_fixture():
    """Ruta del log sintético de pruebas.

    Input:
        Ninguno.

    Output:
        Path: ruta a `2026-01-01.log` dentro del árbol temporal.
    """
    from src.discovery import ruta_log

    return ruta_log(FECHA)
