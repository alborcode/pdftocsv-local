# REGLAS OBLIGATORIAS

## 🚨 ANTES DE NADA

```
1. ¿Existe MEMORY.md?
   → NO: CREARLO ahora mismo
   → SI: LEERLO completo
2. ¿Hay tareas con 2+ pasos? → Crear PLAN.md
3. Solo después → trabajar
```

## REGLAS

| Regla | Qué hacer |
|-------|-----------|
| **1. MEMORY.md** | Crear al inicio, actualizar después de cada tarea, leer al inicio de cada sesión |
| **2. PLAN.md** | Solo si la tarea tiene 2+ pasos. Si hay flujo SDD, usar SDD tasks.md (contiene la misma información que PLAN.md). Consultar thoth-mem para contexto adicional si es necesario |
| **3. "Done" =** | Verificar código + ejecutar tests + actualizar MEMORY.md |
| **4. Tracking** | Registrar agente y modelo en MEMORY.md |

## ESTRUCTURA 
```
nombre_proyecto/
├── RULES.md
├── AGENTS.md
├── MEMORY.md
├── app/                        ← Paquete Python (corto, NO nombre completo)
│   ├── __init__.py
│   ├── main.py                 ← Entry point
│   ├── config.py, database.py, constants.py, ...
│   ├── views/                  ← Vistas UI
│   ├── utils/                  ← Funciones auxiliares
│   ├── scripts/                ← Scripts ejecutables
│   └── static/                 ← Archivos estáticos
├── tests/                      ← Fuera del paquete
└── data/                       ← Fuera del paquete (Bases de datos y otras fuentes)
```

**Regla:** El paquete siempre se llamará (`app`).

## IDIOMA

- Comentarios/docs: **español**
- Variables: español o inglés (ser consistente)

---

MEMORY.md + thoth-mem son la fuente de verdad del estado del proyecto. MEMORY.md es visible y editable por ti; thoth-mem persiste automáticamente decisiones, bugs y patrones. Para contexto adicional, usar `mem_search` o `mem_context`.