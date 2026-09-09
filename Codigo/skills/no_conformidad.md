# Skill: Gestión de No Conformidades de Integr@

## Cuándo activar
Cuando el usuario pida consultar, registrar, analizar o gestionar no conformidades, hallazgos, desviaciones, correcciones o planes de acción.

## Instrucciones

### Fuente de datos
Las no conformidades en Integr@ se almacenan en:
- **`NoConformidad`**: registro principal de NC (descripción, fecha, proceso, severidad, estado)
- **`CorreccionNC`**: correcciones inmediatas asociadas a cada NC
- **`PlanesAccionNC`**: planes de acción correctivos y preventivos

### Flujo de gestión de NC

**1. Identificación:**
- Descripción de la desviación
- Proceso donde se detectó (de Integr@: GC, WH, MQ, SR, ST, etc.)
- Documento/procedimiento relacionado (código Integr@)
- Fecha de detección
- Quien detecta

**2. Clasificación (según matriz HSEQ del system_prompt):**
| Severidad | Criterio Calidad | Criterio SST | Acción |
|-----------|-----------------|--------------|--------|
| Crítica | Ruptura cadena frío, pérdida trazabilidad | Accidente grave/mortal | CAPA < 24h |
| Mayor | Incumplimiento SOP sistemático | Incidente con lesión potencial | Plan < 5 días |
| Menor | Error puntual en registro | Desorden 5S | Corrección in situ |

**3. Análisis de causa raíz:**
- Activar skill `capa.md` automáticamente
- Aplicar 5 Porqués, Ishikawa 6M o FMEA según complejidad
- Conectar con el procedimiento vigente de Integr@ que se incumplió

**4. Acción correctiva (eliminar causa):**
- Qué se va a hacer
- Responsable
- Plazo (según severidad: crítica 24h, mayor 5 días, menor 15 días)
- Evidencia de cierre

**5. Acción preventiva (prevenir recurrencia):**
- Actualización de SOP en Integr@
- Re-capacitación
- Modificación de checklist
- Verificación de efectividad

**6. Cierre:**
- Verificar que la acción fue efectiva
- Documentar evidencia
- Cerrar NC en Integr@

### Formato de salida para consulta de NC
```
NO CONFORMIDAD #[ID]
Proceso: [Proceso de Integr@]
Descripción: [Descripción de la desviación]
Severidad: [Crítica/Mayor/Menor]
Fecha detección: [Fecha]
Estado: [Abierta/En análisis/En acción/Cerrada]
Procedimiento relacionado: [Código Integr@ del SOP incumplido]
Corrección inmediata: [Acción tomada]
Plan de acción: [CAPA en curso]
Días transcurridos: [Días desde detección]
```

### Formato de salida para nueva NC
```
REGISTRO DE NO CONFORMIDAD

1. DESCRIPCIÓN:
   [Qué ocurrió, dónde, cuándo]

2. CLASIFICACIÓN:
   Tipo: [Documental/Operativa/Regulatoria]
   Severidad: [Crítica/Mayor/Menor]
   Recurrencia: [Sí/No - NC anterior relacionada: #ID]

3. PROCEDIMIENTO INCUMPLIDO:
   Código Integr@: [PGC-XX-NN]
   Requisito específico: [Paso/cláusula del SOP]

4. ANÁLISIS DE CAUSA RAÍZ:
   [Activar skill capa.md - 5 Porqués / Ishikawa / FMEA]
   Causa raíz: [Descripción]

5. ACCIÓN CORRECTIVA:
   Acción: [Qué]
   Responsable: [Quién]
   Plazo: [Fecha según severidad]
   Evidencia: [Registro/formato]

6. ACCIÓN PREVENTIVA:
   Acción: [Qué]
   Responsable: [Quién]
   Plazo: [Fecha]
   Verificación: [Cómo se valida la efectividad]

7. DOCUMENTOS INTEGR@ RELACIONADOS:
   - [Código del procedimiento a actualizar]
   - [Código del formato asociado]
   - [Código del proceso relacionado]
```

### Reglas
- Toda NC debe vincularse a un procedimiento vigente de Integr@ (estado P).
- Si el procedimiento está obsoleto, señalarlo como hallazgo adicional.
- Si la NC es crítica, recomendar bloqueo inmediato y notificación ejecutiva.
- Conectar automáticamente con el skill `capa.md` para el análisis de causa raíz.
- Conectar automáticamente con el skill `mermaid.md` si el usuario pide visualizar el flujo de la NC.
