# Skill: Búsqueda por Filtros + Semántica

## Cuándo activar
Cuando el usuario pida buscar documentos combinando filtros con búsqueda semántica. Ej: "procedimientos de refrigeración publicados en 2024", "formatos del proceso WH vigentes", "procedimientos de cadena de frío obsoletos".

## Instrucciones

### Filtros disponibles

El agente puede combinar los siguientes filtros con búsqueda semántica:

| Filtro | Campo Integr@ | Valores |
|--------|--------------|---------|
| Proceso | `ProcesoCod` | GC, WH, MQ, SR, ST, RH, LTL, etc. |
| Tipo documento | `TipoDocumento` | Base Documental, Regulatorio |
| Estado | `PROCEDIMIENTOS_ESTADO` | P (Publicado), O (Obsoleto), E (Elaborado), etc. |
| Fecha publicación | `PROCEDIMIENTOS_FCHPUBLICACION` | Rango de fechas |
| Vigencia | `PROCEDIMIENTOS_VIGENCIA` | Días de vigencia |
| Código | `PROCEDIMIENTOS_COD` | Búsqueda exacta o parcial |
| Nombre | `PROCEDIMIENTOS_NOMBRE` | Búsqueda textual |

### Sintaxis de consulta

Cuando el usuario combine filtros con texto libre, el agente debe:

1. **Identificar filtros explícitos** en la pregunta:
   - Proceso: "del proceso WH", "de almacenamiento", "de calidad"
   - Estado: "vigentes", "publicados", "obsoletos", "elaborados"
   - Tipo: "regulatorios", "base documental"
   - Fecha: "de 2024", "del último año", "recientes"
   - Código: "que empiecen con PGC", "código FGC-16"

2. **Extraer texto libre** para búsqueda semántica:
   - Resto de la pregunta que no es filtro

3. **Aplicar filtros primero** (reducen el universo):
   - Filtrar por proceso, estado, tipo, fecha
   - Excluir obsoletos por defecto (a menos que el usuario los pida explícitamente)

4. **Búsqueda semántica** sobre el subconjunto filtrado:
   - Usar embeddings para encontrar los más relevantes
   - Combinar con TF-IDF para coincidencias léxicas

### Ejemplos

**Ejemplo 1:** "procedimientos de refrigeración publicados en 2024"
- Filtros: estado=P, fecha_publicacion entre 2024-01-01 y 2024-12-31
- Semántico: "refrigeración"

**Ejemplo 2:** "formatos del proceso WH vigentes"
- Filtros: proceso=WH, estado=P, tipo contiene "formato"
- Semántico: (no hay texto libre adicional)

**Ejemplo 3:** "procedimientos de cadena de frío obsoletos"
- Filtros: estado=O (el usuario pide obsoletos explícitamente)
- Semántico: "cadena de frío"
- Nota: advertir al usuario que son obsoletos

### Formato de salida
```
BÚSQUEDA POR FILTROS
Filtros aplicados:
  - Proceso: [valor]
  - Estado: [valor]
  - Tipo: [valor]
  - Fecha: [rango]
Documentos encontrados: [N]
Resultados (top 5):
  1. [Código] - [Nombre] (estado: P, fecha: YYYY-MM-DD)
  2. ...
```
