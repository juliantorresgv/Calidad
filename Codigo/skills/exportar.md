# Skill: Exportar Respuestas a PDF/Word

## Cuándo activar
Cuando el usuario pida exportar, descargar, guardar o generar un documento con la respuesta del agente (PDF, Word, Excel).

## Instrucciones

### Formatos de exportación

**1. PDF profesional:**
Estructura del documento exportado:
```
[Logo/Sistema] AGENTE DE CALIDAD - INTEGR@
Fecha: [YYYY-MM-DD HH:MM]
Consulta: [Pregunta del usuario]

═══════════════════════════════════════════

[Respuesta del agente con formato]

═══════════════════════════════════════════

DOCUMENTOS DE REFERENCIA:
1. [Código] - [Nombre] (estado: P, proceso: WH)
2. [Código] - [Nombre] (estado: P, proceso: GC)

GLOSARIO CONSULTADO:
- [Término]: [Definición]

Generado por: Agente de Calidad Integr@ + Mistral
```

**2. Word (.docx):**
- Mismo contenido que PDF pero editable
- Usa `python-docx` para generar
- Incluye tabla de documentos de referencia
- Incluye sección de glosario si fue consultado

**3. Excel (.xlsx):**
- Para respuestas tabulares (inventarios, listados, comparaciones)
- Usa `openpyxl` para generar
- Hoja 1: Respuesta
- Hoja 2: Documentos de referencia
- Hoja 3: Glosario (si aplica)

### Tipos de exportación

| Tipo de respuesta | Formato recomendado | Motivo |
|------------------|-------------------|--------|
| Respuesta narrativa | PDF | Documento formal para compartir |
| Borrador de SOP | Word | Editable para revisión |
| Inventario/listado | Excel | Datos tabulares |
| Comparación de versiones | Word | Documento de análisis |
| Reporte de auditoría | PDF | Documento formal |
| Matriz CAPA | Excel | Seguimiento de acciones |
| Checklist | Excel | Formato utilizable |

### Reglas
- Siempre incluir la fecha de generación.
- Siempre citar los documentos de Integr@ consultados.
- Si se usó glosario, incluir los términos consultados.
- Marcar el documento como "Generado por IA - validar antes de uso oficial".
- Para SOPs borradores, incluir marca de agua "BORRADOR - NO PUBLICADO".
- Los PDFs se guardan en `Exports/` dentro del proyecto.
- Los nombres de archivo incluyen fecha: `respuesta_YYYYMMDD_HHMM.pdf`.
