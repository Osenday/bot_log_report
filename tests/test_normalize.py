"""Pruebas de las comparaciones de negocio contra los datos inconsistentes de ADManager."""

import pytest

from src.normalize import (
    es_corporativo,
    es_valor_nulo,
    misma_oficina,
    norm,
    quitar_acentos,
    tiene_privilegios,
)


def test_norm_baja_a_minusculas_y_colapsa_espacios():
    assert norm("CORPORATIVO") == norm("Corporativo") == "corporativo"
    assert norm("  Oficina   Central  ") == "oficina central"
    assert norm(None) == ""


def test_quitar_acentos():
    assert quitar_acentos("México") == "Mexico"
    assert quitar_acentos("Panificadora Producción") == "Panificadora Produccion"


@pytest.mark.parametrize("valor", ["", "-", "<not set>", "NONE", "  "])
def test_marcadores_de_sin_dato_de_admanager(valor):
    assert es_valor_nulo(valor)


def test_un_valor_real_no_es_nulo():
    assert not es_valor_nulo("0001")


@pytest.mark.parametrize(
    "oficina", ["CORPORATIVO", "Corporativo", "Oficina Corporativo"]
)
def test_corporativo_sin_importar_mayusculas(oficina):
    assert es_corporativo(oficina)


def test_una_tienda_no_es_corporativo():
    assert not es_corporativo("0001")


@pytest.mark.parametrize(
    "descripcion",
    [
        "Gerente Tienda",
        "GERENTE DE TIENDA",
        "Administrador De Sistemas",
        "admin sistemas",
    ],
)
def test_descripciones_con_privilegios(descripcion):
    assert tiene_privilegios(descripcion)


@pytest.mark.parametrize(
    "descripcion", ["Cajero", "Surtidor Ropa Y Variedades", "", "Mozo"]
)
def test_descripciones_sin_privilegios(descripcion):
    assert not tiene_privilegios(descripcion)


def test_misma_oficina_compara_la_cadena_completa():
    assert misma_oficina("0001", "0001")
    assert not misma_oficina("0001", "0002")


def test_el_orden_de_las_palabras_hace_distintas_dos_oficinas():
    # Es la misma oficina física, pero el bot no reordena palabras: devolvió 403 para
    # este par. Ver COMPARAR_OFICINA_POR_TOKENS en config.py.
    assert not misma_oficina("Cedis 5687 Salinas", "Cedis Salinas 5687")
