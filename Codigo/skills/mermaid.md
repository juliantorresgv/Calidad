# Skill: Generador de Diagramas Mermaid

## Cuándo activar
Cuando el usuario pida un flujo, procedimiento, mapa de decisiones, flujograma, diagrama de causa-efecto o árbol de decisión.

## Instrucciones

Genera automáticamente código en sintaxis Mermaid.js para renderizar el diagrama solicitado.

### Tipos de diagramas

**Flujogramas BPMN** (procesos operativos):
```mermaid
flowchart TD
    A[Recepción de Mercancía] --> B{Inspección Visual}
    B -->|Conforme| C[Registro en WMS]
    B -->|No conforme| D[Bloqueo de Calidad]
    C --> E[Almacenamiento]
    D --> F[Análisis de NC]
    F --> G{CAPA}
    G -->|Resuelto| E
    G -->|Rechazo| H[Devolución Proveedor]
```

**Diagramas de Causa-Efecto (Ishikawa)**:
```mermaid
flowchart LR
    EF[EFECTO: No Conformidad] --- M1[Mano de Obra]
    EF --- M2[Método]
    EF --- M3[Máquina]
    EF --- M4[Material]
    EF --- M5[Medio Ambiente]
    EF --- M6[Medición]
    M1 --- M1a[Falta capacitación]
    M1 --- M1b[Fatiga operario]
    M2 --- M2a[SOP desactualizado]
    M3 --- M3a[Calibración equipo]
```

**Árboles de Decisión** (liberación de lote, excursiones térmicas):
```mermaid
flowchart TD
    A[Lote en Cuarentena] --> B{¿Temp OK?}
    B -->|Sí| C{¿Documentos completos?}
    B -->|No| D[Evaluación de Excursión]
    C -->|Sí| E[Liberar Lote]
    C -->|No| F[Solicitar evidencias]
    D --> G{¿Excursión < 2°C?}
    G -->|Sí| H[Evaluación de Estabilidad]
    G -->|No| I[Bloqueo + Devolución]
```

### Reglas
- Usa nodos con texto descriptivo en español.
- Incluye decisiones como rombos `{}` y procesos como rectángulos `[]`.
- Para Ishikawa, usa las 6M: Mano de Obra, Método, Máquina, Material, Medio Ambiente, Medición.
- Basa los flujos en los procedimientos vigentes de Integr@ recuperados.
- Cita el código del documento Integr@ que respalda cada paso del flujo.
