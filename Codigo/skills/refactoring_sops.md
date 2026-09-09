# Skill: Auditor de Sesgos y Calidad Documental (Refactoring de SOPs)

## Cuándo activar
Cuando el usuario suba o pegue un borrador de procedimiento, SOP, instructivo o formato para revisión, o pida auditar la calidad documental de un documento.

## Instrucciones

Analiza el documento y evalúa los siguientes criterios:

### 1. Detección de Términos Ambiguos
Identifica y marca expresiones subjetivas que no son verificables:

| Término Ambiguo | Sugerencia de Corrección |
|----------------|------------------------|
| "verificar adecuadamente" | "verificar que la temperatura esté entre 2-8°C" |
| "cuando sea necesario" | "al inicio de cada turno (07:00, 15:00, 23:00)" |
| "en un tiempo prudencial" | "dentro de los 30 minutos posteriores a la recepción" |
| "responsable designado" | "Supervisor de Calidad del turno" |
| "condiciones óptimas" | "temperatura 2-8°C, humedad < 65%" |
| "regularmente" | "con frecuencia diaria/semanal" |
| "asegurar que" | "verificar mediante [registro] que" |

### 2. Validación RACI
Verifica que cada actividad tenga responsable claro:

| Problema RACI | Detección | Corrección |
|--------------|-----------|------------|
| Sin responsable | Actividad sin nombre/cargo | Asignar cargo específico |
| Responsable múltiple | "Operario y supervisor" | Definir R (ejecuta) vs A (aprueba) |
| Responsable genérico | "Personal del área" | Especificar cargo y turno |
| Sin aprobador | Sin firma de revisión | Agregar responsable de aprobación |

### 3. Criterios de Aceptación Cuantitativos
Verifica que cada control tenga:
- **Valor medible:** temperatura, tiempo, cantidad, porcentaje
- **Rango específico:** min-max (ej: 2-8°C, no "frío")
- **Frecuencia definida:** cada cuánto se mide
- **Registro obligatorio:** dónde se documenta

### 4. Evidencias Archivables
Verifica que cada actividad genere:
- **Registro:** formato, checklist, log del WMS
- **Responsable del registro:** quién lo llena
- **Tiempo de retención:** cuánto se guarda
- **Ubicación:** dónde se almacena (físico/digital)

### 5. Estructura Documental
Verifica que el documento tenga:
- [ ] Objetivo claro
- [ ] Alcance definido (qué procesos/áreas incluye)
- [ ] Definiciones de términos técnicos
- [ ] Documentos de referencia (códigos Integr@)
- [ ] Procedimiento paso a paso
- [ ] Registros asociados
- [ ] Control de cambios (versiones)
- [ ] Aprobaciones (elaboró, revisó, aprobó)

### Formato de salida
```
AUDITORÍA DOCUMENTAL: [Nombre del documento]

🔴 PROBLEMAS CRÍTICOS (deben corregirse antes de publicar):
  1. [Problema] → [Corrección sugerida]
  2. ...

🟡 MEJORAS RECOMENDADAS:
  1. [Mejora] → [Sugerencia]
  2. ...

🟢 FORTALEZAS (lo que está bien hecho):
  1. [Aspecto positivo]

VERSIÓN SUGERIDA: [Borrador corregido con los cambios aplicados]
```
