# Skill: Analista y Diseñador de Formatos / Checklists Digitales

## Cuándo activar
Cuando el usuario pida diseñar un formato, checklist, matriz de captura, o instrumento para WMS/Power Apps.

## Instrucciones

### Diseño de instrumentos de captura

Genera matrices de datos con tipos de campo específicos:

| Tipo de Campo | Uso | Validación |
|--------------|-----|------------|
| Texto | Descripciones, observaciones | Longitud mínima/máxima |
| Fecha | Fecha de control, vencimiento | No puede ser futura/pasada según regla |
| Selección Única | Cumple/No cumple/No aplica | Obligatoria |
| Selección Múltiple | Tipos de hallazgo, EPP usado | Mínimo 1 |
| Numérico | Temperatura, humedad, conteo | Rango válido (ej: -25 a +8°C) |
| Foto Obligatoria | Evidencia visual | No se puede guardar sin foto |
| Firma Digital | Responsable, aprobador | Obligatoria para cierre |
| Calculado | NPR, % cumplimiento | Fórmula automática |

### Alertas condicionales

Define reglas que disparan acciones automáticas:

```
SI Temperatura > 8°C → Disparar bloqueo de lote + Notificar Jefe de Calidad
SI Humedad > 65% → Alerta amarilla + Registrar desviación
SI EPP incompleto → Bloquear inicio de actividad
SI Merma > tolerancia → Notificar gerencia + Iniciar CAPA
SI Documento obsoleto → Excluir de resultados + Alertar vigencia
```

### Estructura de checklist estándar

```
FORMATO: [Nombre del formato]
CÓDIGO: [F-XX-NN] (si existe en Integr@)
PROCESO: [Proceso al que aplica]
VERSIÓN: [Versión]

CAMPOS DE CABECERA:
- Fecha: [Fecha] (obligatorio)
- Responsable: [Texto] (obligatorio)
- Turno: [Selección: Mañana/Tarde/Noche]
- Área/Ubicación: [Texto] (obligatorio)

PUNTOS DE CONTROL:
| # | Punto de Control | Criterio | Tipo | Resultado | Evidencia | Observación |
|---|-----------------|----------|------|-----------|-----------|-------------|
| 1 | Temperatura cuarto frío | 2-8°C | Numérico | ___°C | [Foto] | _______ |
| 2 | Limpieza de estibas | Sin residuos | Selección | C/NC/NA | [Foto] | _______ |
| 3 | EPP del operario | Completo | Selección | C/NC/NA | [Foto] | _______ |

CAMPOS DE CIERRE:
- Resultado general: [Conforme/No conforme]
- Acción inmediata (si NC): [Texto]
- Responsable de cierre: [Firma digital]
- Fecha de cierre: [Fecha]
```

### Reglas
- Cada campo debe tener propósito, responsable y evidencia verificable.
- Incluye opciones: Cumple, No cumple, No aplica, Requiere validación.
- Recomienda controles para evitar registros incompletos o duplicados.
- Si existe un formato similar en Integr@ (código F-XX), úsalo como base y mejora.
