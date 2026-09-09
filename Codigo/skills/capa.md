# Skill: Motor de Análisis de Causa Raíz (CAPA) y Métodos Avanzados

## Cuándo activar
Cuando el usuario pida analizar una no conformidad, investigar causa raíz, crear un plan CAPA, o usar FMEA/AMEF, Ishikawa, 5 Porqués o análisis 6M.

## Instrucciones

### Los 5 Porqués Integrados
Profundiza en la falla preguntando "¿Por qué?" 5 veces consecutivas, conectando calidad y SST:

1. **¿Por qué ocurrió la falla?** → Causa inmediata
2. **¿Por qué existía esa condición?** → Causa subyacente
3. **¿Por qué no se detectó?** → Falla en control
4. **¿Por qué el control falló?** → Causa del sistema
5. **¿Por qué el sistema permitió eso?** → Causa raíz

Ejemplo de integración SST: Si la falla fue "operario omitió paso del SOP", evalúa si la causa raíz incluye fatiga, falta de EPP adecuado, o condición ergonómica deficiente.

### Análisis 6M (Ishikawa)
Estructura las causas en 6 categorías:
- **Mano de Obra:** capacitación, experiencia, fatiga, supervisión
- **Método:** SOP, procedimiento, instrucciones, frecuencia de control
- **Máquina:** equipo, calibración, mantenimiento, software WMS
- **Material:** materia prima, empaque, temperatura, estabilidad
- **Medio Ambiente:** temperatura ambiente, humedad, layout, iluminación
- **Medición:** instrumentos, criterios de aceptación, registros

### Matriz FMEA / AMEF
Calcula el NPR (Número de Prioridad de Riesgo):

| Campo | Escala | Valores |
|-------|--------|---------|
| Severidad (S) | Impacto del fallo | 1 (sin efecto) - 10 (seguridad/legal) |
| Ocurrencia (O) | Probabilidad de fallo | 1 (remoto) - 10 (muy alto) |
| Detección (D) | Probabilidad de no detectar | 1 (siempre detecta) - 10 (no detecta) |
| **NPR** | S × O × D | 1 - 1000 |

**Priorización:**
- NPR ≥ 100: Acción correctiva inmediata
- NPR 50-99: Plan de acción con plazo definido
- NPR < 50: Monitoreo y control

### Formato de salida CAPA
```
NO CONFORMIDAD: [Descripción]
CLASIFICACIÓN: [Crítica/Mayor/Menor] (según matriz HSEQ)
ANÁLISIS DE CAUSA RAÍZ:
  Método: [5 Porqués / Ishikawa / 6M]
  Causa raíz identificada: [Descripción]

ACCIÓN CORRECTIVA (eliminar causa):
  - Acción: [Qué se va a hacer]
  - Responsable: [Quién]
  - Plazo: [Cuándo]
  - Evidencia de cierre: [Qué registro]

ACCIÓN PREVENTIVA (prevenir recurrencia):
  - Acción: [Qué se va a hacer]
  - Responsable: [Quién]
  - Plazo: [Cuándo]
  - Verificación de efectividad: [Cómo se valida]

DOCUMENTOS INTEGR@ RELACIONADOS: [Códigos de procedimientos vigentes]
```
