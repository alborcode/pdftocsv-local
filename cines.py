# -*- coding: utf-8 -*-
"""
Script para extraer datos de cines desde el PDF del inventario IPCE.

Este script usa un enfoque posicional robusto:
1. Extrae palabras con coordenadas (x0, x1, top) usando pdfplumber.
2. Agrupa palabras en filas usando la coordenada Y.
3. Identifica lineas de CCAA, AYUNTAMIENTO y datos de cines.
4. Realiza forward-fill de comunidad y municipio.
5. Extrae ano de inauguracion y numero de pantallas.

Salida: CSV con columnas: municipio, nombre_cine, numero_pantallas, 
         fecha_inaguracion, direccion, comunidad
"""

import csv
import re
from collections import defaultdict
from pathlib import Path

import pdfplumber

# Rutas
PDF_PATH = Path("data/data_pdf/cines-listado-julio-2021.pdf")
OUTPUT_PATH = Path("data/data_csv/cines.csv")

# Lista de comunidades autonomas (sin tildes para comparacion)
# Normalizar: CATALUNYA -> CATALUNA, EUSKADI -> PAIS VASCO, ILLES BALEARES -> BALEARES
COMUNIDADES = {
    "ANDALUCIA", "ARAGON", "ASTURIAS", "BALEARES", "CANARIAS", "CANTABRIA",
    "CASTILLA-LA MANCHA", "CASTILLA Y LEON", "CATALUNA", "COMUNIDAD VALENCIANA",
    "EXTREMADURA", "GALICIA", "MADRID", "MURCIA", "NAVARRA", "PAIS VASCO",
    "LA RIOJA", "CEUTA", "MELILLA"
}

# Mapeo de variantes a comunidad estandar
VARIANTES = {
    "CATALUNYA": "CATALUNA",
    "EUSKADI": "PAIS VASCO",
    "ILLES BALEARES": "BALEARES",
    "ILLES BALEARS": "BALEARES",
}

# Comunidades que aparecen divididas en el PDF
# El orden importa: buscar las mas largas primero
# Nota: el texto normalizado puede tener las palabras pegadas (CASTILLALA MANCHA)
COMUNIDADES_PARCIALES = [
    ("CASTILLA Y LEON", "CASTILLA Y LEON"),
    ("CASTILLALA MANCHA", "CASTILLA-LA MANCHA"),  # Sin espacio por el guion eliminado
    ("CASTILLA LA MANCHA", "CASTILLA-LA MANCHA"),
    ("CASTILLA", ["CASTILLA-LA MANCHA", "CASTILLA Y LEON"]),
    ("ILLES BALEARES", "BALEARES"),
    ("ILLES BALEARS", "BALEARES"),
    ("ILLESBALEARES", "BALEARES"),  # Sin espacio
    ("ILLESBALEARS", "BALEARS"),
]

# Funcion para normalizar texto (quitar tildes)
def normalize(text):
    """Quita tildes, guiones y pasa a mayusculas."""
    if not text:
        return ""
    #替换带重音符号的字符为基本拉丁字母
    replacements = {
        'Á': 'A', 'É': 'E', 'Í': 'I', 'Ó': 'O', 'Ú': 'U', 'Ü': 'U',
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u', 'ü': 'u',
        'Ñ': 'N', 'ñ': 'n'
    }
    result = text.upper()
    for accented, plain in replacements.items():
        result = result.replace(accented, plain)
    # Eliminar guiones (incluido el guión bajo unicode ‐)
    result = result.replace('-', '').replace('‐', '').replace('‑', '').replace('–', '').replace('—', '')
    return result

# Posiciones X de las columnas (ajustadas segun analisis real del PDF)
COLS = {
    "ccaa": (25, 70),      # CCAA - comunidad autonoma
    "ayto": (70, 160),     # AYUNTAMIENTO - municipio
    "denom": (160, 295),   # DENOMINACION - nombre del cine
    "direc": (295, 450),   # DIRECCION - calle
    "fecha1": (450, 480),  # FECHA INAUGURACION
    "fecha2": (480, 560),  # FECHA CLAUSURA/REFORMA
    "autor": (560, 700),   # AUTOR/ES
    "pantallas": (780, 800)  # NUMERO PANTALLAS
}


def agrupar_palabras(palabras):
    """Agrupa palabras en filas por coordenada Y.
    
    Devuelve lista de tuplas: (top, palabras_fila)
    Usa tolerancia de 3 puntos para agrupar palabras que están muy cerca verticalmente.
    """
    if not palabras:
        return []
    
    # Obtener todos los tops únicos ordenados
    tops_unicos = sorted(set(p["top"] for p in palabras))
    
    # Agrupar tops que están dentro de 3 puntos
    grupos = []
    grupo_actual = [tops_unicos[0]]
    
    for i in range(1, len(tops_unicos)):
        if tops_unicos[i] - tops_unicos[i-1] <= 3:
            # Mismo grupo
            grupo_actual.append(tops_unicos[i])
        else:
            # Nuevo grupo
            grupos.append(grupo_actual)
            grupo_actual = [tops_unicos[i]]
    
    # Agregar el último grupo
    grupos.append(grupo_actual)
    
    # Crear filas usando el promedio del grupo como top
    filas = []
    for grupo in grupos:
        top_promedio = sum(grupo) / len(grupo)
        palabras_fila = [p for p in palabras if abs(p["top"] - grupo[0]) <= 3 or 
                        any(abs(p["top"] - g) <= 3 for g in grupo)]
        filas.append((top_promedio, sorted(palabras_fila, key=lambda x: x["x0"])))
    
    return filas


def es_continuacion_municipio(texto):
    """Determina si el texto parece ser una continuacion del nombre del municipio.
    
    Returns True si el texto parece ser un nombre de lugar (sin digitos)
    """
    if not texto:
        return False
    
    t = texto.strip().upper()
    
    # No debe ser una comunidad autonoma
    if normalize(t) in COMUNIDADES:
        return False
    
    # No debe tener digitos
    if re.search(r'\d', texto):
        return False
    
    # Debe tener sentido como continuacion de municipio
    # Aceptar cualquier palabra que parezca un nombre de lugar (title case o upper case)
    palabras = texto.split()
    if len(palabras) <= 3:
        # Aceptar si parece un nombre de lugar (primera letra mayuscula)
        if texto.title() == texto or texto.upper() == texto:
            return True
    
    return False


def asignar_columnas(fila_palabras):
    """Asigna palabras a columnas segun posicion X.
    
    Devuelve un diccionario con las columnas y también el texto de la columna autor
    para búsqueda alternativa de número de pantallas.
    """
    resultado = {k: "" for k in COLS}
    for p in fila_palabras:
        x = (p["x0"] + p["x1"]) / 2
        if COLS["ccaa"][0] <= x <= COLS["ccaa"][1]:
            resultado["ccaa"] += " " + p["text"]
        elif COLS["ayto"][0] <= x <= COLS["ayto"][1]:
            resultado["ayto"] += " " + p["text"]
        elif COLS["denom"][0] <= x <= COLS["denom"][1]:
            resultado["denom"] += " " + p["text"]
        elif COLS["direc"][0] <= x <= COLS["direc"][1]:
            resultado["direc"] += " " + p["text"]
        elif COLS["fecha1"][0] <= x <= COLS["fecha1"][1]:
            resultado["fecha1"] += " " + p["text"]
        elif COLS["fecha2"][0] <= x <= COLS["fecha2"][1]:
            resultado["fecha2"] += " " + p["text"]
        elif COLS["autor"][0] <= x <= COLS["autor"][1]:
            resultado["autor"] += " " + p["text"]
        elif COLS["pantallas"][0] <= x <= COLS["pantallas"][1]:
            resultado["pantallas"] += " " + p["text"]
    
    resultado = {k: v.strip() for k, v in resultado.items()}
    
    # Verificar si la columna denom tiene contenido que parece continuacion de municipio
    # Solo si ayto tiene contenido en ESTA fila
    if resultado["denom"] and resultado["ayto"] and es_continuacion_municipio(resultado["denom"]):
        # Mover de denom a ayto
        resultado["ayto"] = (resultado["ayto"] + " " + resultado["denom"]).strip()
        resultado["denom"] = ""
    
    return resultado


def es_encabezado(fila):
    """Es encabezado?"""
    t = " ".join(fila.values()).upper()
    return "CCAA" in t or "DENOMINACION" in t


def es_pie(fila):
    """Es pie de pagina?"""
    t = " ".join(fila.values()).upper()
    return "MARTES" in t or "PAGINA" in t


def es_ccaa(fila, ccaa_actual=""):
    """Es una fila de comunidad autonoma?
    
    Una fila es CCAA cuando:
    - La columna CCAA o AYTO tiene una comunidad autonoma conocida
    - La fila tiene poco contenido (solo la comunidad, o comunidad + muy poco mas)
    
    IMPORTANTE: No buscar en denom o direc porque "Andalucía" en direcciones
    se confunde con la comunidad.
    
    EXCEPCION: Si el texto es igual a la CCAA actual (ej: "MADRID" cuando ya estamos en MADRID),
    entonces es un municipio, no una nueva CCAA.
    """
    # Combinar solo las columnas CCAA y AYTO (no denom ni direc)
    texto_completo = normalize(" ".join([fila[c].strip() for c in ["ccaa", "ayto"]]))
    
    # Verificar que la fila tenga poco contenido
    total_len = sum(len(fila[c].strip()) for c in ["ccaa", "ayto"])
    if total_len >= 50:
        return False
    
    # EXCEPCION: Si el texto es exactamente la CCAA actual, NO es nueva CCAA
    # (ej: "MADRID" municipio cuando CCAA=MADRID)
    # Usar strip() para quitar espacios al inicio/final
    if ccaa_actual and texto_completo.strip() == ccaa_actual:
        return False
    
    # Buscar comunidades completas
    for comunidad in COMUNIDADES:
        if comunidad in texto_completo:
            return True
    
    # Buscar comunidades parciales
    for parcial, resultado in COMUNIDADES_PARCIALES:
        if parcial in texto_completo:
            return True
    
    return False


def es_ayto(fila, ccaa_actual=""):
    """Es una fila de municipio?
    
    Una fila es AYUNTAMIENTO cuando:
    - No tiene CCAA (columna ccaa vacia)
    - La columna ayto tiene texto sin digitos
    - No es una direccion (no tiene C/, Avda, etc.)
    - No es una comunidad autonoma (EXCEPTO si es igual a la CCAA actual, ej: Madrid municipio)
    """
    c = normalize(fila["ccaa"].strip())
    a = fila["ayto"].strip()
    
    # Si hay CCAA, no es ayto
    if c:
        return False
    
    if not a:
        return False
    
    # No debe ser una comunidad autonoma
    # EXCEPCION: Si es igual a la CCAA actual (ej: "MADRID" municipio cuando CCAA=MADRID)
    a_norm = normalize(a)
    if a_norm in COMUNIDADES and a_norm != ccaa_actual:
        return False
    
    # No debe tener digitos (excepto s/n que a veces aparece)
    if re.search(r"\d", a) and "s/n" not in a.lower():
        return False
    
    # No debe ser muy largo (mas de 6 palabras es sospechoso)
    if len(a.split()) > 6:
        return False
    
    # No debe ser una direccion
    if re.search(r"\b(C/|AVDA|PL\.|PZA|S/N)\b", a, re.IGNORECASE):
        return False
    
    # Debe tener sentido como nombre de municipio
    # (generalmente 1-3 palabras, primera letra mayuscula)
    palabras = a.split()
    if len(palabras) == 0:
        return False
    
    # Aceptar si tiene 1-3 palabras o si esta en mayusculas
    if len(palabras) <= 3:
        return True
    
    # Para palabras multiples, verificar que parezca un nombre de lugar
    return True


def es_dato(fila):
    """Es una fila de datos de cine?
    
    Una fila es de datos cuando:
    - Tiene contenido en las columnas denom (nombre del cine) o direc (direccion)
    - No es encabezado ni pie de pagina
    - No es CCAA ni AYUNTAMIENTO
    """
    c = fila["ccaa"].strip()
    a = fila["ayto"].strip()
    d = fila["denom"].strip()
    r = fila["direc"].strip()
    
    # Si es CCAA o AYUNTAMIENTO, no es dato
    if c or a:
        return False
    
    # Debe tener denom o direccion
    if not d and not r:
        return False
    
    # Verificar que no sea encabezado/pie
    t = (d + " " + r).upper()
    if any(p in t for p in ["INVENTARIO", "IPCE", "CCAA", "AYUNTAMIENTO", "PAGINA"]):
        return False
    
    return True


def extraer_ano(texto):
    """Extrae ano de inauguracion.
    
    El ano es el primer numero de 4 digitos encontrado en el texto.
    """
    if not texto:
        return ""
    # Buscar el primer numero de 4 digitos
    anos = re.findall(r"\b(\d{4})\b", texto)
    if anos:
        ano = anos[0]
        # Verificar que este en un rango razonable (1800-2025)
        if 1800 <= int(ano) <= 2025:
            return ano
    return ""


def extraer_pantallas(texto, texto_autor=None):
    """Extrae numero de pantallas.
    
    Busca en múltiples posiciones porque cuando AUTOR/ES PROYECTO está vacío,
    los datos se desplazan a la izquierda.
    
    Args:
        texto: Texto de la columna de pantallas (posición principal)
        texto_autor: Texto de la columna de autor (posición alternativa)
    
    Returns:
        Número de pantallas (1-50) o cadena vacía
    """
    # Lista de textos a buscar en orden de prioridad
    textos_a_buscar = []
    
    # Prioridad 1: columna de pantallas (posición correcta)
    if texto and texto.strip():
        textos_a_buscar.append(texto.strip())
    
    # Prioridad 2: columna de autor (cuando pantalla está vacío pero autor tiene valor)
    # Esto ocurre cuando AUTOR/ES PROYECTO está vacío y pantallas se desplaza a la izquierda
    if texto_autor and texto_autor.strip():
        # Verificar que el texto del autor parece un número de pantallas (1-2 dígitos)
        # y no es realmente texto de autor (que tendría palabras)
        autor_limpio = texto_autor.strip()
        if re.match(r'^\d{1,2}$', autor_limpio):
            textos_a_buscar.append(autor_limpio)
    
    # Buscar en cada texto, excluyendo años (4 dígitos)
    for texto_buscar in textos_a_buscar:
        # Excluir años (4 dígitos entre 1800-2025)
        # Buscar solo números de 1-2 dígitos que NO estén rodeados por 4 dígitos
        nums = re.findall(r"\b(\d{1,2})\b", texto_buscar)
        for n in nums:
            if 1 <= int(n) <= 50:
                return n
    
    return ""


def restaurar_espacios(texto):
    """Restaura espacios."""
    if not texto:
        return texto
    # Insertar espacio antes de mayuscula que sigue a minuscula
    resultado = re.sub(r"([a-záéíóúñ])([A-ZÁÉÍÓÚÑ])", r"\1 \2", texto)
    # Corregir 'de X' donde X es mayuscula
    resultado = re.sub(r"\bde\s+([A-ZÁÉÍÓÚÑ])", r"de \1", resultado)
    return resultado


def transformar_municipio(municipio):
    """Transforma municipios con formato 'Apellido, El/La/Los/Las' a 'El/La/Los/Las Apellido'.
    
    Ejemplos:
    - 'Coronil, El' -> 'El Coronil'
    - 'Carolina, La' -> 'La Carolina'
    - 'Barrios, Los' -> 'Los Barrios'
    - 'Palmas, Las' -> 'Las Palmas'
    """
    if not municipio:
        return municipio
    
    # Buscar patrones como "Nombre, El", "Nombre, La", etc.
    match = re.match(r'^(.+),\s*(El|La|Los|Las)$', municipio, re.IGNORECASE)
    if match:
        nombre = match.group(1).strip()
        articulo = match.group(2).strip()
        return f"{articulo} {nombre}"
    
    return municipio


def procesar_pagina(pagina, ccaa_inicial="", ayto_inicial="", ultimo_top_pagina_ant=None, ultimo_municipio_ant=None):
    """Procesa una pagina detectando continuaciones por interlineado.
    
    Args:
        pagina: Objeto pagina de pdfplumber
        ccaa_inicial: Comunidad autonoma inicial (para propagar desde pagina anterior)
        ayto_inicial: Municipio inicial (para propagar desde pagina anterior)
        ultimo_top_pagina_ant: Ultimo top de la pagina anterior (para detectar saltos de pagina)
        ultimo_municipio_ant: Ultimo municipio de la pagina anterior (para detectar cambios)
    
    Returns:
        Tupla (registros, ccaa_final, ayto_final, ultimo_top, ultimo_municipio)
    """
    palabras = pagina.extract_words()
    if not palabras:
        return [], ccaa_inicial, ayto_inicial, 0
    
    # Filtrar solo palabras en el area de datos (entre top=50 y top=570)
    # top=50 para incluir cines que comienzan justo después del encabezado
    palabras = [p for p in palabras if 50 < p["top"] < 570]
    
    # Obtener filas con su posicion Y
    filas_con_top = agrupar_palabras(palabras)
    
    registros = []
    ccaa_actual = ccaa_inicial
    ayto_actual = ayto_inicial
    
    # Variables para tracking de continuacion
    ultimo_tipo = None  # 'ccaa', 'ayto', 'dato'
    ultimo_top = ultimo_top_pagina_ant if ultimo_top_pagina_ant else 0
    registro_actual = None
    ultimo_municipio_explícito = ultimo_municipio_ant if ultimo_municipio_ant else ayto_inicial  # Track del último municipio explícito (de fila 'ayto')
    
    for idx, (top, fila_palabras) in enumerate(filas_con_top):
        fila = asignar_columnas(fila_palabras)
        
        # Calcular interlineado (diferencia con fila anterior)
        # Interlineado pequeño (12-35) = continuación de celda
        # Interlineado grande (>35) = nueva fila (nuevo cine)
        
        # Detectar salto de pagina: la posicion Y actual es mucho menor que la anterior
        # (ej: ultimo_top=500, top=100 en la siguiente pagina)
        es_salto_pagina = ultimo_top > 450 and top < 200
        
        interlineado = top - ultimo_top if ultimo_top else 0
        es_nueva_fila = (interlineado > 35) or es_salto_pagina  # Si hay mas de 35 puntos O salto de pagina, es nueva fila
        es_continuacion = (0 < interlineado <= 35) and not es_salto_pagina  # Si hay poco espacio, es continuacion
        
        # NUEVO: Detectar cambio de municipio - si el municipio actual (ayto_actual) es diferente al último explícito,
        # forzar nueva fila (no continuación) para evitar fusión de cines de diferentes municipios
        es_cambio_municipio = False
        if ayto_actual and ultimo_municipio_explícito:
            # Normalizar para comparar
            mun_norm_actual = normalize(ayto_actual)
            mun_norm_ultimo = normalize(ultimo_municipio_explícito)
            if mun_norm_actual != mun_norm_ultimo and mun_norm_actual:
                es_cambio_municipio = True
        
        # Si hay cambio de municipio, forzar nueva fila
        if es_cambio_municipio:
            es_nueva_fila = True
            es_continuacion = False
            registro_actual = None  # Resetear registro actual
        
        # Saltar encabezado y pie
        if es_encabezado(fila) or es_pie(fila):
            ultimo_top = top
            ultimo_tipo = None
            continue
        
        # Determinar tipo de fila
        # Importante: verificar es_dato antes que es_ayto cuando hay contenido en denom o direc
        # porque una palabra como "Roque" podría ser detectada como municipio incorrectamente
        tipo_fila = None
        if es_ccaa(fila, ccaa_actual):
            tipo_fila = 'ccaa'
        elif es_dato(fila):
            # Solo es dato si hay contenido en denom o direc
            tipo_fila = 'dato'
        elif es_ayto(fila, ccaa_actual):
            tipo_fila = 'ayto'
        
        # NUEVO: Si el tipo de fila cambia de 'ayto' a 'dato', forzar nueva fila
        # Esto evita que un cine se fusione con el municipio anterior
        if ultimo_tipo == 'ayto' and tipo_fila == 'dato':
            es_nueva_fila = True
            es_continuacion = False
        
        # Procesar segun el tipo
        if tipo_fila == 'ccaa':
            # Buscar la comunidad en el texto completo
            texto_completo = normalize(" ".join([fila[c].strip() for c in ["ccaa", "ayto", "denom", "direc"]]))
            
            # Buscar comunidades completas primero
            for comunidad in COMUNIDADES:
                if comunidad in texto_completo:
                    ccaa_actual = comunidad
                    break
            else:
                # Buscar comunidades parciales
                ccaa_actual = ""
                for parcial, resultado in COMUNIDADES_PARCIALES:
                    if parcial in texto_completo:
                        if isinstance(resultado, list):
                            for r in resultado:
                                if r in texto_completo:
                                    ccaa_actual = r
                                    break
                        else:
                            ccaa_actual = resultado
                        break
            
            # Normalizar variantes
            if ccaa_actual in VARIANTES:
                ccaa_actual = VARIANTES[ccaa_actual]
            
            ultimo_top = top
            ultimo_tipo = 'ccaa'
            continue
        
        elif tipo_fila == 'ayto':
            # Es continuacion del municipio anterior?
            nuevo_ayto = fila["ayto"].strip()
            if es_continuacion and ultimo_tipo == 'ayto' and nuevo_ayto:
                # Agregar al municipio anterior
                ayto_actual = ayto_actual + " " + nuevo_ayto
            else:
                # Es un nuevo municipio - transformar si tiene formato "Apellido, El"
                ayto_actual = transformar_municipio(nuevo_ayto)
            
            # Actualizar tracking de municipio explícito
            ultimo_municipio_explícito = ayto_actual
            ultimo_top = top
            ultimo_tipo = 'ayto'
            continue
        
        elif tipo_fila == 'dato':
            denom = fila["denom"].strip()
            direc = fila["direc"].strip()
            fecha1 = fila["fecha1"].strip()
            pantallas_col = fila["pantallas"].strip()
            autor_col = fila["autor"].strip()  # Nueva: capturar columna autor para pantallas
            
            # Es continuacion de la fila anterior?
            # Solo se considera continuacion si:
            # 1. Hay poco interlineado (<=35)
            # 2. La fila anterior era un dato
            # 3. La fila actual tiene contenido que parece continuacion:
            #    - Sin nombre pero con direccion (continuacion de direccion)
            #    - Nombre que termina con ) o , (continuacion de nombre)
            
            # Detectar si el nombre parece una continuacion
            # Se considera continuacion solo si:
            # 1. Termina con ) (cierre de paréntesis)
            # 2. O termina con , y no hay dirección (continuación de nombre)
            # 3. O empieza con ( y el registro anterior tenía nombre con Teatro o Cine
            # 4. O el nombre anterior tenía un paréntesis abierto y esta fila tiene contenido relacionado
            # 5. O es una palabra sola que parece continuación de un nombre compuesto
            # 6. O empieza con ( y NO hay dirección (continuación de paréntesis)
            # 7. O el nombre anterior tenía paréntesis abierto y esta fila NO tiene dirección nueva
            nombre_parece_continuacion = False
            if denom:
                # Caso 1: Termina con ) (cierre de paréntesis)
                if denom.endswith(')'):
                    nombre_parece_continuacion = True
                
                # Caso 2: Termina con , y no hay dirección
                elif denom.endswith(',') and not direc:
                    nombre_parece_continuacion = True
                
                # Caso 3: Empieza con ( (paréntesis multi-línea)
                elif denom.startswith('('):
                    if not direc:
                        nombre_parece_continuacion = True
                    elif registro_actual:
                        nombre_previo = registro_actual.get('nombre_cine', '').upper()
                        if 'TEATRO' in nombre_previo or 'CINE' in nombre_previo:
                            nombre_parece_continuacion = True
                
                # Caso 4: El nombre anterior tenía un paréntesis abierto sin cerrar
                if not nombre_parece_continuacion and registro_actual:
                    nombre_previo = registro_actual.get('nombre_cine', '')
                    if nombre_previo and '(' in nombre_previo and ')' not in nombre_previo:
                        if not direc:
                            nombre_parece_continuacion = True
                        elif len(denom.split()) <= 3:
                            nombre_parece_continuacion = True
                
                # NUEVO Caso 5: Nombre anterior termina con preposición ("de", "del", "la")
                # y la línea actual NO tiene dirección completa
                if not nombre_parece_continuacion and registro_actual and not direc:
                    nombre_previo = registro_actual.get('nombre_cine', '').strip()
                    if nombre_previo:
                        ultimas_palabras = nombre_previo.lower().split()[-2:]
                        if any(p in ultimas_palabras for p in ['de', 'del', 'la', 'el', 'los', 'las']):
                            # El nombre anterior parece incompleto
                            nombre_parece_continuacion = True
                
                # NUEVO Caso 6: Nombre anterior termina con conjunción ("y", "e", "o")
                # y la línea actual NO tiene dirección completa
                if not nombre_parece_continuacion and registro_actual and not direc:
                    nombre_previo = registro_actual.get('nombre_cine', '').strip()
                    if nombre_previo:
                        ultima_palabra = nombre_previo.lower().split()[-1]
                        if ultima_palabra in ['y', 'e', 'o', 'ni']:
                            nombre_parece_continuacion = True
                
                # NUEVO Caso 7: La línea actual tiene paréntesis pero NO empieza con él
                # y no tiene dirección = es continuación de nombre
                if not nombre_parece_continuacion and registro_actual and not direc:
                    if '(' in denom and not denom.startswith('('):
                        nombre_parece_continuacion = True
            
            # Continuacion de direccion: 
            # Caso 1: Sin nombre pero con direccion
            # Caso 2: Con direccion Y el registro anterior también tenía dirección (continuación de dirección multilínea)
            # Caso 3: Hay dirección Y el nombre es muy corto (1-2 palabras) Y hay dirección previa
            nombre_corto = denom and len(denom.split()) <= 2
            tiene_continuacion_direccion = (
                (not denom and direc) or  # Sin nombre, con dirección
                (es_continuacion and direc and registro_actual and 
                 registro_actual.get('direccion') and 
                 not denom) or  # Hay dirección previa Y la actual no tiene nombre nuevo
                (es_continuacion and direc and registro_actual and 
                 registro_actual.get('direccion') and nombre_corto)  # Dirección previa + nombre corto
            )
            # Continuacion de nombre: nombre que parece continuacion (aunque tenga direccion)
            tiene_continuacion_nombre = (nombre_parece_continuacion)
            
            # Determinar si es continuación o nuevo registro
            # Solo es continuación si:
            # 1. Hay poco interlineado (<=35)
            # 2. La fila actual tiene contenido ESPECÍFICO de continuación:
            #    - Sin nombre pero CON dirección (continuación de dirección)
            #    - Nombre que TERMINA con ) o , (continuación de nombre)
            #    - Nombre que EMPIEZA con ( (continuación de paréntesis)
            #    - Interlineado MUY pequeño (< 15 puntos) = continuación forzada
            # 3. Hay un registro previo con nombre de cine
            
            # NUEVO: Interlineado muy pequeño (< 15) indica continuación casi segura
            interlineado_muy_pequeno = 0 < interlineado < 15
            
            # NUEVO: Si tiene nombre COMPLETO (no corto) Y dirección nueva, NO es continuación
            # Esto evita fusionar cines diferentes que están juntos
            nombre_completo_con_direccion = (denom and direc and len(denom.split()) >= 2)
            if nombre_completo_con_direccion and registro_actual:
                # Verificar si el nombre parece independiente (no es continuación de paréntesis)
                nombre_previo = registro_actual.get('nombre_cine', '')
                if ')' in nombre_previo or ('(' not in nombre_previo):
                    # El registro anterior está cerrado o no tiene paréntesis
                    # Y el actual tiene nombre+direccion = nuevo cine
                    es_continuacion_direccion = False
                    es_continuacion_nombre = False
                else:
                    # El registro anterior tiene paréntesis abierto, podría ser continuación
                    es_continuacion_direccion = (es_continuacion and 
                                                  tiene_continuacion_direccion and
                                                  registro_actual is not None and 
                                                  bool(registro_actual.get("nombre_cine")))
                    es_continuacion_nombre = ((es_continuacion or interlineado_muy_pequeno) and 
                                               tiene_continuacion_nombre and
                                               registro_actual is not None and 
                                               bool(registro_actual.get("nombre_cine")))
            else:
                es_continuacion_direccion = (es_continuacion and 
                                              tiene_continuacion_direccion and
                                              registro_actual is not None and 
                                              bool(registro_actual.get("nombre_cine")))
                es_continuacion_nombre = ((es_continuacion or interlineado_muy_pequeno) and 
                                           tiene_continuacion_nombre and
                                           registro_actual is not None and 
                                           bool(registro_actual.get("nombre_cine")))
            
            # Si NO es continuación, crear nuevo registro
            if not (es_continuacion_direccion or es_continuacion_nombre):
                registro_actual = None
            
            # NUEVO: Si hay salto de pagina, forzar nuevo registro EXCEPTO si:
            # - El registro anterior tiene paréntesis abierto sin cerrar
            # - El interlineado es muy pequeño (< 15 puntos)
            if es_salto_pagina:
                if registro_actual:
                    nombre_previo = registro_actual.get('nombre_cine', '')
                    # Si hay paréntesis abierto, mantener continuación a través de página
                    if '(' in nombre_previo and ')' not in nombre_previo:
                        pass  # Mantener registro_actual
                    else:
                        registro_actual = None
                else:
                    registro_actual = None
            
            if es_continuacion_direccion or es_continuacion_nombre:
                # Agregar a la columna correspondiente
                if denom:
                    # Continuar denominacion
                    registro_actual["nombre_cine"] = (registro_actual["nombre_cine"] + " " + denom).strip()
                if direc:
                    # Continuar direccion
                    registro_actual["direccion"] = (registro_actual["direccion"] + " " + direc).strip()
                
                # NO actualizar ultimo_municipio_explícito en continuación
                # IMPORTANTE: SI actualizar ultimo_top para calcular correctamente el siguiente interlineado
                ultimo_top = top
                ultimo_tipo = 'dato'
                continue
            
            # Es una nueva fila de datos
            # Extraer ano solo de columnas de fecha (no de texto completo)
            ano = extraer_ano(fecha1)
            
            # Extraer pantallas: primero de columna pantallas, luego de columna autor
            # NO usar texto completo para evitar confundir años con pantallas
            pantallas = extraer_pantallas(pantallas_col, autor_col)
            
            # Restaurar espacios
            denom = restaurar_espacios(denom)
            direc = restaurar_espacios(direc)
            direc = re.sub(r"\s+", " ", direc).strip()
            
            # Transformar municipio (ej: "Coronil, El" -> "El Coronil")
            municipio_transformado = transformar_municipio(ayto_actual)
            
            # Siempre crear/actualizar el registro
            registro_actual = {
                "municipio": municipio_transformado,
                "nombre_cine": denom,
                "numero_pantallas": pantallas,
                "fecha_inaguracion": ano,
                "direccion": direc,
                "comunidad": ccaa_actual
            }
            
            # Solo agregar a la lista si hay nombre de cine o direccion
            if denom or direc:
                registros.append(registro_actual)
            
            # IMPORTANTE: NO resetear ayto_actual - se mantiene para la siguiente página
            # El municipio se propaga hasta que se encuentra uno nuevo explícitamente
            ultimo_top = top
            ultimo_tipo = 'dato'
        
        else:
            ultimo_top = top
            ultimo_tipo = None
    
    # Devolver ultimo_top de esta pagina para detectar saltos de pagina
    ultimo_top_pagina = ultimo_top if filas_con_top else 0
    return registros, ccaa_actual, ayto_actual, ultimo_top_pagina, ultimo_municipio_explícito


def extraer_cines(pdf_path, output_csv):
    """Funcion principal."""
    print("Iniciando extraccion de cines...")
    
    if not Path(pdf_path).exists():
        print(f"PDF no encontrado: {pdf_path}")
        return
    
    todos = []
    ccaa_actual = ""
    ayto_actual = ""
    ultimo_top_pagina = 0
    ultimo_municipio = ""
    
    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
        print(f"El PDF tiene {total} paginas")
        
        for i in range(1, total):
            regs, ccaa_actual, ayto_actual, ultimo_top_pagina, ultimo_municipio = procesar_pagina(
                pdf.pages[i], ccaa_actual, ayto_actual, ultimo_top_pagina, ultimo_municipio
            )
            todos.extend(regs)
            if (i + 1) % 50 == 0:
                print(f"  Procesadas {i + 1}/{total} paginas...")
    
    print(f"Registros extraidos: {len(todos)}")
    
    output_path = Path(output_csv)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow(["municipio", "nombre_cine", "numero_pantallas", "fecha_inaguracion", "direccion", "comunidad"])
        for r in todos:
            w.writerow([r["municipio"], r["nombre_cine"], r["numero_pantallas"], r["fecha_inaguracion"], r["direccion"], r["comunidad"]])
    
    print(f"CSV guardado: {output_path}")
    return todos


def extraer_cines_csv(pdf_path, output_csv):
    """Funcion principal con delimitador punto y coma."""
    print("Iniciando extraccion de cines...")
    
    if not Path(pdf_path).exists():
        print(f"PDF no encontrado: {pdf_path}")
        return
    
    todos = []
    ccaa_actual = ""
    ayto_actual = ""
    ultimo_top_pagina = 0
    ultimo_municipio = ""
    
    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
        print(f"El PDF tiene {total} paginas")
        
        for i in range(1, total):
            regs, ccaa_actual, ayto_actual, ultimo_top_pagina, ultimo_municipio = procesar_pagina(
                pdf.pages[i], ccaa_actual, ayto_actual, ultimo_top_pagina, ultimo_municipio
            )
            todos.extend(regs)
            if (i + 1) % 50 == 0:
                print(f"  Procesadas {i + 1}/{total} paginas...")
    
    print(f"Registros extraidos: {len(todos)}")
    
    output_path = Path(output_csv)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Usar punto y coma como delimitador para evitar problemas con comas
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=';', quoting=csv.QUOTE_ALL)
        w.writerow(["municipio", "nombre_cine", "numero_pantallas", "fecha_inaguracion", "direccion", "comunidad"])
        for r in todos:
            w.writerow([r["municipio"], r["nombre_cine"], r["numero_pantallas"], r["fecha_inaguracion"], r["direccion"], r["comunidad"]])
    
    print(f"CSV guardado: {output_path}")
    return todos


if __name__ == "__main__":
    extraer_cines_csv(PDF_PATH, OUTPUT_PATH)