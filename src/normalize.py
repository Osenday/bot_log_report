"""Normalización de texto y comparaciones de negocio contra datos de ADManager.

ADManager devuelve los mismos valores con acentos, mayúsculas y espacios distintos, así que
toda comparación de negocio pasa primero por `norm()`. Este módulo no conoce el formato del
log: sólo compara cadenas.
"""

import unicodedata

from .config import (
    COMPARAR_OFICINA_POR_TOKENS,
    MARCADOR_CITY_CLUB,
    MARCADOR_CORPORATIVO,
    PREFIJO_GERENTE,
    PREFIJO_SUBGERENTE,
    PREFIJOS_PRIVILEGIADOS,
    TRATAMIENTOS_VALIDOS,
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


def es_city_club(ou_name: str) -> bool:
    """Indica si un usuario pertenece a City Club según su OU de ADManager.

    En los logs la OU de esos usuarios es "OAT/Tiendas/City Club"; se busca la subcadena
    normalizada para que el nombre exacto de la OU pueda cambiar sin romper la regla.

    Input:
        ou_name (str): valor crudo del campo OU_NAME de ADManager.

    Output:
        bool: `True` si la OU contiene el marcador de City Club.
    """
    return MARCADOR_CITY_CLUB in norm(ou_name)


def tratamiento_valido(tratamiento: str) -> bool:
    """Indica si el tratamiento que llegó en la URL es uno de los que acepta el bot.

    Input:
        tratamiento (str): valor crudo del parámetro `treatment` (por ejemplo "señora").

    Output:
        bool: `True` si, ya normalizado, es "senor" o "senora".
    """
    return norm(tratamiento) in TRATAMIENTOS_VALIDOS


def es_numero_empleado(valor: str) -> bool:
    """Indica si el identificador del usuario objetivo es un número de empleado.

    El bot devuelve 400 cuando `target_employee_id` no es numérico (en los logs llegó a
    venir un `sAMAccountName` como "Caphum165").

    Input:
        valor (str): valor crudo del parámetro `target_employee_id`.

    Output:
        bool: `True` si el valor tiene contenido y todos sus caracteres son dígitos.
    """
    return str(valor).strip().isdigit()


def es_gerente(descripcion: str) -> bool:
    """Indica si el puesto que el usuario ya tiene en ADManager es de gerente.

    Se compara con `startswith` y no con `in` justamente para que "Subgerente" no cuente
    como gerente.

    Input:
        descripcion (str): valor crudo del campo DESCRIPTION de ADManager.

    Output:
        bool: `True` si la descripción normalizada empieza con "gerente".
    """
    return norm(descripcion).startswith(PREFIJO_GERENTE)


def es_subgerente(descripcion: str) -> bool:
    """Indica si el puesto que el usuario ya tiene en ADManager es de subgerente.

    Input:
        descripcion (str): valor crudo del campo DESCRIPTION de ADManager.

    Output:
        bool: `True` si la descripción normalizada empieza con "subgerente".
    """
    return norm(descripcion).startswith(PREFIJO_SUBGERENTE)
