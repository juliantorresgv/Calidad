# Notas del proyecto - Agente de Calidad Integr@ + Mistral

## Objetivo
Crear un agente consultor de calidad basado en Mistral que se conecte a la base de datos SQL Server de **Integr@** (AGV Open Market) para consultar procedimientos, formatos, no conformidades, etc. El agente actúa como consultor experto en calidad, estandarización documental, auditorías, CAPA y gestión de no conformidades para operaciones logísticas farmacéuticas.

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
| 9 | `precargar_faq.py` | Genera respuestas precargadas automaticamente para consultas frecuentes | Mistral API | ~10-20 min (una vez) |

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

# Paso 9 (opcional, una vez): Precargar respuestas frecuentes (FAQ automatico)
$env:MISTRAL_API_KEY="<tu_api_key>"
python Codigo/precargar_faq.py
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

### Módulos avanzados (Grupo 1-5)
- `Codigo/retrieval_avanzado.py` — Retrieval avanzado: NER entidades, RAPTOR, parent-child chunking, late chunking, embeddings en español nativo, fine-tuning de embeddings
- `Codigo/calidad_seguridad.py` — Calidad y seguridad: hallucination detection, citation verification, DLP (Data Loss Prevention), PII redaction en logs
- `Codigo/evaluacion.py` — Evaluación: LLM-as-judge, RAGAS metrics (faithfulness, relevancy, precision, recall), active learning
- `Codigo/observabilidad_avanzada.py` — Observabilidad: OpenTelemetry, Sentry error tracking, latency percentiles (P50/P95/P99), cost alerts, quality dashboards
- `Codigo/capacidades_agenticas.py` — Capacidades agenticas: planificar-ejecutar-verificar, memoria a largo plazo, proactividad, explicabilidad, multi-turn reasoning
- `Codigo/mejoras_extras.py` — Mejoras extras: bias detection, red teaming automatizado, human-in-the-loop (feedback y dataset de fine-tuning), tabla de cambios (change log de documentos)

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

### Tablas de módulos avanzados

| Tabla | Contenido | Módulo |
|-------|-----------|--------|
| `entidades` | Entidades extraídas (NER) por tipo | retrieval_avanzado |
| `documento_entidad` | Relación documento→entidad con frecuencia | retrieval_avanzado |
| `raptor_nodes` | Árbol RAPTOR (resúmenes jerárquicos por nivel) | retrieval_avanzado |
| `chunks_parent` | Chunks padre (contexto amplio) | retrieval_avanzado |
| `chunks_child` | Chunks hijo (búsqueda precisa) | retrieval_avanzado |
| `hallucination_checks` | Resultados de detección de alucinaciones | calidad_seguridad |
| `dlp_checks` | Detecciones de DLP (info sensible) | calidad_seguridad |
| `citation_verifications` | Verificación de citas en respuestas | calidad_seguridad |
| `evaluaciones_respuestas` | Evaluaciones LLM-as-judge por respuesta | evaluacion |
| `ragas_metrics` | Métricas RAGAS (faithfulness, relevancy, etc.) | evaluacion |
| `active_learning_queue` | Cola de preguntas de baja calidad para mejorar | evaluacion |
| `telemetry_spans` | Spans de OpenTelemetry (fallback SQLite) | observabilidad_avanzada |
| `error_log` | Errores capturados (Sentry fallback) | observabilidad_avanzada |
| `latency_metrics` | Métricas de latencia por operación | observabilidad_avanzada |
| `cost_alerts` | Alertas de costo configuradas | observabilidad_avanzada |
| `user_memory` | Memoria a largo plazo del usuario | capacidades_agenticas |
| `user_preferences` | Preferencias del usuario | capacidades_agenticas |
| `user_interests` | Temas de interés del usuario (frecuencia) | capacidades_agenticas |
| `conversation_summary` | Resúmenes de conversaciones anteriores | capacidades_agenticas |
| `reasoning_context` | Contexto de razonamiento multi-turn | capacidades_agenticas |
| `bias_checks` | Resultados de detección de sesgos | mejoras_extras |
| `red_team_results` | Resultados de pruebas de red teaming | mejoras_extras |
| `user_feedback` | Feedback de usuarios sobre respuestas (HITL) | mejoras_extras |
| `training_dataset` | Dataset de fine-tuning generado por feedback | mejoras_extras |
| `expert_reviews` | Revisiones expertas de feedback | mejoras_extras |
| `documento_cambios` | Historial de cambios de documentos | mejoras_extras |
| `documento_versiones` | Versiones de documentos con hash | mejoras_extras |
| `diff_documentos` | Diffs entre versiones de documentos | mejoras_extras |

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

## Mejoras avanzadas implementadas (Grupos 1-5)

### Grupo 1: Retrieval avanzado (`retrieval_avanzado.py`)
- **NER (Named Entity Recognition):** Extrae entidades del dominio HSEQ (procesos, normas, medicamentos, equipos, documentos, roles, métricas, códigos, NCs, fechas, temperaturas) y construye un grafo de entidades.
- **RAPTOR (Recursive Abstractive Processing):** Árbol jerárquico de resúmenes (3 niveles) para recuperar a múltiples granularidades.
- **Parent-child chunking:** Chunks pequeños para búsqueda precisa, chunks padre para contexto amplio.
- **Late chunking:** Genera embedding del documento completo antes de particionar (preserva contexto).
- **Embeddings en español nativo:** Soporte para modelos multilingües (BGE-m3, multilingual-e5-large, etc.).
- **Fine-tuning de embeddings:** Genera dataset de pares (query, positivo, negativo) y script de fine-tuning.

### Grupo 2: Calidad y seguridad (`calidad_seguridad.py`)
- **Hallucination detection:** Detecta afirmaciones no sustentadas en los documentos recuperados (heurística + LLM).
- **Citation verification:** Verifica que los códigos citados en la respuesta existen en la BD.
- **DLP (Data Loss Prevention):** Enmascara información sensible (passwords, API keys, tarjetas, emails, IPs, teléfonos) en las respuestas.
- **PII redaction en logs:** Enmascara PII (cédulas, NITs, emails, teléfonos, IPs, direcciones) en logs.

### Grupo 3: Evaluación (`evaluacion.py`)
- **LLM-as-judge:** Evalúa cada respuesta en 7 dimensiones (faithfulness, relevancy, precision, recall, completeness, clarity, citation quality).
- **RAGAS metrics:** Métricas estándar (faithfulness, answer relevancy, context precision, context recall).
- **Active learning:** Identifica preguntas de baja calidad y las prioriza para mejora.

### Grupo 4: Observabilidad (`observabilidad_avanzada.py`)
- **OpenTelemetry:** Distributed tracing con fallback a SQLite si no hay OTLP endpoint.
- **Sentry error tracking:** Captura automática de excepciones con scrub de PII.
- **Latency percentiles:** P50, P95, P99 por operación.
- **Cost alerts:** Alertas de costo diario, semanal, mensual y por query.
- **Quality dashboards:** Dashboard agregado de calidad, latencia, costos, errores, alucinaciones, DLP y citas.

### Grupo 5: Capacidades agenticas (`capacidades_agenticas.py`)
- **Planificar-ejecutar-verificar:** El agente planifica pasos antes de responder y verifica el resultado.
- **Memoria a largo plazo:** Recuerda preferencias, intereses y resúmenes de conversaciones del usuario entre sesiones.
- **Proactividad:** Sugiere acciones proactivas (documentos vencidos, NCs abiertas, temas de interés).
- **Explicabilidad:** Explica el proceso de retrieval (pasos, scores, documentos usados).
- **Multi-turn reasoning:** Mantiene contexto complejo entre turnos, detecta cambios de tema, rastrea temas resueltos.

### Grupo 6: Mejoras extras (`mejoras_extras.py`)
- **Bias detection:** Detecta sesgos de género, región, edad, discapacidad y cultural en las respuestas. Genera versión neutralizada automáticamente.
- **Red teaming automatizado:** 16 ataques predefinidos (jailbreak/DAN, prompt injection, data extraction, SQL injection, manipulación emocional, content violation, encoding attacks) para probar la seguridad del agente.
- **Human-in-the-loop:** Los usuarios califican respuestas (1-3), proporcionan feedback tipado (correcta, incorrecta, incompleta, irrelevante, alucinación) y corrigen respuestas. Las correcciones se acumulan en un dataset de fine-tuning exportable en JSONL.
- **Tabla de cambios:** Registra historial de cambios de cada documento (creación, revisión, aprobación, publicación, obsoleto, modificación) con autor, revisor, aprobador, versiones, diffs y descripción. Sincronizable desde `PROCEDIMIENTOSCAMBIO` de Integr@.

## Nuevas funcionalidades recientes

### Grupo 7: Mejoras de UI y operación
- **Filtros avanzados de documentos:** Búsqueda por proceso, tipo de documento, estado, rango de vigencia, fechas y responsables (elaborador, revisor, aprobador, publicador).
- **Dashboard de salud del sistema:** Pestaña `Salud del Sistema` que reporta estado de SQL Server, SQLite, ChromaDB, FAISS y proveedores LLM.
- **Visualización interactiva del grafo:** Red de procesos, documentos, responsables y entidades con `vis.js`, filtrable por tipo de nodo.
- **Historial de conversaciones persistente:** Exportación a Markdown, TXT y JSON; importación desde JSON en la UI.
- **Indicadores de uso:** Tabla `usage_stats` y dashboard en FinOps con consultas por usuario, rol, área y proceso.
- **Backup y restauración:** ZIP con SQLite, ChromaDB, FAISS y backup JSON de resúmenes; botones en `Sincronización`.

### Grupo 8: Retrieval y calidad
- **Caché semántico con embeddings reales:** Tabla `cache_semantico` con similitud coseno > 0.92 para reducir costos y latencia.
- **Chunking avanzado:** Late chunking + chunking jerárquico (headers HTML) + chunking semántico en `_get_relevant_sections`.
- **Reintentos de embeddings fallidos:** Método `reintentar_embeddings_fallidos()` que genera embeddings solo para documentos sin embedding.
- **Indicadores de calidad RAG:** Recall@K, Precision@K, MRR y métricas RAGAS en el dashboard FinOps.
- **Pipeline de evaluación automática:** `evaluar_rag.py` guarda resultados en SQLite (`pipeline_eval`) e incluye instrucciones para programar ejecución diaria vía Windows Task Scheduler.

- **FAQ precargadas:** Tabla `faq_precargadas` con preguntas/respuestas generadas automaticamente via `precargar_faq.py`. Búsqueda por hash exacto, keywords o embeddings antes de cualquier retrieval; respuesta < 1s.

### Grupo 9: Proactividad
- **Agente proactivo por rol:** `ProactivityEngine` genera sugerencias personalizadas según rol del usuario (admin, calidad, auditor, operador, usuario) y muestra un panel expandible en el chat.

### Tablas SQLite adicionales
- `cache_semantico` - caché de respuestas con embeddings
- `usage_stats` - métricas de uso por usuario/área/proceso
- `faq_precargadas` - preguntas/respuestas precargadas para respuesta instantánea
- `rag_eval_summary` - resumen de evaluaciones RAG
- `pipeline_eval` - resultados de golden questions + RAGAS
- Backups manuales en `backups/*.zip`
