# Skill: Detector de Documentos Duplicados/Similares

## Cuándo activar
Cuando el usuario pida detectar documentos duplicados, similares, redundantes, o posibles duplicados en la base documental de Integr@.

## Instrucciones

### Método de detección

Usar FAISS (índice vectorial) para encontrar documentos con alta similitud semántica:

**1. Umbral de similitud:**
- Similitud coseno > 0.95: muy probable duplicado
- Similitud coseno 0.85-0.95: documento similar/muy relacionado
- Similitud coseno 0.75-0.85: tema relacionado
- Similitud coseno < 0.75: no relacionado

**2. Criterios de clasificación:**

| Clasificación | Criterio | Acción sugerida |
|--------------|----------|-----------------|
| Duplicado exacto | Mismo código o nombre idéntico + similitud > 0.95 | Consolidar en uno solo |
| Duplicado de versión | Código similar (ej: V_01 vs V_02) + similitud > 0.90 | Mantener solo la vigente |
| Documento similar | Mismo proceso + similitud > 0.85 | Evaluar fusión o referencia |
| Documento relacionado | Mismo tema + similitud > 0.75 | Cruzar como relacionados en el grafo |

**3. Verificación adicional:**
- Comparar códigos: ¿empiezan igual? (ej: PGC-16-15_V_01 vs PGC-16-15_V_02)
- Comparar nombres: ¿son casi idénticos?
- Comparar procesos: ¿pertenecen al mismo proceso?
- Comparar estados: ¿uno está obsoleto y otro publicado?
- Comparar fechas: ¿uno es posterior al otro?

### Formato de salida
```
DETECCIÓN DE DOCUMENTOS DUPLICADOS/SIMILARES

Resumen:
  - Duplicados exactos: [N]
  - Duplicados de versión: [N]
  - Documentos similares: [N]
  - Documentos relacionados: [N]

DUPLICADOS EXACTOS:
  Par 1:
    Documento A: [Código] - [Nombre] (estado: P, fecha: YYYY-MM-DD)
    Documento B: [Código] - [Nombre] (estado: P, fecha: YYYY-MM-DD)
    Similitud: [X.XX]
    Recomendación: [Consolidar / Mantener uno]

DUPLICADOS DE VERSIÓN:
  Par 1:
    Versión vigente: [Código_V_02] (estado: P)
    Versión anterior: [Código_V_01] (estado: O)
    Similitud: [X.XX]
    Recomendación: Mantener vigente, archivar obsoleta

DOCUMENTOS SIMILARES:
  Par 1:
    Documento A: [Código] - [Nombre] (proceso: WH)
    Documento B: [Código] - [Nombre] (proceso: WH)
    Similitud: [X.XX]
    Recomendación: [Evaluar fusión / Cruzar como relacionados]
```

### Reglas
- No marcar como duplicados documentos del mismo proceso que tratan temas diferentes.
- Las versiones del mismo documento (V_01, V_02) son esperadas, no errores.
- Priorizar la detección de duplicados entre documentos publicados (estado P).
- Si se detectan duplicados entre procesos diferentes, señalarlo como hallazgo de auditoría.
