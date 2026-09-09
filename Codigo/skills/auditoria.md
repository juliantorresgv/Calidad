# Skill: Simulador de Auditorías Internas y Entrevistas (Roleplay)

## Cuándo activar
Cuando el usuario pida simular una auditoría, prepararse para auditoría Invima/ISO/cliente, o hacer roleplay de auditor/auditado.

## Instrucciones

### Modo Auditor / Auditado
El agente puede actuar en dos roles:

**Como Auditor:**
1. Genera una lista de verificación basada en procesos vigentes de Integr@.
2. Hace preguntas de muestreo aleatorio al usuario (auditado).
3. Evalúa las respuestas y evidencias presentadas.
4. Redacta hallazgos al finalizar.

**Como Auditado (entrenamiento):**
1. El usuario hace preguntas de preparación.
2. El agente responde como lo haría un responsable de proceso.
3. Sugiere evidencias a tener listas.

### Estructura de Auditoría

**Fase 1: Preparación**
- Selecciona el proceso a auditar (de Integr@: GC, WH, MQ, SR, ST, RH, etc.)
- Genera checklist con criterios basados en procedimientos vigentes
- Define muestreo documental (cuántos registros revisar)

**Fase 2: Ejecución**
- Pregunta una a una, esperando respuesta del usuario
- Tipos de pregunta:
  - Documental: "Muéstrame el procedimiento PGC-XX vigente"
  - Operativa: "¿Cómo se realiza el control de temperatura en cuarto frío?"
  - Trazabilidad: "¿Qué registros evidencian la liberación del lote X?"
  - SST: "¿Qué EPP es obligatorio en esta operación?"

**Fase 3: Reporte de Hallazgos**
Formato de cada hallazgo:
```
HALLAZGO #[N]
Proceso: [Proceso auditado]
Requisito: [Norma/SOP/Invima referenciado]
Evidencia revisada: [Documento Integr@ o respuesta del auditado]
Desviación: [Lo que no cumple]
Clasificación: [Crítica/Mayor/Menor]
Riesgo: [Impacto en calidad/SST/operación]
Recomendación: [Acción sugerida]
```

**Fase 4: Plan de Acción**
- Consolidar hallazgos por severidad
- Asignar responsables y plazos
- Definir verificación de cierre

### Criterios de Evaluación
- **Conforme:** Respuesta respaldada por documento vigente de Integr@
- **No conforme:** Respuesta sin evidencia o contradictoria con SOP
- **Observación:** Mejora sugerida sin incumplimiento
- **No aplica:** Pregunta no relevante para el proceso auditado
