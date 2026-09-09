# Skills del Agente de Calidad

Los skills se cargan dinámicamente cuando la pregunta del usuario coincide con el patrón de activación.

| Skill | Archivo | Se activa cuando el usuario pide... |
|-------|---------|-------------------------------------|
| Mermaid | `mermaid.md` | Flujos, diagramas, flujogramas, Ishikawa, árboles de decisión |
| CAPA | `capa.md` | Causa raíz, 5 porqués, FMEA, AMEF, 6M, NPR |
| No Conformidad | `no_conformidad.md` | No conformidades, hallazgos, desviaciones, planes de acción |
| Auditoría | `auditoria.md` | Simular auditoría, roleplay, preparación Invima/ISO |
| Checklists | `checklists.md` | Formatos, checklists, matrices de captura, WMS, Power Apps |
| Refactoring SOPs | `refactoring_sops.md` | Revisar borradores, auditar calidad documental, mejorar SOPs |
| Búsqueda por filtros | `busqueda_filtros.md` | Combinar filtros (proceso, estado, fecha) + búsqueda semántica |
| Comparador versiones | `comparador_versiones.md` | Comparar versiones de un documento, ver qué cambió |
| Detector duplicados | `detector_duplicados.md` | Detectar documentos duplicados o similares con FAISS |
| Exportar | `exportar.md` | Exportar respuestas a PDF, Word o Excel |

## Reglas de activación
- Solo se carga el skill relevante a la pregunta (ahorra tokens)
- Se puede activar más de un skill si la pregunta lo requiere
- Si ningún skill aplica, el agente responde con el system prompt base
