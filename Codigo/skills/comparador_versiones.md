# Skill: Comparador de Versiones de Documentos

## Cuándo activar
Cuando el usuario pida comparar dos versiones de un procedimiento, ver diferencias entre versiones, o entender qué cambió de una versión a otra.

## Instrucciones

### Fuente de datos
Las versiones se identifican mediante:
- `PROCEDIMIENTOS_COD`: incluye la versión (ej: `PGC-16-15_V_01` vs `PGC-16-15_V_02`)
- `PROCEDIMIENTOS_ANTE`: código del documento anterior en la cadena de versiones
- `PROCEDIMIENTOSCAMBIO`: tabla con descripción de cambios realizados

### Flujo de comparación

**1. Identificar versiones a comparar:**
- Si el usuario da un código: buscar versión actual y anterior usando `PROCEDIMIENTOS_ANTE`
- Si el usuario da dos códigos: comparar directamente
- Si el usuario pide "qué cambió en PGC-16-15": buscar todas las versiones

**2. Extraer contenido de cada versión:**
- Texto extraído de `PROCEDIMIENTOS_WORD` (en SQLite: `contenido_texto`)
- Metadatos: estado, fechas, elaborador, revisor

**3. Comparar secciones:**
- Objetivo
- Alcance
- Responsables
- Definiciones
- Procedimiento (paso a paso)
- Registros
- Anexos

**4. Identificar cambios:**
- Secciones añadidas
- Secciones eliminadas
- Secciones modificadas
- Cambios de responsables
- Cambios en criterios de aceptación
- Cambios en frecuencias o plazos

**5. Consultar PROCEDIMIENTOSCAMBIO:**
- Descripción oficial del cambio registrada en Integr@
- Fecha del cambio
- Usuario que lo realizó

### Formato de salida
```
COMPARACIÓN DE VERSIONES

Documento: [Nombre del procedimiento]
Versión anterior: [Código_V_01] (estado: O, fecha publicación: YYYY-MM-DD)
Versión actual:   [Código_V_02] (estado: P, fecha publicación: YYYY-MM-DD)

CAMBIOS DETECTADOS:

1. SECCIONES AÑADIDAS:
   - [Sección nueva]: [Resumen]

2. SECCIONES ELIMINADAS:
   - [Sección eliminada]: [Resumen]

3. SECCIONES MODIFICADAS:
   - [Sección]: [Qué cambió]
     Antes: [Texto anterior]
     Ahora: [Texto nuevo]

4. CAMBIOS DE METADATOS:
   - Responsable: [Antes] → [Ahora]
   - Frecuencia: [Antes] → [Ahora]
   - Criterio: [Antes] → [Ahora]

5. DESCRIPCIÓN OFICIAL DEL CAMBIO (Integr@):
   [Texto de PROCEDIMIENTOSCAMBIO]
   Fecha: [Fecha]
   Usuario: [Usuario]
```

### Reglas
- Priorizar la versión vigente (estado P) sobre la obsoleta (estado O).
- Si solo existe una versión, informar que no hay versiones anteriores para comparar.
- Si hay más de 2 versiones, mostrar el historial completo de cambios.
- Los cambios críticos (criterios de aceptación, responsables, frecuencias) deben destacarse.
