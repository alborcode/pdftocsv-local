# Memory - pdftocsv-local

## Estado Actual
- Última sesión: 2026-04-19
- Tareas completadas:
  - Modificar cines.py para generar CSV desde PDF - **Agente:** opencode - **Modelo:** mimo-v2-omni
  - Modificar teatros_impreso.py para generar CSV desde PDF - **Agente:** opencode - **Modelo:** mimo-v2-omni
  - Verificar funcionamiento de scripts y CSVs generados - **Agente:** opencode - **Modelo:** mimo-v2-omni
  - Corregir caracteres especiales en CSVs - **Agente:** opencode - **Modelo:** mimo-v2-omni
  - Transformar nombres de municipios/localidades (formato "NOMBRE, ARTÍCULO" a "ARTÍCULO NOMBRE") - **Agente:** opencode - **Modelo:** mimo-v2-omni
  - Corregir "MAD RID" a "MADRID" en ambos scripts - **Agente:** opencode - **Modelo:** mimo-v2-omni
  - Corregir extracción de datos en cines.py - **Agente:** opencode - **Modelo:** mimo-v2-omni
  - Crear script limpio de extracción posicional para cines - **Agente:** OpenAgent - **Modelo:** deepseek-reasoner
  - Corregir problemas de extracción (número de pantallas, fusión de cines) - **Agente:** OpenAgent - **Modelo:** minimax-m2.5
  - Corregir detección de El Coronil (cines.py) - **Agente:** OpenAgent - **Modelo:** minimax-m2.5
- Tarea en progreso: Ninguna (completada)
- Bloqueos: Ninguno

## Resultados de la Extracción (actualizados)
- Registros extraidos: 2685 (óptimo - se fusionaron continuaciones correctamente)
- Comunidad: ~95% llena
- Municipio: ~98% lleno
- Nombre cine: ~99% lleno (mejora significativa en nombres multi-línea)
- Dirección: ~96% llena
- Número pantallas: ~93% lleno
- Fecha inauguración: ~93% llena

## Casos corregidos (sesión actual)
- Jaén - Teatro Municipal Darymelia: ✅ 1 registro (nombre multi-línea con paréntesis fusionado)
- Leganés/Madrid: ✅ Municipios separados correctamente (Madrid detectado como municipio cuando CCAA=MADRID)
- Aluche Minicines + Artistic Metropol: ✅ Separados (nombre+dirección = nuevo cine)
- Vimbodí - Cinema Fomet Municipal de Cultura: ✅ Fusionado (preposición "de" indica continuación)
- Vilallonga del Camp - Cinema de la Societat Centre Recreatiu: ✅ Fusionado (paréntesis en continuación)
- Pedreguer - Espacio Cultural Cine/Espai Cultural: ✅ Fusionado
- Vilanova - Cine Centro Cultural y Recreativo: ✅ Fusionado (conjunción "y" indica continuación)
- El Coronil - Cine Avenida: ✅ Aparece correctamente
- Algeciras - Teatro Municipal Florida: ✅ Aparece después de salto de página

## Decisiones Tomadas
- Eliminar dependencias de módulos `app.*` que no existen en el proyecto actual
- Simplificar lógica de extracción manteniendo solo la extracción de datos crudos
- Generar CSVs con delimitador punto y coma para manejar comas en campos
- Usar extracción posicional con pdfplumber.extract_words() para mayor precisión
- Normalizar texto (quitar tildes, guiones) para detección de comunidades
- Propagar CCAA y AYUNTAMIENTO entre páginas con forward-fill
- Usar tolerancia de 3 puntos al agrupar palabras en filas
- Buscar número de pantallas en múltiples posiciones (columna pantallas y columna autor)
- No usar texto completo para extraer pantallas (evita confundir años con pantallas)
- Actualizar `ultimo_top` en continuaciones para calcular correctamente siguiente interlineado
- Buscar comunidades solo en columnas CCAA/AYTO (no en denom/direc) para evitar falsos positivos
- NO resetear ayto_actual después de procesar datos - se propaga hasta nuevo municipio explícito
- Usar ultimo_municipio_explícito (solo de filas 'ayto') para detectar cambio de municipio
- Ampliar rango de extracción a top=50 (antes top=100) para incluir cines después de encabezado
- Detectar continuación de nombres multi-línea con paréntesis
- Detectar municipio cuando texto es igual a CCAA actual (ej: Madrid municipio)
- Separar cines cuando hay nombre COMPLETO + dirección nueva (no continuación)
- Detectar continuación por preposiciones finales ("de", "del", "la")
- Detectar continuación por conjunciones finales ("y", "e", "o")
- Detectar continuación por paréntesis en línea (no al inicio)

## Siguiente Paso
- Ninguno - tarea completada

## Archivos Clave
- `cines.py`: Script para extraer datos de cines desde PDF y generar CSV
- `teatros_impreso.py`: Script para extraer datos de teatros desde PDF y generar CSV
- `data/data_pdf/cines-listado-julio-2021.pdf`: PDF con datos de cines
- `data/data_pdf/Redescena-Impreso.pdf`: PDF con datos de teatros
- `data/data_csv/cines.csv`: CSV generado con datos de cines
- `data/data_csv/teatros.csv`: CSV generado con datos de teatros
- `PLAN.md`: Plan de trabajo para la tarea

## Contexto Importante
- Los scripts originalmente dependían de módulos `app.database`, `app.models`, etc. que no existen en el proyecto actual
- Se han modificado los scripts para funcionar de forma independiente
- Los PDFs están en `data/data_pdf/` y los CSVs se generan en `data/data_csv/`
- El script de cines actual (`cines.py`) usa extracción posicional con pdfplumber.extract_words()
- Los CSVs generados usan codificación UTF-8 con BOM (utf-8-sig) para compatibilidad con Excel

## Tracking de Uso
- Total tareas completadas: 11
- Agentes utilizados: opencode, OpenAgent
- Modelos utilizados: mimo-v2-omni, deepseek-reasoner, minimax-m2.5