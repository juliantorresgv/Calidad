# Notas del proyecto - Agente de Calidad Integr@ + Mistral

## Objetivo
Crear un agente consultor de calidad basado en Mistral que se conecte a la base de datos SQL Server de **Integr@** (Solistica) para consultar procedimientos, formatos, no conformidades, etc. El agente actúa como consultor experto en calidad, estandarización documental, auditorías, CAPA y gestión de no conformidades para operaciones logísticas farmacéuticas.

## Arquitectura actual

```
SQL Server Integr@ (10.238.66.14)
        |
        v
build_document_index.py ──→ SQLite: procedimientos (2835 docs)
        |
        v
generate_embeddings.py  ──→ ChromaDB + FAISS + SQLite (embeddings)
        |
        v
cluster_temas.py        ──→ SQLite: temas, documento_tema + grafo JSON
        |
        v
glosario.py             ──→ SQLite: glosario (40+ términos)
diccionario_datos.py    ──→ SQLite: diccionario_datos (campos Integr@)
generar_resumenes.py    ──→ SQLite: resumenes + tabla_jerarquica + alertas_vencimiento
inventario_metadatos.py ──→ SQLite: inventario_metadatos + grafo_nodos + grafo_aristas
        |
        v
graph_rag.py            ──→ Agente Graph RAG híbrido
  ├── system_prompt.md  (consultor de calidad)
  ├── skills/*.md       (6 skills dinámicos)
  ├── Glosario          (contexto automático)
  ├── Resúmenes         (contexto enriquecido)
  ├── Grafo persistente (SQLite)
  ├── Filtrado obsoletos (estado O excluido)
  └── Mistral           (respuesta final en español)
```

## Pipeline completo (8 pasos)

| Paso | Script | Qué hace | Requiere | Tiempo |
|------|--------|----------|----------|--------|
| 1 | `build_document_index.py` | Descarga docs de SQL Server, HTML→texto, guarda en SQLite | SQL Server | ~2 min |
| 2 | `generate_embeddings.py` | Embeddings Mistral → ChromaDB + FAISS + SQLite | Mistral API | ~30-40 min |
| 3 | `cluster_temas.py` | K-Means + TF-IDF → temas + grafo JSON | Paso 2 | ~30 seg |
| 4 | `glosario.py` | Instala 40+ términos de calidad+logística en SQLite | Nada | ~1 seg |
| 5 | `diccionario_datos.py` | Instala diccionario de campos de Integr@ en SQLite | Nada | ~1 seg |
| 6 | `generar_resumenes.py` | Resúmenes ejecutivos + tabla jerárquica + alertas vencimiento | Mistral API | ~20-30 min |
| 7 | `inventario_metadatos.py` | Inventario de metadatos + grafo persistente en SQLite | Paso 1 | ~10 seg |
| 8 | `graph_rag.py` | Agente Graph RAG con todas las mejoras | Pasos 1-7 | interactivo |

## Comandos de ejecución

```powershell
# ─── Pipeline completo ───

# Paso 1: Extraer texto de todos los procedimientos
$env:INTEGRA_DB_SERVER="10.238.66.14"
python Codigo/build_document_index.py

# Paso 2: Generar embeddings con Mistral
$env:MISTRAL_API_KEY="<tu_api_key>"
python Codigo/generate_embeddings.py

# Paso 3: Agrupar por temas
python Codigo/cluster_temas.py

# Paso 4: Instalar glosario
python Codigo/glosario.py

# Paso 5: Instalar diccionario de datos
python Codigo/diccionario_datos.py

# Paso 6: Generar resúmenes + jerarquía + alertas
$env:MISTRAL_API_KEY="<tu_api_key>"
python Codigo/generar_resumenes.py

# Paso 7: Inventario de metadatos + grafo persistente
python Codigo/inventario_metadatos.py

# Paso 8: Ejecutar agente
$env:INTEGRA_DB_SERVER="10.238.66.14"
$env:MISTRAL_API_KEY="<tu_api_key>"
python Codigo/graph_rag.py
```

## Comandos del agente (paso 8)

| Comando | Qué hace |
|---------|----------|
| `/stats` | Estadísticas del grafo |
| `/temas` | Lista temas detectados |
| `/jerarquia` | Tabla jerárquica procesos→tipos→docs |
| `/jerarquia almacenamiento` | Filtra por proceso |
| `/vencidos` | Documentos vencidos/por vencer |
| `/resumen PGC-16-15` | Resumen ejecutivo de un documento |
| `/glosario IQ` | Busca términos del glosario |
| `/retrieve ¿cómo...?` | Solo recuperación (sin LLM) |
| `/nodo doc:PGC-16-15` | Explora nodo del grafo |
| Pregunta normal | Graph RAG completo → respuesta con Mistral |

## Skills del agente

| Skill | Archivo | Se activa con |
|-------|---------|---------------|
| Mermaid | `skills/mermaid.md` | Flujos, diagramas, Ishikawa, árboles de decisión |
| CAPA | `skills/capa.md` | Causa raíz, 5 porqués, FMEA, AMEF, 6M, NPR |
| No Conformidad | `skills/no_conformidad.md` | NC, hallazgos, desviaciones, planes de acción |
| Auditoría | `skills/auditoria.md` | Simular auditoría, roleplay, Invima/ISO |
| Checklists | `skills/checklists.md` | Formatos, checklists, WMS, Power Apps |
| Refactoring SOPs | `skills/refactoring_sops.md` | Revisar borradores, auditar calidad documental |

## Estructura de archivos

### Código principal
- `Codigo/build_document_index.py` — Paso 1: extrae texto de 2835 docs a SQLite
- `Codigo/generate_embeddings.py` — Paso 2: embeddings Mistral por lote
- `Codigo/cluster_temas.py` — Paso 3: K-Means + TF-IDF → temas + grafo JSON
- `Codigo/glosario.py` — Paso 4: glosario de dominio Calidad+Logística
- `Codigo/diccionario_datos.py` — Paso 5: diccionario de campos de Integr@
- `Codigo/generar_resumenes.py` — Paso 6: resúmenes + jerarquía + alertas
- `Codigo/inventario_metadatos.py` — Paso 7: inventario + grafo persistente
- `Codigo/graph_rag.py` — Paso 8: agente Graph RAG híbrido

### Configuración del agente
- `Codigo/system_prompt.md` — System prompt del consultor de calidad
- `Codigo/governance.py` — Governance, guardrails, políticas, reglas de seguridad, auditoría
- `Codigo/memoria.py` — Cache semántico, knowledge store, sesiones persistentes, checkpoints, estado de tareas
- `Codigo/context_manager.py` — Context management: sliding window, resumen automático, presupuesto de tokens, detección de cambio de tema
- `Codigo/content_moderation.py` — Content moderation: toxicidad, hate speech, acoso, autolesión, spam
- `Codigo/skills/` — Skills dinámicos del agente
  - `README.md`, `mermaid.md`, `capa.md`, `no_conformidad.md`, `auditoria.md`, `checklists.md`, `refactoring_sops.md`

### Datos generados (no versionar)
- `indice_procedimientos.db` — SQLite con todas las tablas
- `chroma_db/` — ChromaDB persistente
- `faiss_index.bin` — FAISS index
- `tabla_jerarquica.json` — Tabla jerárquica en JSON

### Utilidades y exploración
- `Codigo/integra_db_client.py` — cliente SQL Server de solo lectura
- `Codigo/integra_procedimientos.py` — helper de consultas PROCEDIMIENTOS
- `Codigo/html_to_pdf.py` — conversión HTML→PDF con Edge headless
- `Codigo/exportar_procedimientos_muestra.py` — exporta muestra a CSV/Excel
- `Codigo/map_schema.py` — genera mapa de esquema (132 tablas)
- `Codigo/schema_map.json` — mapa completo de columnas por tabla
- `Codigo/extract_docs.py` / `extract_reunion.py` — extracción de documentación

### Pruebas
- `Codigo/test_mistral.py` — prueba API Mistral
- `Codigo/test_sql.py` — prueba conexión SQL Server
- `Codigo/test_integra.py` — prueba conexión web Integr@

## Tablas SQLite generadas

| Tabla | Contenido | Paso |
|-------|-----------|------|
| `procedimientos` | Documentos + texto extraído | 1 |
| `embeddings` | Backup de embeddings | 2 |
| `temas` | Temas detectados por clustering | 3 |
| `documento_tema` | Relación documento→tema | 3 |
| `glosario` | Términos de calidad+logística | 4 |
| `diccionario_datos` | Campos de Integr@ explicados | 5 |
| `resumenes` | Resúmenes ejecutivos por documento | 6 |
| `tabla_jerarquica` | Estructura Proceso→Tipo→Documento | 6 |
| `alertas_vencimiento` | Documentos vencidos/por vencer | 6 |
| `inventario_metadatos` | Inventario consolidado por categoría | 7 |
| `grafo_nodos` | Nodos del grafo persistente | 7 |
| `grafo_aristas` | Aristas del grafo persistente | 7 |

## Configuración

1. API key de Mistral:
```powershell
$env:MISTRAL_API_KEY="<tu_api_key>"
```

2. Servidor SQL de Integr@:
```powershell
$env:INTEGRA_DB_SERVER="10.238.66.14"
```

3. Instalar dependencias:
```powershell
pip install -r Codigo/requirements.txt
```

4. Credenciales de Integr@ en `credenciales.txt` (NO versionar).

## Hallazgos clave

- Integr@ es una aplicación web ASP.NET con base de datos SQL Server.
- La forma recomendada de consumir la información es consultar directamente las tablas.
- Se mapearon 132 tablas en el esquema `dbo`.
- `PROCEDIMIENTOS_WORD` contiene HTML (no PDF binario).
- Se logró conexión exitosa a SQL Server con `pyodbc` + `ODBC Driver 17 for SQL Server`.
- La URL web devuelve `502 Bad Gateway` desde este entorno (no se usa web automation).

## Tablas principales de Integr@

- `PROCEDIMIENTOS` — documentos base documental y regulatorios
- `ProcedimientoEstado` — historial de cambios de estado
- `PROCEDIMIENTOSCAMBIO` / `PROCEDIMIENTOAREA` / `PROCEDIMIENTOSANEXO` / `PROCEDIMIENTOSFORMATO` / `PROCEDIMIENTOSNORMAS` — relaciones
- `Proceso` — maestro de procesos
- `TipoDocumento` — tipos de documento
- `USUARIOT` / `TUsuarioC` — usuarios
- `NoConformidad`, `CorreccionNC`, `PlanesAccionNC` — no conformidades
- `DocumenExternos`, `Formatos`, `Glosario`, `Comunicaciones`, `FundamentosCorp`

## Estados de PROCEDIMIENTOS (inferidos)

| Estado | Significado probable |
|--------|----------------------|
| `E`    | Elaborado            |
| `D`    | Devuelto (con observaciones) |
| `R`    | Revisado por responsable de proceso |
| `Q`    | Revisado por Calidad / QA |
| `A`    | Aprobado gerencial     |
| `P`    | Publicado (vigente)  |
| `O`    | Obsoleto (excluido por defecto) |
| `Z`    | Estado especial (pendiente de confirmar) |

Secuencia: `E -> D -> R -> Q -> A -> P` y luego puede pasar a `O`.

## Reglas del agente

- **Fuente primaria:** SQL Server de Integr@ (no SharePoint, no Excel sueltos)
- **Exclusión de obsoletos:** estado `O` se excluye automáticamente
- **Solo documentos vigentes:** estado `P` (Publicado) por defecto
- **Respuestas en español** con citas al código del documento
- **Skills dinámicos:** se cargan solo cuando son relevantes (ahorro de tokens)
- **Glosario automático:** se incluye en el contexto cuando hay términos relevantes
- **Resúmenes enriquecidos:** se incluyen en el contexto de cada documento recuperado
- **Grafo persistente:** se carga desde SQLite, no se reconstruye cada vez
