"""Pruebas de los mensajes de `resultado_final`, uno por código HTTP.

Es la única cobertura de los códigos 202 y 429, que no aparecen en ningún log real.
"""

from src.enrich import OperacionReset, Usuario
from src.outcomes import RESOLVERS, resolver_resultado

GERENTE = Usuario("gerencia001", True, "Ana Ruiz", "0001", "Gerente Tienda")
EMPLEADO = Usuario(
    "001000001", True, "Luis Paz", "0001", "Cajero", "Tienda/POS/Usuarios"
)


def operacion(status, solicitante=GERENTE, target=EMPLEADO, adm_raw=None):
    """Arma una OperacionReset mínima para probar un resolver."""
    return OperacionReset(
        operation_id="prueba",
        timestamp="2026-01-01T00:00:00Z",
        status=status,
        solicitante=solicitante,
        target=target,
        adm_raw=adm_raw,
    )


def test_todos_los_codigos_de_la_especificacion_tienen_resolver():
    assert set(RESOLVERS) == {200, 202, 403, 404, 429, 500, 503, 504}


def test_200_es_exito():
    assert resolver_resultado(operacion(200)) == "Proceso exitoso."


def test_202_menciona_corporativo():
    assert "Corporativo" in resolver_resultado(operacion(202))


def test_403_por_oficinas_distintas():
    otra_oficina = Usuario("002000001", True, "Eva Lima", "0002", "Cajero")
    mensaje = resolver_resultado(operacion(403, target=otra_oficina))
    assert "misma oficina" in mensaje


def test_403_por_falta_de_privilegios():
    cajero = Usuario("caja001", True, "Sol Diaz", "0001", "Cajero General")
    mensaje = resolver_resultado(operacion(403, solicitante=cajero))
    assert "gerente ni administrador" in mensaje


def test_403_por_la_ou_bloqueada():
    en_cedis = Usuario("001000004", True, "Ivo Rey", "0001", "Surtidor", "OAT/Cedis/BY")
    mensaje = resolver_resultado(operacion(403, target=en_cedis))
    assert "OAT/Cedis/BY" in mensaje


def test_404_target_no_encontrado():
    perdido = Usuario("noexiste", encontrado=False)
    assert "objetivo no se encontró" in resolver_resultado(
        operacion(404, target=perdido)
    )


def test_404_solicitante_no_encontrado():
    perdido = Usuario("noexiste", encontrado=False)
    mensaje = resolver_resultado(operacion(404, solicitante=perdido))
    assert "solicitante no se encontró" in mensaje


def test_404_ningun_usuario_encontrado():
    perdido = Usuario("noexiste", encontrado=False)
    mensaje = resolver_resultado(operacion(404, solicitante=perdido, target=perdido))
    assert mensaje == "Ningún usuario se encontró en ADManager."


def test_429_menciona_los_tokens():
    assert "tokens" in resolver_resultado(operacion(429))


def test_500_es_critico():
    assert "crítico" in resolver_resultado(operacion(500)).lower()


def test_503_concatena_el_mensaje_exacto_de_admanager():
    adm = {
        "status": 200,
        "body": [{"statusMessage": "No such user matched.", "status": "0"}],
    }
    mensaje = resolver_resultado(operacion(503, adm_raw=adm))
    assert "No such user matched." in mensaje


def test_503_sin_detalle_usa_solo_el_mensaje_base():
    mensaje = resolver_resultado(operacion(503))
    assert "Respuesta de ADManager" not in mensaje


def test_504_menciona_el_timeout():
    assert "Timeout" in resolver_resultado(operacion(504))


def test_un_codigo_nuevo_no_rompe_el_proceso():
    mensaje = resolver_resultado(operacion(418))
    assert "sin regla de negocio definida" in mensaje
