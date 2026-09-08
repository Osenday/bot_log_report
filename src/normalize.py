"""Normalización de texto y comparaciones de negocio contra datos de ADManager.

ADManager devuelve los mismos valores con acentos, mayúsculas y espacios distintos, así que
toda comparación de negocio pasa primero por `norm()`. Este módulo no conoce el formato del
log: sólo compara cadenas.
"""

import unicodedata

from .config import (
    COMPARAR_OFICINA_POR_TOKENS,
    MARCADOR_CORPORATIVO,
    PREFIJOS_PRIVILEGIADOS,
    VALORES_NULOS_AD,
)


def quitar_acentos(texto: str) -> str:
    """Elimina los acentos de un texto mediante la descomposición NFKD.

    NFKD separa cada carácter acentuado en letra base + marca diacrítica y aplana las
    variantes de estilo; después se descartan las marcas combinantes.

    Input:
        texto (str): cadena original, con o sin acentos.

    Output:
        str: la misma cadena sin marcas diacríticas (conserva mayúsculas y espacios).
    """
    descompuesto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in descompuesto if not unicodedata.combining(c))


def norm(valor: object) -> str:
    """Normaliza un valor para poder compararlo: minúsculas, sin acentos y sin espacios
    sobrantes. Es la base de toda comparación de negocio contra datos de ADManager.

    Input:
        valor (object): cualquier valor; se convierte a `str`. `None` se trata como vacío.

    Output:
        str: texto en minúsculas, sin acentos y con espacios internos colapsados a uno.
    """
    if valor is None:
        return ""
    return " ".join(quitar_acentos(str(valor)).casefold().split())


def es_valor_nulo(valor: object) -> bool:
    """Indica si un valor de ADManager representa "sin dato".

    ADManager usa indistintamente '', '-', '<not set>' y 'none' como ausencia de dato.

    Input:
        valor (object): valor crudo tal como llegó de ADManager.

    Output:
        bool: `True` si el valor normalizado está en `VALORES_NULOS_AD`.
    """
    return norm(valor) in VALORES_NULOS_AD


def misma_oficina(a: str, b: str) -> bool:
    """Determina si dos oficinas son la misma según el criterio configurado.

    Con `COMPARAR_OFICINA_POR_TOKENS = False` compara las cadenas normalizadas tal cual
    (replica el comportamiento del bot); con `True` compara los conjuntos de palabras, de
    modo que "Cedis 5687 Salinas" y "Cedis Salinas 5687" se consideran iguales.

    Input:
        a (str): oficina del usuario solicitante (campo OFFICE).
        b (str): oficina del usuario objetivo (campo OFFICE).

    Output:
        bool: `True` si ambas oficinas se consideran la misma.
    """
    na, nb = norm(a), norm(b)
    if COMPARAR_OFICINA_POR_TOKENS:
        return sorted(na.split()) == sorted(nb.split())
    return na == nb


def es_corporativo(oficina: str) -> bool:
    """Indica si una oficina pertenece a Corporativo (causa del estatus 202).

    Busca la subcadena normalizada 'corporativo', por lo que atrapa "Corporativo",
    "CORPORATIVO" y variantes con acentos o espacios extra.

    Input:
        oficina (str): valor crudo del campo OFFICE de ADManager.

    Output:
        bool: `True` si la oficina contiene el marcador de Corporativo.
    """
    return MARCADOR_CORPORATIVO in norm(oficina)


def tiene_privilegios(descripcion: str) -> bool:
    """Indica si el solicitante es gerente o administrador de sistemas.

    Basta con que el campo `DESCRIPTION` de ADManager empiece con "gerente" o "admin"
    (ya normalizado), según la regla de negocio del estatus 403.

    Input:
        descripcion (str): valor crudo del campo DESCRIPTION de ADManager.

    Output:
        bool: `True` si la descripción normalizada empieza con alguno de los prefijos de
        `PREFIJOS_PRIVILEGIADOS`.
    """
    return norm(descripcion).startswith(PREFIJOS_PRIVILEGIADOS)
