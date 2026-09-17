"""
Graph RAG para Integra: combina grafo de conocimiento + BM25 + embeddings
para recuperación híbrida de documentos.

Arquitectura:
  1. Nodos: documentos, procesos, tipos, formatos, normas, usuarios, temas
  2. Aristas: relaciones entre entidades (pertenece a, usa formato, cumple norma, etc.)
  3. Recuperación:
     a) Seed: embeddings (semántico) + BM25 (lexical) → documentos iniciales
     b) Expand: traversar el grafo desde los seeds → documentos relacionados
     c) Rerank: cross-encoder local (mas rapido y mejor que LLM)
     d) Context: incluir entidades y relaciones del grafo en el prompt

Uso:
    from graph_rag import GraphRAG
    rag = GraphRAG()
    resultados = rag.retrieve("¿cómo se controla la temperatura?")
    answer = rag.ask("¿cómo se controla la temperatura?")
"""
import json
import os
import pickle
import re
import shutil
import sqlite3
import sys
import time
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import faiss
import networkx as nx
import numpy as np
from openai import OpenAI
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity, linear_kernel

# BM25 para mejor retrieval lexico que TF-IDF
try:
    from rank_bm25 import BM25Okapi
    _HAS_BM25 = True
except ImportError:
    _HAS_BM25 = False

# Cross-encoder para reranking local (mas rapido y mejor que LLM)
try:
    from sentence_transformers import CrossEncoder
    _HAS_CROSSENCODER = True
except ImportError:
    _HAS_CROSSENCODER = False

# Glosario de dominio
from glosario import glosario_para_contexto, buscar_termino, GLOSARIO

# Observabilidad (LangFuse + FinOps)
from observabilidad import Observabilidad

# Governance (guardrails: prompt injection, PII, SQL, tópicos, rate limit)
try:
    from governance import Governance
    _HAS_GOVERNANCE = True
except ImportError:
    _HAS_GOVERNANCE = False

# Content moderation (toxicidad, hate speech, acoso, spam)
try:
    from content_moderation import ContentModeration
    _HAS_MODERATION = True
except ImportError:
    _HAS_MODERATION = False

# Memoria (cache semantico, sesiones, knowledge store)
try:
    from memoria import Memoria
    _HAS_MEMORIA = True
except ImportError:
    _HAS_MEMORIA = False

# ─── Modulos avanzados (Grupo 1-5) ───
# Retrieval avanzado: NER, RAPTOR, parent-child, late chunking, embeddings ES, fine-tuning
try:
    from retrieval_avanzado import (
        extract_entities_llm, search_by_entities, raptor_retrieve,
        retrieve_parent_child, build_all_advanced_indices,
        get_spanish_embedding_model, late_chunking,
    )
    _HAS_RETRIEVAL_ADV = True
except ImportError:
    _HAS_RETRIEVAL_ADV = False

# Calidad y seguridad: hallucination detection, citation verification, DLP, PII redaction
try:
    from calidad_seguridad import (
        detect_hallucination, verify_citations, add_citations_if_missing,
        apply_dlp, check_input_dlp, redact_pii_in_log, safe_log,
        init_quality_tables, save_hallucination_check,
        save_dlp_check, save_citation_verification,
    )
    _HAS_CALIDAD_SEG = True
except ImportError:
    _HAS_CALIDAD_SEG = False

# Evaluacion: LLM-as-judge, RAGAS, active learning
try:
    from evaluacion import (
        llm_as_judge, calculate_ragas, get_quality_stats,
        init_eval_tables, save_evaluation, save_ragas,
        suggest_improvements,
    )
    _HAS_EVALUACION = True
except ImportError:
    _HAS_EVALUACION = False

# Observabilidad avanzada: OpenTelemetry, Sentry, latency percentiles, cost alerts, dashboards
try:
    from observabilidad_avanzada import (
        TelemetryManager, get_telemetry, trace_operation,
        init_sentry, capture_exception,
        record_latency, get_latency_percentiles, get_latency_by_operation,
        check_cost_alerts, get_cost_summary, get_quality_dashboard,
        init_observability_tables,
    )
    _HAS_OBS_ADV = True
except ImportError:
    _HAS_OBS_ADV = False

# Capacidades agenticas: planificar-ejecutar-verificar, memoria largo plazo, proactividad, explicabilidad, multi-turn
try:
    from capacidades_agenticas import (
        AgenticPlanner, LongTermMemory, ProactivityEngine,
        ExplainabilityEngine, MultiTurnReasoner,
        init_agentic_tables,
    )
    _HAS_AGENTIC = True
except ImportError:
    _HAS_AGENTIC = False

# Mejoras extras: bias detection, red teaming, human-in-the-loop, tabla de cambios
try:
    from mejoras_extras import (
        detect_bias, check_response_bias, run_red_team_test, save_red_team_results,
        get_red_team_summary, init_hitl_tables, submit_feedback, get_feedback_stats,
        get_training_dataset, export_training_dataset, review_feedback,
        init_change_log_tables, registrar_cambio, guardar_version_documento,
        guardar_diff, obtener_historial_cambios, obtener_versiones_documento,
        obtener_diffs_documento, sincronizar_cambios_desde_integra,
        get_change_log_stats, init_mejoras_extras_tables, save_bias_check,
        get_bias_stats, RED_TEAM_ATTACKS,
    )
    _HAS_MEJORAS_EXTRAS = True
except ImportError:
    _HAS_MEJORAS_EXTRAS = False

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DB_PATH = Path(__file__).parent.parent / "indice_procedimientos.db"
CHROMA_PATH = Path(__file__).parent.parent / "chroma_db"
FAISS_PATH = Path(__file__).parent.parent / "faiss_index.bin"
MISTRAL_BASE_URL = "https://api.mistral.ai/v1"
CHAT_MODEL = os.environ.get("MISTRAL_MODEL", "mistral-small-latest")
EMBED_MODEL = "mistral-embed"
EMBED_DIM = 1024

# Pesos para scoring híbrido
W_SEMANTIC = 0.4   # embeddings
W_LEXICAL = 0.3    # TF-IDF
W_GRAPH = 0.3      # grafo
TOP_K_SEED = 10    # seeds iniciales
TOP_K_FINAL = 5    # documentos finales para el LLM
MAX_GRAPH_HOPS = 2  # profundidad de traversa del grafo

# Reciprocal Rank Fusion (RRF) - reemplaza suma ponderada
USE_RRF = True  # Si True, usa RRF en vez de pesos fijos
RRF_K = 60  # Constante de suavizado RRF (estandar: 60)

# ─── Query Expansion: diccionario de abreviaciones del dominio ───
QUERY_EXPANSION_DICT = {
    "iq": "instalacion qualification instalacion cualificacion",
    "oq": "operational qualification operacion cualificacion",
    "pq": "performance qualification desempeno cualificacion",
    "nc": "no conformidad no conforme",
    "capa": "corrective action preventive action accion correctiva preventiva",
    "sop": "standard operating procedure procedimiento operativo estandar",
    "fmea": "failure mode effects analysis analisis modo efecto falla",
    "amef": "analisis modo efecto falla fallo",
    "npr": "numero prioridad riesgo severity ocurrence detection",
    "epp": "equipo proteccion personal equipos proteccion personal",
    "fds": "ficha datos seguridad material safety data sheet msds",
    "wms": "warehouse management system sistema gestion almacen",
    "cedi": "centro distribucion centro distribucion",
    "hseq": "health safety environment quality salud seguridad ambiente calidad",
    "sst": "seguridad salud trabajo occupational health safety",
    "kpi": "key performance indicator indicador desempeno clave",
    "raci": "responsible accountable consulted informed responsable",
    "iso": "international organization standardization organizacion internacional normalizacion",
    "invima": "instituto vigilancia medicamentos alimentos instituto nacional vigilancia medicamentos alimentos",
    "fda": "food drug administration administracion alimentos medicamentos",
    "oms": "organizacion mundial salud world health organization",
    "poe": "procedimiento operativo estandar standard operating procedure",
    "lote": "batch lote produccion",
    "merma": "perdida desperdicio loss waste",
    "devolucion": "return devolucion producto retorno",
    "recepcion": "recepcion ingreso mercancia goods receipt",
    "despacho": "despacho salida mercancia dispatch shipping",
    "almacenamiento": "almacenamiento storage bodega warehouse",
    "cuarto frio": "cold room cuarto refrigerado cadena frio",
    "cadena de frio": "cold chain cadena refrigerada temperatura controlada",
    "calidad": "quality assurance calidad aseguramiento",
    "auditoria": "audit auditoria inspeccion revision",
    "vencimiento": "expiracion vencimiento caducidad expiry expiration",
    "vigente": "vigente publicado actual valido current published",
    "obsoleto": "obsoleto descontinuado deprecated obsolete",
    "no conformidad": "no conforme no conformidad nonconformity non conformity hallazgo",
    "plan de accion": "action plan plan accion corrective preventive",
    "traceabilidad": "traceability trazabilidad rastreabilidad",
    "contaminacion cruzada": "cross contamination contaminacion cruzada",
}

# ──────────────────────────────────────────────
# System Prompt: se carga desde system_prompt.md
# ──────────────────────────────────────────────

SYSTEM_PROMPT_PATH = Path(__file__).parent / "system_prompt.md"
SKILLS_DIR = Path(__file__).parent / "skills"

# Mapeo de palabras clave → skill
SKILL_TRIGGERS = {
    "mermaid.md": ["flujo", "flujograma", "diagrama", "mermaid", "mapa de proceso",
                   "árbol de decisión", "ishikawa", "causa-efecto", "bpmn"],
    "capa.md": ["causa raíz", "5 porqués", "cinco porqués", "fmea", "amef", "6m",
                "capa", "acción correctiva", "acción preventiva",
                "npr", "severidad", "ocurrencia", "detección"],
    "no_conformidad.md": ["no conformidad", "no conforme", "hallazgo", "desviación",
                          "corrección", "plan de acción", "nc ", "n.c.",
                          "registrar nc", "gestionar nc", "reportar nc"],
    "auditoria.md": ["auditoría", "auditoria", "simular auditor", "roleplay",
                     "invima", "iso 9001", "iso 45001", "auditado", "auditor",
                     "lista de verificación", "hallazgo de auditoría"],
    "checklists.md": ["checklist", "formato", "matriz de captura", "wms",
                      "power apps", "lista de verificación", "campo obligatorio",
                      "foto obligatoria", "firma digital", "alerta condicional"],
    "refactoring_sops.md": ["revisar borrador", "auditar documento", "refactoring",
                            "mejorar sop", "calidad documental", "términos ambiguos",
                            "raci", "revisar procedimiento"],
    "busqueda_filtros.md": ["publicados en", "del proceso", "del año", "vigentes",
                            "obsoletos", "por estado", "filtrar", "por proceso",
                            "por tipo", "por fecha", "de 2024", "de 2023"],
    "comparador_versiones.md": ["comparar versiones", "qué cambió", "diferencias entre",
                                "versión anterior", "historial de cambios", "comparar documentos"],
    "detector_duplicados.md": ["duplicados", "documentos similares", "redundantes",
                               "posibles duplicados", "documentos idénticos"],
    "exportar.md": ["exportar", "descargar", "guardar pdf", "generar pdf", "generar word",
                    "exportar a excel", "guardar respuesta", "descargar respuesta"],
}


def _load_system_prompt() -> str:
    """Carga el system prompt desde el archivo .md."""
    if SYSTEM_PROMPT_PATH.exists():
        return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    return (
        "Eres un agente experto en la plataforma Integr@ de Solistica. "
        "Responde en español, de forma clara y concisa. "
        "Cita el código del documento del que extraes la información."
    )


def _load_relevant_skills(question: str) -> str:
    """Carga los skills relevantes a la pregunta del usuario."""
    question_lower = question.lower()
    loaded_skills = []

    for skill_file, triggers in SKILL_TRIGGERS.items():
        for trigger in triggers:
            if trigger in question_lower:
                skill_path = SKILLS_DIR / skill_file
                if skill_path.exists():
                    content = skill_path.read_text(encoding="utf-8")
                    loaded_skills.append(f"\n\n=== SKILL: {skill_file} ===\n{content}")
                break  # no cargar el mismo skill dos veces

    return "".join(loaded_skills)


SYSTEM_PROMPT_CALIDAD = _load_system_prompt()


class GraphRAG:
    """Motor de Graph RAG con recuperación híbrida."""

    def __init__(self, db_path: Path = DB_PATH, llm_primary: str = "openai",
                 llm_fallback: list[str] | None = None):
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)

        # Proveedores LLM con fallback automatico
        from llm_providers import LLMProviders
        # Si se usa Ollama exclusivamente, no requiere MISTRAL_API_KEY
        if llm_primary != "ollama" and not os.environ.get("MISTRAL_API_KEY"):
            raise SystemExit("Falta MISTRAL_API_KEY")
        fallback_order = llm_fallback if llm_fallback is not None else ["openai", "mistral", "ollama", "groq", "gemini"]
        self.llm = LLMProviders(
            primary=llm_primary,
            fallback_order=fallback_order,
        )
        self.client = self.llm.clients.get(self.llm.primary, (None, None))[0] if hasattr(self.llm, "clients") else getattr(self.llm, "client", None)  # compatibilidad hacia atras

        # Observabilidad (LangFuse + FinOps)
        self.obs = Observabilidad()

        # Governance (guardrails de entrada y salida)
        if _HAS_GOVERNANCE:
            self.governance = Governance()
            print(f"  [GraphRAG] Governance: guardrails activos (prompt injection, PII, SQL, rate limit)")
        else:
            self.governance = None

        # Content moderation
        if _HAS_MODERATION:
            self.moderation = ContentModeration()
            print(f"  [GraphRAG] Content moderation: activo (toxicidad, hate speech, acoso)")
        else:
            self.moderation = None

        # Memoria (cache semantico + sesiones)
        if _HAS_MEMORIA:
            self.memoria = Memoria()
            print(f"  [GraphRAG] Memoria: cache semantico + sesiones activo")
        else:
            self.memoria = None

        # ─── Modulos avanzados ───

        # Calidad y seguridad (hallucination, citations, DLP, PII)
        if _HAS_CALIDAD_SEG:
            init_quality_tables(self.conn)
            self.calidad_seguridad = True
            print(f"  [GraphRAG] Calidad/Seguridad: hallucination detection + DLP + PII redaction activos")
        else:
            self.calidad_seguridad = False

        # Evaluacion (LLM-as-judge, RAGAS, active learning)
        if _HAS_EVALUACION:
            init_eval_tables(self.conn)
            self.evaluacion = True
            print(f"  [GraphRAG] Evaluacion: LLM-as-judge + RAGAS + active learning activos")
        else:
            self.evaluacion = False

        # Observabilidad avanzada (OpenTelemetry, Sentry, latency, cost alerts)
        if _HAS_OBS_ADV:
            init_observability_tables(self.conn)
            self.telemetry = get_telemetry()
            init_sentry()  # Inicializa Sentry si SENTRY_DSN esta configurado
            print(f"  [GraphRAG] Observabilidad: OpenTelemetry + Sentry + latency + cost alerts activos")
        else:
            self.telemetry = None

        # Capacidades agenticas (planificar-ejecutar-verificar, memoria LP, proactividad, explicabilidad, multi-turn)
        if _HAS_AGENTIC:
            init_agentic_tables(self.conn)
            self.planner = AgenticPlanner(self.client)
            self.long_term_memory = LongTermMemory(self.db_path)
            self.proactivity = ProactivityEngine(self.db_path)
            self.explainer = ExplainabilityEngine()
            self.multi_turn = MultiTurnReasoner(self.db_path)
            print(f"  [GraphRAG] Capacidades agenticas: planner + memoria LP + proactividad + explicabilidad + multi-turn activos")
        else:
            self.planner = None
            self.long_term_memory = None
            self.proactivity = None
            self.explainer = None
            self.multi_turn = None

        # Retrieval avanzado (NER, RAPTOR, parent-child)
        self.retrieval_adv = _HAS_RETRIEVAL_ADV
        if self.retrieval_adv:
            print(f"  [GraphRAG] Retrieval avanzado: NER + RAPTOR + parent-child + late chunking + embeddings ES activos")

        # Mejoras extras (bias detection, red teaming, HITL, change log)
        if _HAS_MEJORAS_EXTRAS:
            init_mejoras_extras_tables(self.conn)
            self.mejoras_extras = True
            print(f"  [GraphRAG] Mejoras extras: bias detection + red teaming + human-in-the-loop + tabla de cambios activos")
        else:
            self.mejoras_extras = False

        # Cache de embeddings de query (evita llamar Mistral en consultas repetidas)
        self._query_emb_cache: dict[str, list[float]] = {}

        # Cache semantico de respuestas con embeddings reales
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS cache_semantico (
                query_hash TEXT PRIMARY KEY,
                query_text TEXT,
                embedding BLOB,
                respuesta TEXT,
                modelo TEXT,
                created_at TEXT,
                hits INTEGER DEFAULT 0
            )
        """)
        self.conn.commit()

        # Tabla de uso por usuario, rol, area y proceso
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS usage_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                username TEXT,
                role TEXT,
                area TEXT,
                timestamp TEXT,
                question TEXT,
                proceso_principal TEXT,
                docs_count INTEGER,
                provider TEXT,
                cached INTEGER DEFAULT 0
            )
        """)
        self.conn.commit()

        # Tabla de preguntas y respuestas precargadas (FAQ)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS faq_precargadas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pregunta TEXT UNIQUE,
                pregunta_hash TEXT UNIQUE,
                pregunta_embedding BLOB,
                respuesta TEXT,
                keywords TEXT,
                categoria TEXT,
                proceso TEXT,
                fuente TEXT,
                uso_count INTEGER DEFAULT 0,
                created_at TEXT,
                updated_at TEXT,
                documentos_citados TEXT,
                estados_documentos TEXT,
                tipo_contenido TEXT,
                vigente_hasta TEXT,
                feedback_positivo INTEGER DEFAULT 0,
                feedback_negativo INTEGER DEFAULT 0,
                activa INTEGER DEFAULT 1
            )
        """)
        self.conn.commit()

        # Migrar columnas si la tabla ya existia con schema antiguo
        self._migrar_faq_precargadas()

        # Tabla de feedback por documento para reranking
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS feedback_documentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pregunta TEXT,
                respuesta TEXT,
                codigo TEXT,
                feedback TEXT,
                timestamp TEXT DEFAULT (datetime('now', 'localtime'))
            )
        """)
        self.conn.commit()

        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS doc_feedback_stats (
                codigo TEXT PRIMARY KEY,
                positivo INTEGER DEFAULT 0,
                negativo INTEGER DEFAULT 0,
                total INTEGER DEFAULT 0,
                score_boost REAL DEFAULT 0.0,
                updated_at TEXT
            )
        """)
        self.conn.commit()

        # Tabla de cache persistente de embeddings de query
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS cache_embeddings (
                query_hash TEXT PRIMARY KEY,
                query_text TEXT,
                embedding BLOB,
                modelo TEXT,
                created_at TEXT
            )
        """)
        self.conn.commit()

        # Cargar datos
        self._load_documents()
        self._load_embeddings()
        self._build_tfidf()
        self._build_graph()
        self.history: list[dict] = []

    # ──────────────────────────────────────────────
    # Carga de datos
    # ──────────────────────────────────────────────

    def _load_documents(self):
        """Carga todos los documentos con texto desde SQLite."""
        rows = self.conn.execute("""
            SELECT codigo, nombre, estado, estado_desc, proceso_cod, proceso_nom,
                   tipo_documento, contenido_texto, texto_length, fecha_publicacion,
                   elaborador, revisor_proceso, revisor_calidad, aprobador_gerencia
            FROM procedimientos
            WHERE texto_length > 100
            ORDER BY codigo
        """).fetchall()

        if not rows:
            raise RuntimeError("No hay documentos. Ejecuta build_document_index.py primero.")

        self.docs = {}
        self.codigos = []
        for r in rows:
            codigo = r[0]
            self.docs[codigo] = {
                "codigo": codigo,
                "nombre": r[1],
                "estado": r[2],
                "estado_desc": r[3],
                "proceso_cod": r[4],
                "proceso_nom": r[5],
                "tipo_documento": r[6],
                "texto": r[7] or "",
                "texto_length": r[8],
                "fecha_publicacion": r[9],
                "elaborador": r[10],
                "revisor_proceso": r[11],
                "revisor_calidad": r[12],
                "aprobador_gerencia": r[13],
            }
            self.codigos.append(codigo)

        print(f"  [GraphRAG] Documentos cargados: {len(self.codigos)}")

    def _load_embeddings(self):
        """Carga embeddings desde ChromaDB (primario) y construye índice FAISS."""
        import chromadb

        # ChromaDB
        chroma_client = chromadb.PersistentClient(path=str(CHROMA_PATH))
        self.collection = chroma_client.get_or_create_collection("procedimientos")

        # Cargar todos los embeddings desde ChromaDB
        results = self.collection.get(include=["embeddings", "metadatas", "documents"])

        if not results["ids"]:
            # Fallback: cargar desde SQLite si ChromaDB está vacío
            print(f"  [GraphRAG] ChromaDB vacío, cargando desde SQLite...")
            rows = self.conn.execute("""
                SELECT e.codigo, e.embedding, p.nombre, p.proceso_nom,
                       p.tipo_documento, p.estado, p.estado_desc, p.contenido_texto
                FROM embeddings e
                JOIN procedimientos p ON e.codigo = p.codigo
            """).fetchall()
            if not rows:
                raise RuntimeError("No hay embeddings. Ejecuta generate_embeddings.py primero.")

            self.embeddings = {}
            self.embedding_matrix = []
            self.embedding_codigos = []
            for r in rows:
                codigo = r[0]
                if codigo in self.docs:
                    emb = pickle.loads(r[1])
                    self.embeddings[codigo] = np.array(emb)
                    self.embedding_matrix.append(emb)
                    self.embedding_codigos.append(codigo)
        else:
            self.embeddings = {}
            self.embedding_matrix = []
            self.embedding_codigos = []
            for i, codigo in enumerate(results["ids"]):
                if codigo in self.docs:
                    emb = np.array(results["embeddings"][i])
                    self.embeddings[codigo] = emb
                    self.embedding_matrix.append(emb)
                    self.embedding_codigos.append(codigo)

        self.embedding_matrix = np.array(self.embedding_matrix) if self.embedding_matrix else None

        # Construir índice FAISS para búsqueda ultra rápida
        if self.embedding_matrix is not None:
            self.faiss_index = faiss.IndexFlatIP(EMBED_DIM)
            vecs = np.array([self._normalize_dim(v) for v in self.embedding_matrix])
            faiss.normalize_L2(vecs)
            self.faiss_index.add(vecs)
        else:
            self.faiss_index = None

        print(f"  [GraphRAG] Embeddings cargados: {len(self.embedding_codigos)}")
        print(f"  [GraphRAG] Índice FAISS: {self.faiss_index.ntotal if self.faiss_index else 0} vectores")

    def _build_tfidf(self):
        """Construye índice léxico. Usa BM25 si disponible, sino TF-IDF."""
        if _HAS_BM25:
            print(f"  [GraphRAG] Construyendo índice BM25...")
            self._build_bm25()
        else:
            print(f"  [GraphRAG] Construyendo índice TF-IDF (BM25 no disponible)...")
            self._build_tfidf_fallback()

    def _build_bm25(self):
        """Construye índice BM25 sobre el texto de los documentos."""
        # Stop words en español
        stop_words = {
            "el", "la", "los", "las", "de", "del", "y", "o", "a", "en",
            "que", "es", "se", "para", "con", "por", "un", "una", "su",
            "al", "lo", "como", "mas", "menos", "si", "no", "este", "esta",
            "the", "of", "and", "to", "in", "for", "is", "are", "with",
            "this", "that", "it", "as", "be", "or", "on", "at", "by",
            "an", "from", "was", "were", "has", "have", "had", "not",
            "but", "what", "which", "when", "where", "who", "how",
            "todo", "toda", "todos", "todas", "cada", "alguna", "alguno",
            "entre", "sobre", "hasta", "desde", "sin", "tras", "durante",
            "mediante", "segun", "contra", "ante", "bajo", "cab", "cabe",
        }

        def tokenize(text):
            tokens = re.findall(r"[a-záéíóúñ]{3,}", text.lower())
            return [t for t in tokens if t not in stop_words]

        textos = [self.docs[c]["texto"] for c in self.embedding_codigos]
        self.bm25_corpus = [tokenize(t) for t in textos]
        self.bm25 = BM25Okapi(self.bm25_corpus)
        self.bm25_tokenize = tokenize
        print(f"  [GraphRAG] BM25: {len(self.bm25_corpus)} docs indexados")

    def _build_tfidf_fallback(self):
        """Fallback a TF-IDF si BM25 no esta disponible."""
        stop_words = [
            "el", "la", "los", "las", "de", "del", "y", "o", "a", "en",
            "que", "es", "se", "para", "con", "por", "un", "una", "su",
            "al", "lo", "como", "mas", "menos", "si", "no", "este", "esta",
            "the", "of", "and", "to", "in", "for", "is", "are", "with",
            "this", "that", "it", "as", "be", "or", "on", "at", "by",
            "an", "from", "was", "were", "has", "have", "had", "not",
            "but", "what", "which", "when", "where", "who", "how",
            "todo", "toda", "todos", "todas", "cada", "alguna", "alguno",
            "entre", "sobre", "hasta", "desde", "sin", "tras", "durante",
            "mediante", "segun", "contra", "ante", "bajo", "cab", "cabe",
        ]

        textos = [self.docs[c]["texto"] for c in self.embedding_codigos]

        self.tfidf_vectorizer = TfidfVectorizer(
            max_features=8000,
            stop_words=stop_words,
            token_pattern=r"[a-záéíóúñ]{3,}",
            max_df=0.85,
            min_df=2,
            ngram_range=(1, 2),
            sublinear_tf=True,
        )
        self.tfidf_matrix = self.tfidf_vectorizer.fit_transform(textos)
        self.tfidf_feature_names = self.tfidf_vectorizer.get_feature_names_out()
        print(f"  [GraphRAG] TF-IDF: {self.tfidf_matrix.shape[0]} docs × {self.tfidf_matrix.shape[1]} términos")

    # ──────────────────────────────────────────────
    # Construcción del grafo de conocimiento
    # ──────────────────────────────────────────────

    def _build_graph(self):
        """Construye el grafo de conocimiento:
        - Nodos: documentos, procesos, tipos, formatos, normas, temas
        - Aristas: relaciones entre entidades
        """
        print(f"  [GraphRAG] Construyendo grafo de conocimiento...")
        start = time.time()

        self.graph = nx.Graph()

        # 1. Nodos de documentos
        for codigo in self.embedding_codigos:
            doc = self.docs[codigo]
            self.graph.add_node(
                f"doc:{codigo}",
                type="documento",
                codigo=codigo,
                nombre=doc["nombre"],
                estado=doc["estado_desc"],
            )

        # 2. Nodos de procesos + aristas doc→proceso
        for codigo in self.embedding_codigos:
            doc = self.docs[codigo]
            if doc["proceso_cod"]:
                proc_node = f"proceso:{doc['proceso_cod']}"
                self.graph.add_node(
                    proc_node,
                    type="proceso",
                    nombre=doc["proceso_nom"],
                    codigo=doc["proceso_cod"],
                )
                self.graph.add_edge(f"doc:{codigo}", proc_node, relation="pertenece_a")

        # 3. Nodos de tipos de documento + aristas
        for codigo in self.embedding_codigos:
            doc = self.docs[codigo]
            if doc["tipo_documento"]:
                tipo_node = f"tipo:{doc['tipo_documento']}"
                self.graph.add_node(tipo_node, type="tipo_documento", nombre=doc["tipo_documento"])
                self.graph.add_edge(f"doc:{codigo}", tipo_node, relation="es_de_tipo")

        # 4. Nodos de usuarios + aristas
        for codigo in self.embedding_codigos:
            doc = self.docs[codigo]
            for role, user in [
                ("elaborador", doc["elaborador"]),
                ("revisor_proceso", doc["revisor_proceso"]),
                ("revisor_calidad", doc["revisor_calidad"]),
                ("aprobador_gerencia", doc["aprobador_gerencia"]),
            ]:
                if user and user.strip():
                    user_node = f"user:{user.strip()}"
                    self.graph.add_node(user_node, type="usuario", nombre=user.strip())
                    self.graph.add_edge(f"doc:{codigo}", user_node, relation=role)

        # 5. Aristas documento→documento por proceso compartido
        # (conexión entre docs del mismo proceso)
        proceso_docs = defaultdict(list)
        for codigo in self.embedding_codigos:
            proc = self.docs[codigo]["proceso_cod"]
            if proc:
                proceso_docs[proc].append(codigo)

        for proc, docs in proceso_docs.items():
            # Conectar documentos del mismo proceso (limitar para evitar explosión)
            if len(docs) <= 20:
                for i in range(len(docs)):
                    for j in range(i + 1, len(docs)):
                        self.graph.add_edge(
                            f"doc:{docs[i]}", f"doc:{docs[j]}",
                            relation="mismo_proceso",
                            proceso=proc,
                        )

        # 6. Nodos de temas (clusters) desde SQLite
        try:
            tema_rows = self.conn.execute(
                "SELECT tema_id, nombre, palabras_clave FROM temas"
            ).fetchall()
            for tema_id, nombre, palabras in tema_rows:
                tema_node = f"tema:{tema_id}"
                self.graph.add_node(
                    tema_node,
                    type="tema",
                    nombre=nombre,
                    palabras_clave=json.loads(palabras) if palabras else [],
                )

                # Conectar documentos a su tema
                doc_rows = self.conn.execute(
                    "SELECT codigo FROM documento_tema WHERE tema_id = ?", (tema_id,)
                ).fetchall()
                for (doc_codigo,) in doc_rows:
                    if f"doc:{doc_codigo}" in self.graph:
                        self.graph.add_edge(tema_node, f"doc:{doc_codigo}", relation="pertenece_a_tema")
        except sqlite3.OperationalError:
            pass  # tabla temas no existe aún

        elapsed = time.time() - start
        n_nodes = self.graph.number_of_nodes()
        n_edges = self.graph.number_of_edges()
        print(f"  [GraphRAG] Grafo: {n_nodes} nodos, {n_edges} aristas ({elapsed:.1f}s)")

        # Estadísticas por tipo
        tipos = defaultdict(int)
        for n in self.graph.nodes:
            tipos[self.graph.nodes[n].get("type", "?")] += 1
        for t, c in sorted(tipos.items()):
            print(f"           {t}: {c}")

    # ──────────────────────────────────────────────
    # Recuperación híbrida
    # ──────────────────────────────────────────────

    def _embed_query(self, query: str) -> np.ndarray:
        """Genera embedding de 1024 dims (compatible con FAISS) con cache RAM + SQLite."""
        import hashlib, pickle
        q_norm = query[:8000].lower().strip()
        # Usar Mistral por defecto para embeddings, ya que FAISS/Chroma se generaron asi
        prefer_embed = "mistral"
        cache_key = hashlib.sha256((q_norm + "|" + prefer_embed).encode("utf-8")).hexdigest()[:32]

        # 1. Cache en RAM
        ram_key = q_norm[:200]
        cached_ram = self._query_emb_cache.get(ram_key)
        if cached_ram is not None and len(cached_ram) == EMBED_DIM:
            return np.array(cached_ram)

        # 2. Cache persistente en SQLite
        try:
            row = self.conn.execute(
                "SELECT embedding FROM cache_embeddings WHERE query_hash = ?",
                (cache_key,)
            ).fetchone()
            if row:
                emb = pickle.loads(row[0])
                if len(emb) == EMBED_DIM:
                    self._query_emb_cache[ram_key] = emb
                    return np.array(emb)
                else:
                    print(f"  [GraphRAG] Cache embedding descartado: dimension {len(emb)} != {EMBED_DIM}")
        except Exception as e:
            print(f"  [GraphRAG] Error leyendo cache de embeddings: {e}")

        # 3. Generar embedding via LLM (Mistral primero, fallback OpenAI a 1024 dims)
        try:
            emb, provider = self.llm.embeddings(q_norm, prefer=prefer_embed)
            if provider != prefer_embed:
                print(f"  [GraphRAG] Embedding query via {provider} fallback")
            vec = self._normalize_dim(emb)
            if len(np.asarray(emb).reshape(-1)) != EMBED_DIM:
                print(f"  [GraphRAG] Embedding dimension {len(np.asarray(emb).reshape(-1))} ajustada a {EMBED_DIM}")

            # Guardar en cache RAM
            if len(self._query_emb_cache) < 500:
                self._query_emb_cache[ram_key] = vec

            # Guardar en cache persistente
            try:
                self.conn.execute("""
                    INSERT OR REPLACE INTO cache_embeddings (query_hash, query_text, embedding, modelo, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (cache_key, q_norm, pickle.dumps(vec.astype(np.float32)), prefer_embed, datetime.now().isoformat()))
                self.conn.commit()
            except Exception as e:
                print(f"  [GraphRAG] Error guardando cache de embeddings: {e}")

            return vec
        except Exception as e:
            raise RuntimeError(f"No se pudo generar embedding: {e}")

    def _migrar_faq_precargadas(self):
        """Agrega columnas de vigencia y feedback si la tabla fue creada con schema antiguo."""
        try:
            cols = {c[1] for c in self.conn.execute("PRAGMA table_info(faq_precargadas)").fetchall()}
            nuevas = {
                "documentos_citados": "TEXT",
                "estados_documentos": "TEXT",
                "tipo_contenido": "TEXT",
                "vigente_hasta": "TEXT",
                "feedback_positivo": "INTEGER DEFAULT 0",
                "feedback_negativo": "INTEGER DEFAULT 0",
                "activa": "INTEGER DEFAULT 1",
            }
            for col, tipo in nuevas.items():
                if col not in cols:
                    self.conn.execute(f"ALTER TABLE faq_precargadas ADD COLUMN {col} {tipo}")
            self.conn.commit()
        except Exception as e:
            print(f"  [GraphRAG] Error migrando faq_precargadas: {e}")

    def _tipo_contenido_faq(self, pregunta: str) -> str:
        """Clasifica una pregunta segun riesgo de obsolescencia."""
        q = pregunta.lower()
        if any(x in q for x in ["que es", "qué es", "definicion", "definición", "como se define", "cómo se define", "significado"]):
            return "conceptual"
        if any(x in q for x in ["que documento", "qué documento", "cual documento", "cuál documento", "aplica para", "aplica a", "donde encuentro", "dónde encuentro", "vigente"]):
            return "documental"
        return "operativo"

    def _dias_vigencia_faq(self, tipo: str) -> int:
        if tipo == "conceptual":
            return 90
        if tipo == "documental":
            return 7
        return 30

    def _extraer_documentos_resultados(self, resultados: list[dict]) -> tuple[list[str], dict[str, str]]:
        """Extrae codigos y estados de una lista de resultados de retrieval."""
        codigos = []
        estados = {}
        for r in resultados:
            codigo = r.get("codigo")
            if codigo and codigo not in codigos:
                codigos.append(codigo)
                estados[codigo] = r.get("estado", "")
        return codigos, estados

    def _faq_es_vigente(self, faq: dict) -> tuple[bool, str]:
        """Revalida una FAQ contra documentos citados y vigencia."""
        import json
        from datetime import datetime, timedelta
        now = datetime.now()

        # 1. TTL por tipo de contenido
        vigente_hasta_str = faq.get("vigente_hasta")
        if vigente_hasta_str:
            try:
                vigente_hasta = datetime.fromisoformat(vigente_hasta_str)
                if now > vigente_hasta:
                    return False, "expirada"
            except Exception:
                pass

        # 2. Documentos citados siguen vigentes
        doc_str = faq.get("documentos_citados")
        est_str = faq.get("estados_documentos")
        if not doc_str:
            # Sin documentos citados: asumir conceptual sin riesgo documental
            return True, "ok"

        try:
            codigos = json.loads(doc_str)
            estados_guardados = json.loads(est_str) if est_str else {}
        except Exception:
            return False, "metadata_corrupta"

        if not codigos:
            return True, "ok"

        # Consultar estados actuales en SQLite
        try:
            placeholders = ",".join("?" * len(codigos))
            rows = self.conn.execute(
                f"SELECT codigo, estado FROM procedimientos WHERE codigo IN ({placeholders})",
                tuple(codigos)
            ).fetchall()
            estados_actuales = {r[0]: (r[1] or "") for r in rows}
        except Exception:
            return False, "error_db"

        for codigo in codigos:
            actual = estados_actuales.get(codigo, "")
            guardado = estados_guardados.get(codigo, "")
            if actual != guardado:
                return False, f"cambio_estado:{codigo}"

        return True, "ok"

    def _doc_feedback_boosts(self, codigos: set[str]) -> dict[str, float]:
        """Carga boosts de feedback para un conjunto de codigos de documentos."""
        try:
            if not codigos:
                return {}
            placeholders = ",".join("?" * len(codigos))
            rows = self.conn.execute(
                f"SELECT codigo, score_boost FROM doc_feedback_stats WHERE codigo IN ({placeholders})",
                tuple(codigos)
            ).fetchall()
            return {r[0]: float(r[1] or 0.0) for r in rows}
        except Exception:
            return {}

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Calcula similitud coseno entre dos vectores."""
        if a.shape != b.shape:
            return 0.0
        a = a / (np.linalg.norm(a) + 1e-9)
        b = b / (np.linalg.norm(b) + 1e-9)
        return float(np.dot(a, b))

    def _buscar_cache_semantico(self, query: str, threshold: float = 0.92) -> dict | None:
        """Busca respuestas similares en cache usando embeddings reales."""
        try:
            q_emb = self._embed_query(query)
            import pickle
            rows = self.conn.execute("""
                SELECT query_hash, query_text, embedding, respuesta, modelo, created_at, hits
                FROM cache_semantico
            """).fetchall()
            best = None
            best_score = 0.0
            for row in rows:
                emb = pickle.loads(row[2])
                score = self._cosine_similarity(q_emb, np.array(emb))
                if score > best_score:
                    best_score = score
                    best = row
            if best and best_score >= threshold:
                self.conn.execute(
                    "UPDATE cache_semantico SET hits = hits + 1 WHERE query_hash = ?",
                    (best[0],)
                )
                self.conn.commit()
                return {
                    "respuesta": best[3],
                    "modelo": best[4],
                    "created_at": best[5],
                    "from_cache": True,
                    "match_type": "semantic",
                    "similarity": round(best_score, 3),
                }
        except Exception as e:
            print(f"  [GraphRAG] Error cache semantico: {e}")
        return None

    def _guardar_cache_semantico(self, query: str, respuesta: str, modelo: str):
        """Guarda una respuesta en cache semantico con embedding."""
        try:
            import hashlib, pickle
            qhash = hashlib.sha256(query.encode("utf-8")).hexdigest()[:32]
            q_emb = self._embed_query(query)
            self.conn.execute("""
                INSERT OR REPLACE INTO cache_semantico
                (query_hash, query_text, embedding, respuesta, modelo, created_at, hits)
                VALUES (?, ?, ?, ?, ?, ?, 0)
            """, (
                qhash, query, pickle.dumps(q_emb.astype(np.float32)),
                respuesta, modelo, datetime.now().isoformat()
            ))
            self.conn.commit()
            print(f"  [GraphRAG] Respuesta guardada en cache semantico")
        except Exception as e:
            print(f"  [GraphRAG] Error guardando cache semantico: {e}")

    def buscar_faq_precargada(self, query: str, threshold: float = 0.93) -> dict | None:
        """Busca una respuesta precargada activa y vigente para la pregunta.
        Orden: match exacto por hash, coincidencia de keywords, similitud coseno.
        Revalida vigencia antes de devolver la FAQ.
        """
        try:
            import hashlib, pickle, json
            q_norm = re.sub(r"\s+", " ", query.strip().lower())
            qhash = hashlib.sha256(q_norm.encode("utf-8")).hexdigest()[:32]

            columnas = """
                id, pregunta, respuesta, fuente, keywords,
                documentos_citados, estados_documentos, tipo_contenido, vigente_hasta,
                feedback_positivo, feedback_negativo, activa
            """

            def _hacer_dict(row, match_type):
                return {
                    "id": row[0],
                    "pregunta": row[1],
                    "respuesta": row[2],
                    "fuente": row[3],
                    "keywords": row[4],
                    "documentos_citados": row[5],
                    "estados_documentos": row[6],
                    "tipo_contenido": row[7],
                    "vigente_hasta": row[8],
                    "feedback_positivo": row[9] or 0,
                    "feedback_negativo": row[10] or 0,
                    "activa": row[11] if row[11] is not None else 1,
                    "match": match_type,
                }

            # 1. Match exacto por hash (solo FAQs activas)
            row = self.conn.execute(
                f"SELECT {columnas} FROM faq_precargadas WHERE pregunta_hash = ? AND activa = 1",
                (qhash,)
            ).fetchone()
            if row:
                faq = _hacer_dict(row, "exact")
                vigente, razon = self._faq_es_vigente(faq)
                if vigente:
                    self.conn.execute("UPDATE faq_precargadas SET uso_count = uso_count + 1, updated_at = ? WHERE id = ?",
                                      (datetime.now().isoformat(), faq["id"]))
                    self.conn.commit()
                    print(f"  [GraphRAG] FAQ exact match: {faq['pregunta']}")
                    return faq
                else:
                    print(f"  [GraphRAG] FAQ exact match descartada: {razon}")
                    return None

            # 2. Coincidencia de keywords (rapido, sin embeddings, solo activas)
            query_words = set(re.findall(r"\b\w+\b", q_norm))
            rows = self.conn.execute(f"SELECT {columnas} FROM faq_precargadas WHERE activa = 1").fetchall()
            best_keyword = None
            best_kw_score = 0.0
            for row in rows:
                kw_set = set((row[4] or "").lower().split(",")) if row[4] else set()
                if not kw_set:
                    continue
                overlap = len(query_words & kw_set)
                score = overlap / max(len(query_words), len(kw_set), 1)
                if score > best_kw_score and score >= 0.6:
                    best_kw_score = score
                    best_keyword = row
            if best_keyword:
                faq = _hacer_dict(best_keyword, "keyword")
                vigente, razon = self._faq_es_vigente(faq)
                if vigente:
                    self.conn.execute("UPDATE faq_precargadas SET uso_count = uso_count + 1, updated_at = ? WHERE id = ?",
                                      (datetime.now().isoformat(), faq["id"]))
                    self.conn.commit()
                    print(f"  [GraphRAG] FAQ keyword match: {faq['pregunta']} (score={best_kw_score:.2f})")
                    return faq
                else:
                    print(f"  [GraphRAG] FAQ keyword match descartada: {razon}")
                    return None

            # 3. Similitud coseno con embeddings (solo FAQs activas con embedding)
            faq_rows = self.conn.execute(f"SELECT {columnas} FROM faq_precargadas WHERE pregunta_embedding IS NOT NULL AND activa = 1").fetchall()
            if faq_rows:
                q_emb = self._embed_query(query)
                q_emb_norm = q_emb / (np.linalg.norm(q_emb) + 1e-9)
                best = None
                best_score = -1
                for row in faq_rows:
                    try:
                        f_emb = pickle.loads(row[4])
                        if isinstance(f_emb, list):
                            f_emb = np.array(f_emb, dtype=np.float32)
                        f_emb_norm = f_emb / (np.linalg.norm(f_emb) + 1e-9)
                        sim = float(np.dot(q_emb_norm, f_emb_norm))
                        if sim > best_score and sim >= threshold:
                            best_score = sim
                            best = row
                    except Exception:
                        continue
                if best:
                    faq = _hacer_dict(best, "semantic")
                    vigente, razon = self._faq_es_vigente(faq)
                    if vigente:
                        self.conn.execute("UPDATE faq_precargadas SET uso_count = uso_count + 1, updated_at = ? WHERE id = ?",
                                          (datetime.now().isoformat(), faq["id"]))
                        self.conn.commit()
                        print(f"  [GraphRAG] FAQ semantic match: {faq['pregunta']} (sim={best_score:.2f})")
                        return faq
                    else:
                        print(f"  [GraphRAG] FAQ semantic match descartada: {razon}")
                        return None

            return None
        except Exception as e:
            print(f"  [GraphRAG] Error buscando FAQ: {e}")
            return None

    def _actualizar_faq_si_existe(self, pregunta: str, respuesta: str, resultados: list[dict]) -> bool:
        """Si ya existe una FAQ para esta pregunta exacta, la actualiza con la respuesta vigente."""
        try:
            import hashlib
            q_norm = re.sub(r"\s+", " ", pregunta.strip().lower())
            qhash = hashlib.sha256(q_norm.encode("utf-8")).hexdigest()[:32]
            existe = self.conn.execute("SELECT 1 FROM faq_precargadas WHERE pregunta_hash = ?", (qhash,)).fetchone()
            if not existe:
                return False
            doc_list, est_dict = self._extraer_documentos_resultados(resultados)
            tipo = self._tipo_contenido_faq(pregunta)
            keywords = ", ".join(re.findall(r"\b\w+\b", q_norm)[:10])
            return self.guardar_faq_precargada(
                pregunta=pregunta,
                respuesta=respuesta,
                keywords=keywords,
                categoria="auto_actualizada",
                fuente="chat_actualizacion",
                documentos_citados=doc_list,
                estados_documentos=est_dict,
                tipo_contenido=tipo,
            )
        except Exception as e:
            print(f"  [GraphRAG] Error actualizando FAQ existente: {e}")
            return False

    def guardar_faq_precargada(self, pregunta: str, respuesta: str,
                                keywords: str = "", categoria: str = "",
                                proceso: str = "", fuente: str = "",
                                documentos_citados: list[str] | None = None,
                                estados_documentos: dict[str, str] | None = None,
                                tipo_contenido: str = "") -> bool:
        """Guarda o actualiza una pregunta/respuesta precargada con metadatos de vigencia."""
        try:
            import hashlib, pickle, json
            from datetime import datetime, timedelta
            q_norm = re.sub(r"\s+", " ", pregunta.strip().lower())
            qhash = hashlib.sha256(q_norm.encode("utf-8")).hexdigest()[:32]
            now = datetime.now().isoformat()

            tipo = tipo_contenido or self._tipo_contenido_faq(pregunta)
            dias = self._dias_vigencia_faq(tipo)
            vigente_hasta = (datetime.now() + timedelta(days=dias)).isoformat()

            doc_list = documentos_citados or []
            est_dict = estados_documentos or {}

            try:
                q_emb = self._embed_query(pregunta)
                emb_blob = pickle.dumps(q_emb.astype(np.float32))
            except Exception:
                emb_blob = None

            self.conn.execute("""
                INSERT OR REPLACE INTO faq_precargadas
                (pregunta, pregunta_hash, pregunta_embedding, respuesta, keywords, categoria, proceso, fuente,
                 created_at, updated_at, documentos_citados, estados_documentos, tipo_contenido, vigente_hasta,
                 feedback_positivo, feedback_negativo, activa)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?,
                        COALESCE((SELECT created_at FROM faq_precargadas WHERE pregunta_hash = ?), ?), ?,
                        ?, ?, ?, ?,
                        COALESCE((SELECT feedback_positivo FROM faq_precargadas WHERE pregunta_hash = ?), 0),
                        COALESCE((SELECT feedback_negativo FROM faq_precargadas WHERE pregunta_hash = ?), 0),
                        COALESCE((SELECT activa FROM faq_precargadas WHERE pregunta_hash = ?), 1))
            """, (
                q_norm, qhash, emb_blob, respuesta, keywords, categoria, proceso, fuente,
                qhash, now, now,
                json.dumps(doc_list), json.dumps(est_dict), tipo, vigente_hasta,
                qhash, qhash, qhash
            ))
            self.conn.commit()
            print(f"  [GraphRAG] FAQ guardada ({tipo}, vigencia {dias}d): {pregunta[:60]}")
            return True
        except Exception as e:
            print(f"  [GraphRAG] Error guardando FAQ: {e}")
            return False

    def reparar_faq_existentes(self) -> dict:
        """Recategoriza y completa metadatos de vigencia de FAQs existentes."""
        try:
            import json, re
            from datetime import datetime, timedelta

            rows = self.conn.execute("""
                SELECT id, pregunta, respuesta, created_at, updated_at
                FROM faq_precargadas
            """).fetchall()

            if not rows:
                return {"total": 0, "reparadas": 0}

            # Cargar codigos vigentes para buscar citas en respuestas
            doc_rows = self.conn.execute("SELECT codigo, estado FROM procedimientos").fetchall()
            codigos = [r[0] for r in doc_rows if r[0]]
            estado_actual = {r[0]: (r[1] or "") for r in doc_rows if r[0]}

            reparadas = 0
            for row in rows:
                try:
                    faq_id, pregunta, respuesta, created_at, updated_at = row
                    tipo = self._tipo_contenido_faq(pregunta)
                    dias = self._dias_vigencia_faq(tipo)

                    # Fecha base: created_at o updated_at o ahora
                    base_str = created_at or updated_at or datetime.now().isoformat()
                    try:
                        base_dt = datetime.fromisoformat(base_str)
                    except Exception:
                        base_dt = datetime.now()
                    vigente_hasta = (base_dt + timedelta(days=dias)).isoformat()

                    # Extraer documentos citados en la respuesta
                    doc_list = []
                    estados = {}
                    for codigo in codigos:
                        if re.search(r'\b' + re.escape(codigo) + r'\b', respuesta or '', re.IGNORECASE):
                            doc_list.append(codigo)
                            estados[codigo] = estado_actual.get(codigo, "")

                    self.conn.execute("""
                        UPDATE faq_precargadas
                        SET tipo_contenido = ?,
                            vigente_hasta = ?,
                            documentos_citados = ?,
                            estados_documentos = ?,
                            updated_at = ?
                        WHERE id = ?
                    """, (
                        tipo, vigente_hasta,
                        json.dumps(doc_list), json.dumps(estados),
                        datetime.now().isoformat(), faq_id
                    ))
                    reparadas += 1
                except Exception as e:
                    print(f"  [GraphRAG] Error reparando FAQ {row[0]}: {e}")
                    continue

            self.conn.commit()
            print(f"  [GraphRAG] FAQs reparadas: {reparadas}/{len(rows)}")
            return {"total": len(rows), "reparadas": reparadas}
        except Exception as e:
            print(f"  [GraphRAG] Error reparando FAQs: {e}")
            return {"total": 0, "reparadas": 0}

    def listar_faq_precargadas(self, limit: int = 100) -> list[dict]:
        """Lista FAQs precargadas ordenadas por uso."""
        try:
            rows = self.conn.execute("""
                SELECT id, pregunta, respuesta, keywords, categoria, proceso, fuente, uso_count, created_at
                FROM faq_precargadas
                ORDER BY uso_count DESC, updated_at DESC
                LIMIT ?
            """, (limit,)).fetchall()
            return [
                {
                    "id": r[0], "pregunta": r[1], "respuesta": r[2],
                    "keywords": r[3], "categoria": r[4], "proceso": r[5],
                    "fuente": r[6], "uso_count": r[7], "created_at": r[8]
                }
                for r in rows
            ]
        except Exception as e:
            print(f"  [GraphRAG] Error listando FAQ: {e}")
            return []

    def precargar_faq_desde_uso(self, min_count: int = 2, top_n: int = 50) -> dict:
        """Genera respuestas precargadas para las preguntas mas frecuentes del historial de uso."""
        try:
            # Preguntas mas frecuentes
            rows = self.conn.execute("""
                SELECT question, COUNT(*) as n
                FROM usage_stats
                WHERE question IS NOT NULL AND length(question) > 5
                GROUP BY question
                HAVING n >= ?
                ORDER BY n DESC
                LIMIT ?
            """, (min_count, top_n)).fetchall()

            generadas = 0
            existentes = 0
            for question, count in rows:
                # Si ya existe FAQ, saltar
                exists = self.conn.execute("SELECT 1 FROM faq_precargadas WHERE pregunta = ?",
                                           (question.lower().strip(),)).fetchone()
                if exists:
                    existentes += 1
                    continue

                # Generar respuesta con ask() en modo rapido
                try:
                    respuesta, resultados = self.ask(question, modo_rapido=True)
                    if respuesta and len(respuesta) > 20:
                        doc_list, est_dict = self._extraer_documentos_resultados(resultados)
                        self.guardar_faq_precargada(
                            pregunta=question,
                            respuesta=respuesta,
                            keywords=", ".join(re.findall(r"\b\w+\b", question.lower())[:10]),
                            categoria="auto_generada",
                            fuente="usage_stats",
                            documentos_citados=doc_list,
                            estados_documentos=est_dict,
                            tipo_contenido=self._tipo_contenido_faq(question)
                        )
                        generadas += 1
                except Exception as e:
                    print(f"  [GraphRAG] Error generando FAQ para '{question[:40]}': {e}")
                    continue

            return {"total_preguntas": len(rows), "generadas": generadas, "existentes_skipped": existentes}
        except Exception as e:
            print(f"  [GraphRAG] Error precargando FAQ desde uso: {e}")
            return {"total_preguntas": 0, "generadas": 0, "existentes_skipped": 0}

    def registrar_uso(self, username: str, role: str, area: str, question: str,
                      resultados: list[dict], provider: str, cached: bool = False):
        """Registra uso del agente para indicadores por usuario/area/proceso."""
        try:
            # Proceso principal: el mas frecuente entre los documentos recuperados
            procesos = [r.get("proceso_cod", "") for r in resultados if r.get("proceso_cod")]
            proceso_principal = max(set(procesos), key=procesos.count) if procesos else ""
            self.conn.execute("""
                INSERT INTO usage_stats
                (session_id, username, role, area, timestamp, question, proceso_principal, docs_count, provider, cached)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                getattr(self, '_current_session_id', 'default'),
                username, role, area, datetime.now().isoformat(),
                question, proceso_principal, len(resultados), provider, int(cached)
            ))
            self.conn.commit()
        except Exception as e:
            print(f"  [GraphRAG] Error registrando uso: {e}")

    def get_usage_stats(self) -> dict:
        """Devuelve indicadores de uso por usuario, area y proceso."""
        try:
            por_usuario = self.conn.execute("""
                SELECT username, COUNT(*) as n, SUM(CASE WHEN cached=1 THEN 1 ELSE 0 END) as cached
                FROM usage_stats
                GROUP BY username
                ORDER BY n DESC
                LIMIT 20
            """).fetchall()

            por_proceso = self.conn.execute("""
                SELECT proceso_principal, COUNT(*) as n
                FROM usage_stats
                WHERE proceso_principal <> ''
                GROUP BY proceso_principal
                ORDER BY n DESC
                LIMIT 20
            """).fetchall()

            por_area = self.conn.execute("""
                SELECT area, COUNT(*) as n
                FROM usage_stats
                WHERE area <> ''
                GROUP BY area
                ORDER BY n DESC
                LIMIT 20
            """).fetchall()

            por_rol = self.conn.execute("""
                SELECT role, COUNT(*) as n
                FROM usage_stats
                GROUP BY role
                ORDER BY n DESC
            """).fetchall()

            total = self.conn.execute("SELECT COUNT(*) FROM usage_stats").fetchone()[0]

            return {
                "total": total,
                "por_usuario": [{"Usuario": u[0], "Consultas": u[1], "Cache": u[2]} for u in por_usuario],
                "por_proceso": [{"Proceso": p[0], "Consultas": p[1]} for p in por_proceso],
                "por_area": [{"Area": a[0], "Consultas": a[1]} for a in por_area],
                "por_rol": [{"Rol": r[0], "Consultas": r[1]} for r in por_rol],
            }
        except Exception as e:
            print(f"  [GraphRAG] Error obteniendo uso: {e}")
            return {"total": 0, "por_usuario": [], "por_proceso": [], "por_area": [], "por_rol": []}

    def documentos_sin_embedding(self) -> list[dict]:
        """Lista documentos con texto pero sin embedding en SQLite."""
        try:
            rows = self.conn.execute("""
                SELECT p.codigo, p.nombre, p.contenido_texto, p.texto_length
                FROM procedimientos p
                LEFT JOIN embeddings e ON p.codigo = e.codigo
                WHERE p.texto_length > 100
                  AND (e.codigo IS NULL OR e.embedding IS NULL)
                  AND p.estado <> 'O'
            """).fetchall()
            return [
                {"codigo": r[0], "nombre": r[1], "texto": r[2], "texto_length": r[3]}
                for r in rows
            ]
        except Exception as e:
            print(f"  [GraphRAG] Error listando docs sin embedding: {e}")
            return []

    def reintentar_embeddings_fallidos(self, batch_size: int = 10) -> dict:
        """Genera embeddings solo para documentos fallidos y sincroniza indices."""
        fallidos = self.documentos_sin_embedding()
        if not fallidos:
            return {"status": "ok", "total": 0, "generados": 0, "error": None}

        generados = 0
        errores = []
        nuevos_embeddings = {}

        for i in range(0, len(fallidos), batch_size):
            batch = fallidos[i:i + batch_size]
            textos = [d["texto"][:4000] for d in batch]

            for j, doc in enumerate(batch):
                try:
                    emb, provider = self.llm.embeddings(textos[j])
                    emb = np.array(emb, dtype=np.float32)
                    if emb.shape[0] != EMBED_DIM:
                        # Ajustar dimension si es necesario
                        if emb.shape[0] > EMBED_DIM:
                            emb = emb[:EMBED_DIM]
                        else:
                            pad = np.zeros(EMBED_DIM - emb.shape[0], dtype=np.float32)
                            emb = np.concatenate([emb, pad])

                    # Guardar en SQLite
                    self.conn.execute("""
                        INSERT OR REPLACE INTO embeddings (codigo, embedding, modelo, creado)
                        VALUES (?, ?, ?, ?)
                    """, (doc["codigo"], pickle.dumps(emb.tolist()), provider, datetime.now().isoformat()))
                    self.conn.commit()

                    nuevos_embeddings[doc["codigo"]] = emb
                    generados += 1
                    print(f"  [GraphRAG] Embedding re-generado: {doc['codigo']} ({provider})")
                except Exception as e:
                    errores.append(f"{doc['codigo']}: {e}")
                    print(f"  [GraphRAG] Error re-generando {doc['codigo']}: {e}")

        # Actualizar FAISS si esta cargado
        if nuevos_embeddings and self.faiss_index is not None:
            for codigo, emb in nuevos_embeddings.items():
                faiss.normalize_L2(emb.reshape(1, -1))
                self.faiss_index.add(emb.reshape(1, -1))
                if codigo not in self.embedding_codigos:
                    self.embedding_codigos.append(codigo)
            try:
                faiss.write_index(self.faiss_index, str(FAISS_PATH))
            except Exception as e:
                print(f"  [GraphRAG] Error guardando FAISS: {e}")

        return {
            "status": "ok" if generados > 0 else "error",
            "total": len(fallidos),
            "generados": generados,
            "errores": errores,
        }

    def _normalize_dim(self, vec: np.ndarray, target: int = EMBED_DIM) -> np.ndarray:
        """Ajusta un vector de embedding a la dimension esperada (truncar o pad con ceros)."""
        v = np.asarray(vec, dtype=np.float32).reshape(-1)
        if len(v) == target:
            return v
        if len(v) > target:
            return v[:target]
        pad = np.zeros(target - len(v), dtype=np.float32)
        return np.concatenate([v, pad])

    def _semantic_search(self, query_emb: np.ndarray, top_k: int = TOP_K_SEED) -> list[tuple[str, float]]:
        """Búsqueda por similitud semántica usando FAISS (ultra rápido)."""
        if self.faiss_index is None or self.faiss_index.ntotal == 0:
            return []
        vec = self._normalize_dim(query_emb).reshape(1, -1)
        faiss.normalize_L2(vec)
        scores, indices = self.faiss_index.search(vec, min(top_k, self.faiss_index.ntotal))
        results = []
        for i, idx in enumerate(indices[0]):
            if idx >= 0 and idx < len(self.embedding_codigos):
                results.append((self.embedding_codigos[idx], float(scores[0][i])))
        return results

    def backup_indices(self, dest_path: Path | str | None = None) -> str:
        """Crea un backup comprimido de SQLite, ChromaDB, FAISS y resumenes."""
        try:
            dest = Path(dest_path) if dest_path else Path(__file__).parent.parent / "backups"
            dest.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            zip_file = dest / f"backup_agente_{ts}.zip"

            with zipfile.ZipFile(zip_file, 'w', zipfile.ZIP_DEFLATED) as zf:
                # SQLite
                if self.db_path.exists():
                    zf.write(self.db_path, arcname=self.db_path.name)
                # FAISS
                if FAISS_PATH.exists():
                    zf.write(FAISS_PATH, arcname=FAISS_PATH.name)
                # ChromaDB
                if CHROMA_PATH.exists():
                    for f in CHROMA_PATH.rglob('*'):
                        if f.is_file():
                            arc = f"chroma_db/{f.relative_to(CHROMA_PATH).as_posix()}"
                            zf.write(f, arcname=arc)
                # Resumenes como JSON
                try:
                    resumenes = self.conn.execute("SELECT codigo, resumen_ejecutivo, palabras_clave FROM resumenes").fetchall()
                    resumen_json = {
                        r[0]: {"resumen_ejecutivo": r[1], "palabras_clave": r[2]}
                        for r in resumenes
                    }
                    zf.writestr("resumenes_backup.json", json.dumps(resumen_json, ensure_ascii=False, indent=2))
                except Exception:
                    pass

            return str(zip_file)
        except Exception as e:
            raise RuntimeError(f"Error en backup: {e}")

    def restore_indices(self, zip_file: Path | str) -> dict:
        """Restaura SQLite, ChromaDB, FAISS y resumenes desde un backup ZIP."""
        try:
            zip_path = Path(zip_file)
            if not zip_path.exists():
                raise FileNotFoundError(f"No existe {zip_path}")

            restored = {"sqlite": False, "faiss": False, "chroma": False, "resumenes": False}
            base = self.db_path.parent

            with zipfile.ZipFile(zip_path, 'r') as zf:
                # SQLite
                if self.db_path.name in zf.namelist():
                    target = base / self.db_path.name
                    with zf.open(self.db_path.name) as src, open(target, 'wb') as dst:
                        shutil.copyfileobj(src, dst)
                    restored["sqlite"] = True
                # FAISS
                if FAISS_PATH.name in zf.namelist():
                    target = base / FAISS_PATH.name
                    with zf.open(FAISS_PATH.name) as src, open(target, 'wb') as dst:
                        shutil.copyfileobj(src, dst)
                    restored["faiss"] = True
                # ChromaDB
                chroma_files = [n for n in zf.namelist() if n.startswith("chroma_db/")]
                if chroma_files:
                    if CHROMA_PATH.exists():
                        shutil.rmtree(CHROMA_PATH)
                    CHROMA_PATH.mkdir(parents=True, exist_ok=True)
                    for name in chroma_files:
                        target = base / name
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with zf.open(name) as src, open(target, 'wb') as dst:
                            shutil.copyfileobj(src, dst)
                    restored["chroma"] = True
                # Resumenes JSON (opcional, no reemplaza tabla)
                if "resumenes_backup.json" in zf.namelist():
                    restored["resumenes"] = True

            return restored
        except Exception as e:
            raise RuntimeError(f"Error en restore: {e}")

    def _lexical_search(self, query: str, top_k: int = TOP_K_SEED) -> list[tuple[str, float]]:
        """Búsqueda léxica. Usa BM25 si disponible, sino TF-IDF."""
        if _HAS_BM25 and hasattr(self, "bm25"):
            return self._bm25_search(query, top_k)
        return self._tfidf_search(query, top_k)

    def _bm25_search(self, query: str, top_k: int = TOP_K_SEED) -> list[tuple[str, float]]:
        """Búsqueda por BM25 (mejor que TF-IDF para documentos de longitud variable)."""
        tokens = self.bm25_tokenize(query)
        if not tokens:
            return []
        scores = self.bm25.get_scores(tokens)
        top_idx = scores.argsort()[-top_k:][::-1]
        max_score = scores[top_idx[0]] if scores[top_idx[0]] > 0 else 1.0
        return [(self.embedding_codigos[i], float(scores[i] / max_score))
                for i in top_idx if scores[i] > 0]

    def _tfidf_search(self, query: str, top_k: int = TOP_K_SEED) -> list[tuple[str, float]]:
        """Búsqueda por TF-IDF (fallback)."""
        query_vec = self.tfidf_vectorizer.transform([query])
        scores = linear_kernel(query_vec, self.tfidf_matrix).flatten()
        top_idx = scores.argsort()[-top_k:][::-1]
        return [(self.embedding_codigos[i], float(scores[i])) for i in top_idx if scores[i] > 0]

    def _graph_expand(self, seed_codigos: list[str], max_hops: int = MAX_GRAPH_HOPS,
                      seed_limit: int = 10, max_nodes: int = 200) -> dict[str, float]:
        """Expande desde los seeds usando el grafo. Retorna {codigo: score_grafo}.
        Limita expansion a los top seeds y numero maximo de nodos visitados."""
        graph_scores = defaultdict(float)

        # Usar solo los N mejores seeds para controlar expansion
        seeds = seed_codigos[:seed_limit]
        total_visited = 0

        for seed_codigo in seeds:
            if total_visited >= max_nodes:
                break
            seed_node = f"doc:{seed_codigo}"
            if seed_node not in self.graph:
                continue

            # BFS desde el seed
            visited = {seed_node: 0}
            queue = [(seed_node, 0)]

            while queue and total_visited < max_nodes:
                node, hops = queue.pop(0)
                if hops >= max_hops:
                    continue

                for neighbor in self.graph.neighbors(node):
                    if neighbor not in visited and total_visited < max_nodes:
                        visited[neighbor] = hops + 1
                        queue.append((neighbor, hops + 1))
                        total_visited += 1

                        # Si el vecino es un documento, darle score
                        if neighbor.startswith("doc:"):
                            codigo = neighbor[4:]
                            # Score decrece con la distancia
                            edge_data = self.graph.get_edge_data(node, neighbor) or {}
                            relation = edge_data.get("relation", "")

                            # Ponderar por tipo de relación
                            rel_weight = {
                                "mismo_proceso": 0.6,
                                "pertenece_a_tema": 0.8,
                                "pertenece_a": 0.3,
                                "es_de_tipo": 0.2,
                            }.get(relation, 0.4)

                            score = rel_weight / (hops + 1)
                            graph_scores[codigo] = max(graph_scores[codigo], score)

        return dict(graph_scores)

    def _rerank_with_llm(self, query: str, candidates: list[dict], top_k: int = 5) -> list[dict]:
        """Reordena los candidatos. Usa cross-encoder local + LLM (hybrid reranking).
        1. Cross-encoder para scoring rapido
        2. LLM para reordenar el top 10 final (mas preciso)
        """
        if not candidates:
            return candidates[:top_k]

        # 1. Cross-encoder local (mas rapido y mejor que LLM para reranking inicial)
        if _HAS_CROSSENCODER:
            cross_ranked = self._rerank_cross_encoder(query, candidates, top_k=10)

            # 2. LLM reranking del top 10 (mas preciso, verifica relevancia contextual)
            if len(cross_ranked) > top_k and self.llm:
                print(f"  [GraphRAG] LLM reranking de top {len(cross_ranked)} (hybrid)...")
                llm_ranked = self._rerank_with_llm_fallback(query, cross_ranked, top_k)
                return llm_ranked
            return cross_ranked[:top_k]

        # Fallback: reranking con LLM
        return self._rerank_with_llm_fallback(query, candidates, top_k)

    def _rerank_cross_encoder(self, query: str, candidates: list[dict], top_k: int = 5) -> list[dict]:
        """Reranking con cross-encoder local (sentence-transformers)."""
        if not hasattr(self, "_cross_encoder"):
            print(f"  [GraphRAG] Cargando cross-encoder (primera vez)...")
            try:
                self._cross_encoder = CrossEncoder(
                    "cross-encoder/ms-marco-MiniLM-L-6-v2",
                    max_length=512,
                )
            except Exception as e:
                print(f"  [GraphRAG] Cross-encoder no disponible ({e}), fallback a LLM")
                return self._rerank_with_llm_fallback(query, candidates, top_k)

        print(f"  [GraphRAG] Reranking {len(candidates)} candidatos con cross-encoder...")

        # Preparar pares (query, documento)
        pairs = []
        for c in candidates[:15]:
            doc_text = f"{c['codigo']} {c['nombre']} {c.get('texto', '')[:500]}"
            pairs.append((query, doc_text))

        try:
            scores = self._cross_encoder.predict(pairs)
        except Exception as e:
            print(f"  [GraphRAG] Cross-encoder fallo ({e}), fallback a LLM")
            return self._rerank_with_llm_fallback(query, candidates, top_k)

        # Ordenar por score descendente
        ranked_idx = scores.argsort()[::-1]
        reranked = [candidates[i] for i in ranked_idx if i < len(candidates)]
        return reranked[:top_k]

    def _rerank_with_llm_fallback(self, query: str, candidates: list[dict], top_k: int = 5) -> list[dict]:
        """Reranking con LLM (fallback cuando cross-encoder no disponible)."""
        if not candidates or not self.client:
            return candidates[:top_k]

        docs_list = []
        for i, c in enumerate(candidates[:15]):
            docs_list.append(f"{i+1}. [{c['codigo']}] {c['nombre'][:80]}")

        prompt = (
            f"Pregunta del usuario: {query}\n\n"
            f"Documentos candidatos:\n" + "\n".join(docs_list) + "\n\n"
            f"Ordena los documentos del MÁS relevante al MENOS relevante para responder la pregunta.\n"
            f"Responde SOLO con los números separados por comas, ej: 3,1,5,2,4"
        )

        try:
            resp, provider = self.llm.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=100,
            )
            print(f"  [GraphRAG] Reranking via {provider} (fallback LLM)")
            respuesta = resp.choices[0].message.content.strip()

            orden = []
            for num in re.findall(r'\d+', respuesta):
                idx = int(num) - 1
                if 0 <= idx < len(candidates) and candidates[idx] not in [candidates[i] for i in orden]:
                    orden.append(idx)

            reranked = [candidates[i] for i in orden]
            for i, c in enumerate(candidates[:15]):
                if c not in reranked:
                    reranked.append(c)

            return reranked[:top_k]

        except Exception as e:
            print(f"  [GraphRAG] Reranking fallo ({e}), usando orden original")
            return candidates[:top_k]

    def _expand_query(self, query: str) -> str:
        """Query Expansion: expande abreviaciones y terminos del dominio.
        Ej: 'IQ OQ PQ' -> 'instalacion qualification operational qualification performance qualification'
        """
        query_lower = query.lower()
        expanded_terms = []
        for abbr, expansion in QUERY_EXPANSION_DICT.items():
            # Match exacto de palabra (no substring)
            pattern = r'\b' + re.escape(abbr) + r'\b'
            if re.search(pattern, query_lower):
                if expansion not in query_lower:
                    expanded_terms.append(expansion)

        if expanded_terms:
            expanded = query + " " + " ".join(expanded_terms[:5])
            print(f"  [GraphRAG] Query expansion: +{len(expanded_terms)} terminos")
            return expanded
        return query

    def _needs_retrieval(self, query: str) -> bool:
        """Self-RAG: determina si la pregunta necesita retrieval de documentos.
        Preguntas de saludo, meta, o generales no necesitan retrieval.
        """
        query_lower = query.lower().strip()

        # Patrones que NO necesitan retrieval
        no_retrieval_patterns = [
            r'^(hola|buenos d[ií]as|buenas tardes|buenas noches|hi|hello)\b',
            r'^(gracias|muchas gracias|ok|entendido|perfecto)\b',
            r'^(qu[eé] puedes hacer|qu[eé] haces|ayuda|help|comandos)\b',
            r'^(qui[eé]n eres|c[oó]mo te llamas|tu nombre)\b',
            r'^(qu[eé] es (un |una )?(sop|procedimiento|no conformidad))\b.*\?$',
        ]

        for pattern in no_retrieval_patterns:
            if re.match(pattern, query_lower):
                print(f"  [GraphRAG] Self-RAG: sin retrieval (pregunta generico/saludo)")
                return False

        # Si la pregunta es muy corta y no contiene keywords de calidad, no recuperar
        if len(query_lower) < 10:
            return False

        return True

    def _calculate_confidence(self, resultados: list[dict]) -> dict:
        """Confidence Score: calcula nivel de confianza de la respuesta.
        Retorna: {nivel: 'alto'|'medio'|'bajo', score: float, razon: str}
        """
        if not resultados:
            return {"nivel": "bajo", "score": 0.0, "razon": "Sin documentos recuperados"}

        top_score = resultados[0].get("score_total", 0)
        avg_score = sum(r.get("score_total", 0) for r in resultados) / len(resultados)
        n_docs = len(resultados)
        top_sem = resultados[0].get("score_semantico", 0)
        top_lex = resultados[0].get("score_lexical", 0)

        # Confianza alta: top score alto + multiple docs + semantico alto
        if top_score > 0.35 and n_docs >= 3 and top_sem > 0.7:
            return {
                "nivel": "alto",
                "score": round(top_score, 3),
                "razon": f"Score alto ({top_score:.3f}), {n_docs} docs, semantico {top_sem:.2f}",
            }
        # Confianza media: scores moderados
        elif top_score > 0.15 or (top_sem > 0.5 and n_docs >= 2):
            return {
                "nivel": "medio",
                "score": round(top_score, 3),
                "razon": f"Score moderado ({top_score:.3f}), {n_docs} docs",
            }
        # Confianza baja: scores bajos
        else:
            return {
                "nivel": "bajo",
                "score": round(top_score, 3),
                "razon": f"Score bajo ({top_score:.3f}), {n_docs} docs",
            }

    def _detect_hallucination(self, respuesta: str, documentos: list[dict]) -> dict:
        """Hallucination Detection: verifica que la respuesta este sustentada en los documentos.
        Usa heuristica + LLM para verificar claims.
        Retorna: {hallucination: bool, score: float, claims_verificados: int, claims_no_sustentados: int}
        """
        if not documentos or not respuesta:
            return {"hallucination": False, "score": 1.0, "claims_verificados": 0, "claims_no_sustentados": 0}

        # 1. Heuristica: extraer codigos citados y verificar que esten en los documentos
        codigos_citados = set(re.findall(r'\b[A-Z]{2,5}[-_]\w{2,}[-_]\d{1,}\b', respuesta))
        codigos_docs = set(d.get("codigo", "") for d in documentos)
        codigos_no_encontrados = codigos_citados - codigos_docs

        # 2. Heuristica: verificar que palabras clave de la respuesta esten en los documentos
        texto_docs = " ".join(d.get("texto", "") for d in documentos).lower()
        # Extraer afirmaciones (frases con verbos de afirmacion)
        afirmaciones = re.findall(r'(?:debe|requiere|establece|define|est[aá] compuesto|incluye|contiene|se realiza|se debe)\s+[^.]{10,80}', respuesta.lower())

        claims_sustentados = 0
        claims_no_sustentados = 0

        for af in afirmaciones[:10]:  # limitar a 10 claims
            # Extraer palabras clave de la afirmacion
            keywords = re.findall(r'[a-záéíóúñ]{4,}', af)
            keywords = [k for k in keywords if k not in {'debe', 'requiere', 'establece', 'define', 'incluye', 'contiene'}]
            if not keywords:
                continue
            # Verificar cuantas keywords estan en los documentos
            matches = sum(1 for k in keywords if k in texto_docs)
            ratio = matches / len(keywords) if keywords else 0
            if ratio > 0.3:
                claims_sustentados += 1
            else:
                claims_no_sustentados += 1

        # 3. LLM verification (si hay claims no sustentados)
        hallucination_score = 1.0 - (len(codigos_no_encontrados) / max(len(codigos_citados), 1)) if codigos_citados else 1.0

        if claims_no_sustentados > 0 and self.llm:
            try:
                doc_text = "\n".join(d.get("texto", "")[:500] for d in documentos[:3])
                prompt = (
                    f"Verifica si la siguiente respuesta esta sustentada en los documentos.\n\n"
                    f"Respuesta: {respuesta[:1000]}\n\n"
                    f"Documentos:\n{doc_text}\n\n"
                    f"Responde SOLO con un JSON: {{\"sustentado\": true/false, \"score\": 0.0-1.0}}"
                )
                resp_llm, _ = self.llm.chat(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.0,
                    max_tokens=100,
                )
                llm_resp = resp_llm.choices[0].message.content.strip()
                # Extraer JSON
                import json
                json_match = re.search(r'\{[^}]+\}', llm_resp)
                if json_match:
                    result = json.loads(json_match.group())
                    hallucination_score = result.get("score", hallucination_score)
                    if not result.get("sustentado", True):
                        claims_no_sustentados += 1
            except Exception:
                pass  # fallback a heuristica

        total_claims = claims_sustentados + claims_no_sustentados
        hallucination = claims_no_sustentados > total_claims * 0.3 if total_claims > 0 else False

        return {
            "hallucination": hallucination,
            "score": round(hallucination_score, 3),
            "claims_verificados": total_claims,
            "claims_no_sustentados": claims_no_sustentados,
            "codigos_citados": len(codigos_citados),
            "codigos_no_encontrados": len(codigos_no_encontrados),
        }

    def _hyde_generate(self, query: str) -> str | None:
        """HyDE: genera un documento hipotetico de respuesta para mejorar retrieval.
        El LLM genera una respuesta hipotetica, se embede y se usa para busqueda semantica.
        Esto mejora el recall porque el documento hipotetico esta mas cerca de los
        documentos reales que la pregunta original.
        """
        try:
            prompt = (
                f"Eres un experto en calidad HSEQ farmaceutica. "
                f"Responde brevemente (maximo 200 palabras) la siguiente pregunta "
                f"como si fuera un fragmento de un procedimiento de calidad:\n\n"
                f"Pregunta: {query}\n\nRespuesta hipotetica:"
            )
            resp, provider = self.llm.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=300,
            )
            hyde_text = resp.choices[0].message.content.strip()
            if len(hyde_text) > 50:
                print(f"  [GraphRAG] HyDE: documento hipotetico generado ({len(hyde_text)} chars, via {provider})")
                return hyde_text
        except Exception as e:
            print(f"  [GraphRAG] HyDE: no disponible ({e}), usando query original")
        return None

    def _multi_query_reformulate(self, query: str) -> list[str]:
        """Multi-query: reformula la pregunta en 3 variantes para mejorar recall.
        Si el LLM no esta disponible, usa variaciones basadas en keywords.
        """
        try:
            prompt = (
                f"Eres un experto en calidad HSEQ. Reformula la siguiente pregunta "
                f"en 3 variantes diferentes que busquen la misma informacion. "
                f"Responde SOLO con las 3 variantes, una por linea, sin numeracion.\n\n"
                f"Pregunta original: {query}\n\nVariantes:"
            )
            resp, provider = self.llm.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=200,
            )
            text = resp.choices[0].message.content.strip()
            variantes = [v.strip() for v in text.split("\n") if v.strip() and len(v.strip()) > 10]
            if len(variantes) >= 2:
                print(f"  [GraphRAG] Multi-query: {len(variantes)} variantes generadas (via {provider})")
                return variantes[:3]
        except Exception:
            pass

        # Fallback: variaciones simples basadas en keywords
        variantes = [query]
        if "?" in query:
            variantes.append(query.replace("?", " procedimiento"))
        if not query.startswith("como"):
            variantes.append(f"como {query}")
        return variantes[:3]

    def _crag_evaluate(self, query: str, resultados: list[dict]) -> str:
        """Corrective RAG: evalua la calidad de la recuperacion.
        Retorna: 'good', 'ambiguous', o 'poor'
        """
        if not resultados:
            return "poor"

        # Evaluar por scores
        top_score = resultados[0].get("score_total", 0)
        avg_score = sum(r.get("score_total", 0) for r in resultados) / len(resultados)

        # Si el top score es alto y hay varios resultados, es good
        if top_score > 0.3 and len(resultados) >= 3:
            return "good"
        # Si hay algunos resultados pero scores bajos, es ambiguous
        elif top_score > 0.1 or len(resultados) >= 2:
            return "ambiguous"
        else:
            return "poor"

    def _multi_vector_search(self, query: str, top_k: int = 10) -> dict[str, float]:
        """Multi-vector retrieval (ColBERT simplificado).
        Divide la query en tokens y busca cada token individualmente.
        Fusiona los scores con MaxSim (como ColBERT).
        Retorna: {codigo: max_sim_score}
        """
        # Dividir query en tokens significativos
        query_tokens = re.findall(r"[a-záéíóúñ]{3,}", query.lower())
        # Quitar stopwords basicas
        stopwords = {"que", "como", "para", "por", "con", "sin", "una", "uno",
                     "del", "las", "los", "este", "esta", "pero", "mas", "menos"}
        query_tokens = [t for t in query_tokens if t not in stopwords]

        if not query_tokens or len(query_tokens) < 2:
            return {}

        # Para cada token, buscar semánticamente y guardar el score
        token_scores: dict[str, list[float]] = {}
        for token in query_tokens[:8]:  # limitar a 8 tokens
            try:
                token_emb = self._embed_query(token)
                results = self._semantic_search(token_emb, top_k=top_k)
                for codigo, score in results:
                    if codigo not in token_scores:
                        token_scores[codigo] = []
                    token_scores[codigo].append(score)
            except Exception:
                pass

        # MaxSim: para cada documento, el score es la suma de los maximos scores por token
        max_sim_scores = {}
        n_tokens = len(query_tokens)
        for codigo, scores in token_scores.items():
            # Score = (numero de tokens que matchearon / total tokens) * promedio de scores
            coverage = len(scores) / n_tokens if n_tokens > 0 else 0
            avg_score = sum(scores) / len(scores) if scores else 0
            max_sim_scores[codigo] = coverage * avg_score

        return max_sim_scores

    def _es_pregunta_rapida(self, query: str, sem_top_score: float = 0.0) -> bool:
        """Detecta si la pregunta puede resolverse con retrieval rapido."""
        q = query.lower().strip()
        palabras = q.split()

        # Corta (< 15 palabras)
        if len(palabras) < 15:
            return True

        # Contiene codigo de documento (ej. PGC-31-09, MGC-35-04)
        if re.search(r"\b[A-Z]{2,3}-\d{2,3}-\d{2,4}\b", query.upper()):
            return True

        # Preguntas definitorias
        definitorias = [
            "que es", "qué es", "cuando", "cuándo", "quien", "quién",
            "como se define", "cómo se define", "definicion", "definición",
            "explique", "explícame", "dime", "cuales son", "cuáles son",
            "donde encuentro", "dónde encuentro", "como se", "cómo se",
        ]
        if any(d in q for d in definitorias):
            return True

        # Alto score semantico directo
        if sem_top_score > 0.85:
            return True

        return False

    def _es_pregunta_compleja(self, query: str) -> bool:
        """Detecta si la pregunta requiere analisis profundo (HyDE, multi-query)."""
        q = query.lower()
        complejas = [
            "comparar", "compara", "diferencias", "relación", "relacion",
            "causa raíz", "causa raiz", "analiza", "analizar", "5 porqués",
            "5 porques", "fmea", "ishikawa", "capa", "plan de accion",
            "auditoria", "auditoría", "mejores prácticas", "mejores practicas",
            "riesgo", "impacto", "si", "escenario", "hipotetico",
        ]
        return any(c in q for c in complejas)

    def retrieve(self, query: str, top_k: int = TOP_K_FINAL,
                 use_reranking: bool = True, modo_rapido: bool | None = None) -> list[dict]:
        """Recuperación híbrida: semántico + lexical + grafo + multi-vector.
        Incluye Query Expansion, HyDE, multi-query retrieval, CRAG, RRF y ColBERT simplificado.
        """
        # 0. Query Expansion: expandir abreviaciones del dominio
        expanded_query = self._expand_query(query)

        # 1. Búsqueda semántica rapida inicial para decidir estrategia
        query_emb = self._embed_query(expanded_query)
        sem_seed_results = self._semantic_search(query_emb, top_k=TOP_K_SEED)
        top_sem_score = sem_seed_results[0][1] if sem_seed_results else 0.0

        lex_seed_results = self._lexical_search(expanded_query, top_k=TOP_K_SEED)
        top_lex_score = lex_seed_results[0][1] if lex_seed_results else 0.0

        # Decidir modo rapido: si se pasa explicito, respetarlo
        if modo_rapido is None:
            modo_rapido = self._es_pregunta_rapida(query, top_sem_score)
            usar_completo = self._es_pregunta_compleja(query)
            if usar_completo:
                modo_rapido = False

        print(f"  [GraphRAG] Modo retrieval: {'rapido' if modo_rapido else 'completo'}")

        # 2. HyDE y multi-query solo si es necesario (modo complejo o score bajo)
        hyde_text = ""
        query_variants = [expanded_query]
        if not modo_rapido or top_sem_score < 0.6 or top_lex_score < 0.3:
            hyde_text = self._hyde_generate(query)
            query_variants = self._multi_query_reformulate(query)

        # 3. Generar embeddings: query expandida + HyDE + variantes
        embeddings_to_search = [query_emb]

        if hyde_text:
            hyde_emb = self._embed_query(hyde_text)
            embeddings_to_search.append(hyde_emb)

        for v in query_variants[1:]:  # skip first (original)
            try:
                v_emb = self._embed_query(v)
                embeddings_to_search.append(v_emb)
            except Exception:
                pass

        # 4. Búsqueda semántica con todos los embeddings (fusion)
        sem_results = {}
        for emb in embeddings_to_search:
            results = self._semantic_search(emb, top_k=TOP_K_SEED)
            for codigo, score in results:
                # Max fusion: quedarse con el mejor score
                sem_results[codigo] = max(sem_results.get(codigo, 0), score)

        # 5. Búsqueda lexical BM25 con query original + variantes
        lex_results = {}
        for q in query_variants:
            results = self._lexical_search(q, top_k=TOP_K_SEED)
            for codigo, score in results:
                lex_results[codigo] = max(lex_results.get(codigo, 0), score)

        # 6. Combinar seeds
        all_seeds = set(sem_results.keys()) | set(lex_results.keys())

        # 6b. Multi-vector retrieval (ColBERT simplificado) - omitir en modo rapido
        mv_results = {}
        if not modo_rapido:
            mv_results = self._multi_vector_search(query, top_k=TOP_K_SEED)
            if mv_results:
                print(f"  [GraphRAG] Multi-vector (ColBERT): {len(mv_results)} candidatos")
                all_seeds = all_seeds | set(mv_results.keys())

        # 6c. NER entity search (busqueda por entidades extraidas) - rapido solo si hay entidades
        ner_results = {}
        if _HAS_RETRIEVAL_ADV:
            try:
                ner_results = search_by_entities(query, self.conn, top_k=TOP_K_SEED)
                if ner_results:
                    print(f"  [GraphRAG] NER entities: {len(ner_results)} candidatos")
                    all_seeds = all_seeds | set(ner_results.keys())
            except Exception as e:
                print(f"  [GraphRAG] NER error (no critico): {e}")

        # 6d. RAPTOR retrieval (busqueda en arbol jerarquico) - omitir en modo rapido
        raptor_results = {}
        if not modo_rapido and _HAS_RETRIEVAL_ADV:
            try:
                raptor_docs = raptor_retrieve(query, self.conn, top_k=TOP_K_SEED)
                for doc in raptor_docs:
                    raptor_results[doc["codigo"]] = doc["score"]
                if raptor_results:
                    print(f"  [GraphRAG] RAPTOR: {len(raptor_results)} candidatos")
            except Exception as e:
                print(f"  [GraphRAG] RAPTOR error (no critico): {e}")

        # 6e. Parent-child retrieval (chunks pequeños -> contexto padre)
        pc_results = {}
        if _HAS_RETRIEVAL_ADV:
            try:
                pc_docs = retrieve_parent_child(query, self.conn, top_k=TOP_K_SEED)
                for doc in pc_docs:
                    pc_results[doc["codigo"]] = doc["score"]
                if pc_results:
                    print(f"  [GraphRAG] Parent-child: {len(pc_results)} candidatos")
            except Exception as e:
                print(f"  [GraphRAG] Parent-child error (no critico): {e}")

        # 7. Expansión por grafo (limitada en modo rapido)
        try:
            t_graph_start = time.time()
            graph_seed_limit = 10 if modo_rapido else 30
            graph_max_nodes = 200 if modo_rapido else 800
            graph_scores = self._graph_expand(list(all_seeds), max_hops=MAX_GRAPH_HOPS,
                                              seed_limit=graph_seed_limit,
                                              max_nodes=graph_max_nodes)
            print(f"  [GraphRAG] Graph expand: {len(graph_scores)} candidatos ({time.time()-t_graph_start:.2f}s)")
        except Exception as e:
            print(f"  [GraphRAG] Graph expand error (no critico): {e}")
            graph_scores = {}

        # 8. Scoring híbrido (RRF o suma ponderada)
        candidates = set(sem_results.keys()) | set(lex_results.keys()) | set(graph_scores.keys()) | set(mv_results.keys()) | set(ner_results.keys()) | set(raptor_results.keys()) | set(pc_results.keys())
        print(f"  [GraphRAG] Total candidatos unicos: {len(candidates)}")

        if USE_RRF:
            # Reciprocal Rank Fusion: RRF(d) = Σ 1/(k + rank_i(d))
            # Crear rankings por cada sistema
            sem_ranked = sorted(sem_results.items(), key=lambda x: x[1], reverse=True)
            lex_ranked = sorted(lex_results.items(), key=lambda x: x[1], reverse=True)
            gra_ranked = sorted(graph_scores.items(), key=lambda x: x[1], reverse=True)
            mv_ranked = sorted(mv_results.items(), key=lambda x: x[1], reverse=True)
            ner_ranked = sorted(ner_results.items(), key=lambda x: x[1], reverse=True)
            raptor_ranked = sorted(raptor_results.items(), key=lambda x: x[1], reverse=True)
            pc_ranked = sorted(pc_results.items(), key=lambda x: x[1], reverse=True)

            # Reciprocal Rank Fusion con lookups O(1) para evitar bucles anidados
            rank_maps = {
                "sem": {code: rank for rank, (code, _) in enumerate(sem_ranked)},
                "lex": {code: rank for rank, (code, _) in enumerate(lex_ranked)},
                "gra": {code: rank for rank, (code, _) in enumerate(gra_ranked)},
                "mv": {code: rank for rank, (code, _) in enumerate(mv_ranked)},
                "ner": {code: rank for rank, (code, _) in enumerate(ner_ranked)},
                "raptor": {code: rank for rank, (code, _) in enumerate(raptor_ranked)},
                "pc": {code: rank for rank, (code, _) in enumerate(pc_ranked)},
            }

            rrf_scores = {}
            feedback_boost = self._doc_feedback_boosts(candidates)
            for codigo in candidates:
                rrf = 0.0
                for rank_map in rank_maps.values():
                    rank = rank_map.get(codigo)
                    if rank is not None:
                        rrf += 1.0 / (RRF_K + rank + 1)
                boost = feedback_boost.get(codigo, 0.0)
                rrf_scores[codigo] = rrf * (1.0 + boost)

            scored = [(codigo, rrf_scores[codigo],
                       sem_results.get(codigo, 0.0),
                       lex_results.get(codigo, 0.0),
                       graph_scores.get(codigo, 0.0))
                      for codigo in candidates]
            print(f"  [GraphRAG] Scoring: RRF (k={RRF_K})")
        else:
            feedback_boost = self._doc_feedback_boosts(candidates)
            scored = []
            for codigo in candidates:
                sem_score = sem_results.get(codigo, 0.0)
                lex_score = lex_results.get(codigo, 0.0)
                gra_score = graph_scores.get(codigo, 0.0)
                total = (
                    W_SEMANTIC * sem_score
                    + W_LEXICAL * lex_score
                    + W_GRAPH * gra_score
                )
                boost = feedback_boost.get(codigo, 0.0)
                scored.append((codigo, total * (1.0 + boost), sem_score, lex_score, gra_score))

        scored.sort(key=lambda x: x[1], reverse=True)

        # 9. Construir resultados con contexto del grafo
        # Reranking pool: menor en modo rapido
        rerank_pool_default = 15
        if modo_rapido:
            rerank_pool_default = 7
        rerank_pool = min(top_k * 3, rerank_pool_default) if use_reranking else top_k

        resultados = []
        for codigo, total, sem, lex, gra in scored[:rerank_pool]:
            doc = self.docs.get(codigo, {})
            grafo_info = self._get_graph_context(codigo)
            try:
                secciones = self._get_relevant_sections(codigo, query, max_sections=3 if not modo_rapido else 2)
            except Exception:
                secciones = []
            resultados.append({
                "codigo": codigo,
                "nombre": doc.get("nombre", ""),
                "proceso": doc.get("proceso_nom", ""),
                "tipo_documento": doc.get("tipo_documento", ""),
                "estado": doc.get("estado_desc", ""),
                "fecha_publicacion": doc.get("fecha_publicacion", ""),
                "score_total": total,
                "score_semantico": sem,
                "score_lexical": lex,
                "score_grafo": gra,
                "texto": doc.get("texto", "")[:2500],
                "secciones": secciones,
                "grafo": grafo_info,
            })
        print(f"  [GraphRAG] Resultados construidos: {len(resultados)}")

        # 10. CRAG: evaluar calidad de la recuperacion
        try:
            crag_quality = self._crag_evaluate(query, resultados)
            if crag_quality == "poor":
                print(f"  [GraphRAG] CRAG: recuperacion POOR (scores bajos)")
                if len(resultados) < top_k:
                    for codigo, total, sem, lex, gra in scored[rerank_pool:rerank_pool + top_k]:
                        doc = self.docs.get(codigo, {})
                        grafo_info = self._get_graph_context(codigo)
                        resultados.append({
                            "codigo": codigo,
                            "nombre": doc.get("nombre", ""),
                            "proceso": doc.get("proceso_nom", ""),
                            "tipo_documento": doc.get("tipo_documento", ""),
                            "estado": doc.get("estado_desc", ""),
                            "fecha_publicacion": doc.get("fecha_publicacion", ""),
                            "score_total": total,
                            "score_semantico": sem,
                            "score_lexical": lex,
                            "score_grafo": gra,
                            "texto": doc.get("texto", "")[:2500],
                            "secciones": [],
                            "grafo": grafo_info,
                        })
            elif crag_quality == "ambiguous":
                print(f"  [GraphRAG] CRAG: recuperacion AMBIGUOUS (scores medios)")
            else:
                print(f"  [GraphRAG] CRAG: recuperacion GOOD (scores altos)")
        except Exception as e:
            print(f"  [GraphRAG] CRAG error (no critico): {e}")

        # 11. Reranking con cross-encoder (o LLM fallback)
        if use_reranking and len(resultados) > top_k:
            try:
                print(f"  [GraphRAG] Reranking {len(resultados)} candidatos...")
                resultados = self._rerank_with_llm(query, resultados, top_k=top_k)
            except Exception as e:
                print(f"  [GraphRAG] Reranking error (no critico): {e}")

        return resultados[:top_k]

    def _semantic_chunking(self, texto: str, max_chunk_size: int = 500) -> list[str]:
        """Chunking semantico: divide el texto por limites semanticos (oraciones).
        Agrupa oraciones hasta alcanzar el tamano optimo de chunk.
        Mas preciso que dividir por headers fijos.
        """
        if not texto or len(texto) < 100:
            return [texto] if texto else []

        # 1. Dividir en oraciones (puntos, signos de exclamacion, interrogacion)
        oraciones = re.split(r'(?<=[.!?])\s+', texto)
        oraciones = [o.strip() for o in oraciones if o.strip()]

        if not oraciones:
            return [texto]

        # 2. Agrupar oraciones en chunks semanticos
        chunks = []
        chunk_actual = ""
        for oracion in oraciones:
            if len(chunk_actual) + len(oracion) < max_chunk_size:
                chunk_actual += " " + oracion if chunk_actual else oracion
            else:
                if chunk_actual:
                    chunks.append(chunk_actual.strip())
                chunk_actual = oracion

        if chunk_actual:
            chunks.append(chunk_actual.strip())

        # 3. Filtrar chunks muy cortos
        chunks = [c for c in chunks if len(c) > 50]
        return chunks

    def _hierarchical_chunking(self, texto: str) -> list[str]:
        """Chunking jerarquico: divide por encabezados HTML/titulos en mayusculas.
        Mantiene la estructura de secciones del documento."""
        if not texto or len(texto) < 100:
            return [texto] if texto else []

        # 1. Intentar dividir por headers HTML
        html_headers = re.split(r'\n(?=<h[1-6][^>]*>|[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ\s]{4,}:?)', texto)
        if len(html_headers) >= 3:
            return [h.strip() for h in html_headers if len(h.strip()) > 50]

        # 2. Fallback: dividir por lineas dobles o numeros de seccion
        fallback = re.split(r'\n{2,}|(?:^|\n)\d+[.\)]\s+[A-ZÁÉÍÓÚÑ]', texto)
        fallback = [f.strip() for f in fallback if len(f.strip()) > 50]
        return fallback if fallback else [texto]

    def _late_chunking(self, texto: str, chunk_size: int = 500) -> list[dict]:
        """Late chunking: primero embedding del documento completo,
        luego chunks con contexto global. Usa embeddings del LLM configurado."""
        if not texto or len(texto) < 100:
            return [{"text": texto, "start": 0, "end": len(texto), "doc_embedding": None, "chunk_embedding": None}] if texto else []

        try:
            # Generar embedding del documento completo (late context)
            doc_emb, _ = self.llm.embeddings(texto[:4000])
            doc_emb = np.array(doc_emb)
        except Exception:
            doc_emb = None

        chunks = []
        # Semantic chunk base
        secciones = self._semantic_chunking(texto, max_chunk_size=chunk_size)
        start = 0
        for sec in secciones:
            try:
                sec_emb, _ = self.llm.embeddings(sec[:2000])
                sec_emb = np.array(sec_emb)
            except Exception:
                sec_emb = None
            end = start + len(sec)
            chunks.append({
                "text": sec,
                "start": start,
                "end": end,
                "doc_embedding": doc_emb,
                "chunk_embedding": sec_emb,
            })
            start = end
        return chunks

    def _get_relevant_sections(self, codigo: str, query: str, max_sections: int = 3) -> list[dict]:
        """Parent-child retrieval: obtiene las secciones mas relevantes del documento.
        Usa chunking semantico, jerarquico o late chunking segun el documento."""
        doc = self.docs.get(codigo, {})
        texto = doc.get("texto", "")
        if not texto or len(texto) < 200:
            return []

        # Estrategia de chunking segun tamano y estructura
        if len(texto) > 8000:
            # Documentos grandes: late chunking con contexto global
            late_chunks = self._late_chunking(texto, chunk_size=500)
            secciones = [c["text"] for c in late_chunks]
        else:
            # Documentos medianos: intentar chunking jerarquico
            secciones = self._hierarchical_chunking(texto)
            if len(secciones) < 3:
                # Fallback a chunking semantico
                secciones = self._semantic_chunking(texto, max_chunk_size=500)

        # Fallback final
        if len(secciones) < 3:
            header_sections = re.split(r'\n(?=[A-Z][A-ZÁÉÍÓÚ\s]{5,}:?)', texto)
            if len(header_sections) > len(secciones):
                secciones = header_sections
            elif len(secciones) <= 1:
                secciones = texto.split("\n\n")

        # Filtrar secciones muy cortas
        secciones = [s for s in secciones if len(s.strip()) > 50]

        if not secciones:
            return []

        # BM25 sobre las secciones del documento
        query_tokens = re.findall(r"[a-záéíóúñ]{3,}", query.lower())
        if not query_tokens:
            return []

        try:
            from rank_bm25 import BM25Okapi
            sec_tokens = [re.findall(r"[a-záéíóúñ]{3,}", s.lower()) for s in secciones]
            bm25_sec = BM25Okapi(sec_tokens)
            scores = bm25_sec.get_scores(query_tokens)
            top_idx = scores.argsort()[-max_sections:][::-1]
            return [
                {
                    "texto": secciones[i].strip()[:800],
                    "score": float(scores[i]),
                }
                for i in top_idx if scores[i] > 0
            ]
        except Exception:
            return []

    def _get_graph_context(self, codigo: str) -> dict:
        """Obtiene el contexto del grafo para un documento."""
        node = f"doc:{codigo}"
        if node not in self.graph:
            return {}

        procesos = []
        tipos = []
        usuarios = []
        temas = []
        docs_relacionados = []

        for neighbor in self.graph.neighbors(node):
            n_data = self.graph.nodes[neighbor]
            edge = self.graph.get_edge_data(node, neighbor) or {}
            relation = edge.get("relation", "")
            n_type = n_data.get("type", "")

            if n_type == "proceso":
                procesos.append(n_data.get("nombre", ""))
            elif n_type == "tipo_documento":
                tipos.append(n_data.get("nombre", ""))
            elif n_type == "usuario":
                usuarios.append({"nombre": n_data.get("nombre", ""), "rol": relation})
            elif n_type == "tema":
                temas.append(n_data.get("nombre", ""))
            elif n_type == "documento" and neighbor != node:
                docs_relacionados.append({
                    "codigo": n_data.get("codigo", ""),
                    "nombre": n_data.get("nombre", ""),
                    "relation": relation,
                })

        return {
            "procesos": procesos,
            "tipos": tipos,
            "usuarios": usuarios[:4],  # limitar
            "temas": temas,
            "docs_relacionados": docs_relacionados[:5],
        }

    # ──────────────────────────────────────────────
    # Generación de respuesta
    # ──────────────────────────────────────────────

    def _filtrar_obsoletos(self, resultados: list[dict]) -> list[dict]:
        """Filtra documentos obsoletos de los resultados.
        Excluye cualquier documento con estado 'O' (Obsoleto).
        """
        filtrados = []
        excluidos = 0
        for r in resultados:
            estado = (r.get("estado") or "").upper().strip()
            # Excluir obsoletos
            if estado == "OBSOLETO" or estado == "O":
                excluidos += 1
                continue
            filtrados.append(r)
        if excluidos > 0:
            print(f"  [GraphRAG] {excluidos} documentos obsoletos excluidos")
        return filtrados

    def ask(self, question: str, modo_rapido: bool | None = None) -> tuple[str, list[dict]]:
        """Responde una pregunta usando Graph RAG."""
        # ── DLP input check: verificar intento de extraccion de datos ──
        if _HAS_CALIDAD_SEG:
            try:
                dlp_input = check_input_dlp(question)
                if not dlp_input["is_safe"]:
                    print(f"  [GraphRAG] DLP: entrada bloqueada (intento de extraccion de datos)")
                    return "No puedo proporcionar informacion sensible como credenciales, API keys o datos personales. Por favor, haz una pregunta relacionada con calidad HSEQ.", []
            except Exception as e:
                print(f"  [GraphRAG] DLP input check error (no critico): {e}")

        # ── Agentic Planner: crear plan de accion ──
        if _HAS_AGENTIC and self.planner:
            try:
                plan = self.planner.plan(question)
                if plan.get("needs_planning"):
                    print(f"  [GraphRAG] Plan agentic: {plan['complexity']} ({len(plan['steps'])} pasos)")
            except Exception as e:
                print(f"  [GraphRAG] Planner error (no critico): {e}")

        # ── Guardrail de entrada: governance ──
        if self.governance:
            ok, reason = self.governance.validate_input(question)
            if not ok:
                safe = self.governance.safe_response(reason)
                print(f"  [GraphRAG] Entrada bloqueada por governance: {reason}")
                return safe, []

        # ── Content moderation de entrada ──
        if self.moderation:
            mod_result = self.moderation.moderate(question)
            if mod_result.get("blocked"):
                safe = (
                    f"Tu mensaje fue bloqueado por content moderation. "
                    f"Categoria: {mod_result.get('category', 'N/A')}. "
                    f"Por favor, mantén la conversación enfocada en calidad HSEQ."
                )
                print(f"  [GraphRAG] Entrada bloqueada por moderation: {mod_result.get('category')}")
                return safe, []
            question = mod_result.get("filtered_text", question)

        # ── FAQ precargada: respuestas instantáneas para preguntas frecuentes ──
        faq = self.buscar_faq_precargada(question, threshold=0.90)
        if faq:
            print(f"  [GraphRAG] FAQ HIT ({faq['match']}): respuesta precargada")
            return faq["respuesta"], []

        # ── Cache semantico: buscar si ya respondimos esta pregunta ──
        cached = self._buscar_cache_semantico(question, threshold=0.92)
        if not cached and self.memoria:
            cached = self.memoria.cache_semantic_lookup(question)
        if cached:
            print(f"  [GraphRAG] Cache HIT (match: {cached.get('match_type', 'exact')}, sim: {cached.get('similarity', 'N/A')})")
            return cached["respuesta"], []

        # ── Self-RAG: determinar si necesita retrieval ──
        needs_retrieval = self._needs_retrieval(question)

        # Iniciar traza de observabilidad
        trace_id = self.obs.start_trace(question)

        if not needs_retrieval:
            # Self-RAG: responder directo sin retrieval
            print(f"\n  [GraphRAG] Self-RAG: respondiendo sin retrieval")
            confidence = {"nivel": "alto", "score": 1.0, "razon": "Respuesta directa (sin retrieval)"}
            resultados = []
        else:
            print(f"\n  [GraphRAG] Recuperando documentos...")
            t_rec_start = time.time()
            resultados = self.retrieve(question, top_k=TOP_K_FINAL * 2, modo_rapido=modo_rapido)

            # Filtrar documentos obsoletos
            n_before = len(resultados)
            resultados = self._filtrar_obsoletos(resultados)
            n_obsoletos = n_before - len(resultados)
            resultados = resultados[:TOP_K_FINAL]
            t_rec_end = time.time()

            # Trackear recuperación
            self.obs.track_retrieval(
                trace_id, question, len(resultados), n_obsoletos,
                t_rec_end - t_rec_start
            )

            print(f"  [GraphRAG] {len(resultados)} documentos vigentes recuperados:")
            for i, r in enumerate(resultados):
                print(f"    {i+1}. {r['codigo']} (total={r['score_total']:.3f} "
                      f"sem={r['score_semantico']:.2f} lex={r['score_lexical']:.2f} "
                      f"grafo={r['score_grafo']:.2f}) - {r['nombre'][:50]}")

            # ── Confidence Score ──
            confidence = self._calculate_confidence(resultados)
            print(f"  [GraphRAG] Confidence: {confidence['nivel']} ({confidence['score']:.3f}) - {confidence['razon']}")

        # Glosario relevante
        glosario_ctx = glosario_para_contexto(question)

        # Construir contexto enriquecido con grafo + resúmenes
        contexto_parts = []
        for i, r in enumerate(resultados):
            grafo = r.get("grafo", {})
            grafo_str = ""
            if grafo.get("procesos"):
                grafo_str += f"Proceso: {', '.join(grafo['procesos'])}\n"
            if grafo.get("temas"):
                grafo_str += f"Tema: {', '.join(grafo['temas'])}\n"
            if grafo.get("docs_relacionados"):
                rels = [f"{d['codigo']} ({d['relation']})" for d in grafo['docs_relacionados'][:3]]
                grafo_str += f"Documentos relacionados: {', '.join(rels)}\n"

            # Resumen ejecutivo si existe
            resumen = self.get_resumen(r["codigo"])
            resumen_str = ""
            if resumen and resumen.get("resumen"):
                resumen_str = f"Resumen ejecutivo: {resumen['resumen']}\n"
                if resumen.get("proposito"):
                    resumen_str += f"Propósito: {resumen['proposito']}\n"
                if resumen.get("alcance"):
                    resumen_str += f"Alcance: {resumen['alcance']}\n"
                if resumen.get("palabras_clave"):
                    resumen_str += f"Palabras clave: {resumen['palabras_clave']}\n"

            contexto_parts.append(
                f"--- Documento {i+1}: {r['codigo']} ---\n"
                f"Nombre: {r['nombre']}\n"
                f"Estado: {r['estado']}\n"
                f"{grafo_str}{resumen_str}"
                f"Contenido:\n{r['texto'][:2000]}\n"
            )

        contexto = "\n".join(contexto_parts)

        # Incluir glosario si hay términos relevantes
        if glosario_ctx:
            contexto = glosario_ctx + "\n\n" + contexto

        # Incluir alertas de vencimiento si la pregunta es sobre vigencia
        if any(w in question.lower() for w in ["venc", "vigente", "caduc", "actual", "vigencia"]):
            alertas = self.alertas_vencimiento(solo_vencidos=True)
            if alertas:
                alertas_str = "\nALERTAS DE VENCIMIENTO:\n"
                for a in alertas[:5]:
                    alertas_str += f"- {a['codigo']}: {a['estado_alerta']} ({a['dias_restantes']} días) - {a['nombre'][:50]}\n"
                contexto = alertas_str + "\n" + contexto

        # ── Multi-turn context: incluir contexto de turnos anteriores ──
        if _HAS_AGENTIC and self.multi_turn:
            try:
                multi_turn_ctx = self.multi_turn.build_multi_turn_context(
                    getattr(self, '_current_session_id', 'default'), question
                )
                if multi_turn_ctx:
                    contexto = multi_turn_ctx + "\n\n" + contexto
            except Exception as e:
                print(f"  [GraphRAG] Multi-turn context error (no critico): {e}")

        # ── Long-term memory: incluir preferencias e intereses del usuario ──
        if _HAS_AGENTIC and self.long_term_memory:
            try:
                user_ctx = self.long_term_memory.get_context_for_user(
                    getattr(self, '_current_user_id', 'default')
                )
                if user_ctx:
                    contexto = user_ctx + "\n\n" + contexto
            except Exception as e:
                print(f"  [GraphRAG] Long-term memory context error (no critico): {e}")

        system_prompt = SYSTEM_PROMPT_CALIDAD

        # Cargar skills relevantes a la pregunta
        skills_ctx = _load_relevant_skills(question)
        skills_activados = []
        if skills_ctx:
            system_prompt = system_prompt + skills_ctx
            skills_activados = [s.strip() for s in skills_ctx.split("=== SKILL:")[1:]]
            skills_activados = [s.split("===")[0].strip() for s in skills_activados]
            print(f"  [GraphRAG] Skills activados: {len(skills_activados)}")
            self.obs.track_skills(trace_id, skills_activados)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Contexto:\n{contexto}\n\nPregunta: {question}"},
        ]

        if self.history:
            messages = [messages[0]] + self.history[-6:] + [messages[1]]

        print(f"  [GraphRAG] Consultando LLM...")
        t_llm_start = time.time()
        try:
            response, provider_used = self.llm.chat(
                messages=messages,
                temperature=0.2,
            )
            if provider_used != "mistral":
                print(f"  [GraphRAG] Respuesta via {provider_used} (fallback)")
        except RuntimeError as e:
            print(f"  [GraphRAG] Error: todos los proveedores fallaron")
            raise
        t_llm_end = time.time()
        answer = response.choices[0].message.content

        # ── Guardrail de salida: governance (PII, credenciales) ──
        if self.governance:
            ok_out, reason_out = self.governance.validate_output(answer)
            if not ok_out:
                answer = self.governance.safe_response(reason_out)
                print(f"  [GraphRAG] Salida bloqueada por governance: {reason_out}")
            else:
                answer = self.governance._filter_pii(answer)

        # ── Content moderation de salida ──
        if self.moderation:
            mod_out = self.moderation.moderate(answer)
            if mod_out.get("blocked"):
                answer = self.governance.safe_response("content_moderation_output") if self.governance else "Respuesta bloqueada por content moderation."
                print(f"  [GraphRAG] Salida bloqueada por moderation")
            else:
                answer = mod_out.get("filtered_text", answer)

        # ── Hallucination Detection ──
        if resultados:
            hallucination_result = self._detect_hallucination(answer, resultados)
            if hallucination_result["hallucination"]:
                print(f"  [GraphRAG] Hallucination detectada: {hallucination_result['claims_no_sustentados']} claims no sustentados")
                # Agregar advertencia a la respuesta
                answer += f"\n\n---\n*Confianza: {confidence['nivel']} | Claims verificados: {hallucination_result['claims_verificados']} | Sustentados: {hallucination_result['claims_verificados'] - hallucination_result['claims_no_sustentados']}*"
            else:
                print(f"  [GraphRAG] Hallucination check OK: {hallucination_result['claims_verificados']} claims verificados")
                answer += f"\n\n---\n*Confianza: {confidence['nivel']} | Claims verificados: {hallucination_result['claims_verificados']}*"
        else:
            answer += f"\n\n---\n*Confianza: {confidence['nivel']}*"

        # ── DLP (Data Loss Prevention): enmascarar info sensible en la salida ──
        if _HAS_CALIDAD_SEG:
            try:
                answer, dlp_detections = apply_dlp(answer)
                if dlp_detections:
                    print(f"  [GraphRAG] DLP: {len(dlp_detections)} detecciones de info sensible enmascaradas")
            except Exception as e:
                print(f"  [GraphRAG] DLP error (no critico): {e}")

        # ── Bias Detection: detectar sesgos en la respuesta ──
        if _HAS_MEJORAS_EXTRAS:
            try:
                bias_result = check_response_bias(answer, self.client)
                if bias_result["has_bias"]:
                    print(f"  [GraphRAG] Bias detectado: score={bias_result['bias_score']:.2f} categorias={list(bias_result['categories'].keys())}")
                    save_bias_check(self.conn, getattr(self, '_current_session_id', 'default'),
                                    answer, bias_result)
                    # Si el sesgo es alto, usar la version neutralizada
                    if bias_result["bias_score"] >= 0.5 and bias_result.get("neutral_suggestion"):
                        answer = bias_result["neutral_suggestion"]
                else:
                    save_bias_check(self.conn, getattr(self, '_current_session_id', 'default'),
                                    answer, bias_result)
            except Exception as e:
                print(f"  [GraphRAG] Bias detection error (no critico): {e}")

        # ── Citation Verification: verificar que las citas existen ──
        if _HAS_CALIDAD_SEG and resultados:
            try:
                cit_result = verify_citations(answer, self.conn)
                if not cit_result["all_valid"]:
                    print(f"  [GraphRAG] Citation check: {len(cit_result['not_found'])} citas no encontradas")
                else:
                    print(f"  [GraphRAG] Citation check OK: {cit_result['total_citations']} citas verificadas")
            except Exception as e:
                print(f"  [GraphRAG] Citation verification error (no critico): {e}")

        # ── Agregar citas si faltan ──
        if _HAS_CALIDAD_SEG and resultados:
            try:
                answer = add_citations_if_missing(answer, resultados)
            except Exception as e:
                print(f"  [GraphRAG] Add citations error (no critico): {e}")

        # ── LLM-as-Judge: evaluar calidad de la respuesta ──
        if _HAS_EVALUACION:
            try:
                eval_result = llm_as_judge(question, answer, contexto, self.client)
                print(f"  [GraphRAG] LLM-as-Judge: overall={eval_result['overall']:.1f}/10 (method={eval_result['method']})")
                save_evaluation(self.conn, getattr(self, '_current_session_id', 'default'),
                                question, answer, eval_result)
            except Exception as e:
                print(f"  [GraphRAG] LLM-as-Judge error (no critico): {e}")

        # ── RAGAS Metrics ──
        if _HAS_EVALUACION and resultados:
            try:
                ragas = calculate_ragas(question, answer, resultados, self.client)
                print(f"  [GraphRAG] RAGAS: faithfulness={ragas['faithfulness']:.2f} relevancy={ragas['answer_relevancy']:.2f} precision={ragas['context_precision']:.2f} recall={ragas['context_recall']:.2f}")
                save_ragas(self.conn, getattr(self, '_current_session_id', 'default'),
                           question, ragas)
            except Exception as e:
                print(f"  [GraphRAG] RAGAS error (no critico): {e}")

        # ── Latency recording ──
        if _HAS_OBS_ADV:
            try:
                record_latency("ask_total", (time.time() - t_llm_start) * 1000, self.conn)
            except Exception as e:
                print(f"  [GraphRAG] Latency recording error (no critico): {e}")

        # ── Multi-turn reasoning: actualizar contexto ──
        if _HAS_AGENTIC and self.multi_turn:
            try:
                resolved = self.multi_turn.track_resolved_topics(question, answer)
                self.multi_turn.update_context(
                    getattr(self, '_current_session_id', 'default'),
                    len(self.history) // 2 + 1,
                    question, answer,
                    {"resolved_topics": resolved}
                )
            except Exception as e:
                print(f"  [GraphRAG] Multi-turn error (no critico): {e}")

        # ── Long-term memory: track interests ──
        if _HAS_AGENTIC and self.long_term_memory:
            try:
                user_id = getattr(self, '_current_user_id', 'default')
                topics = self.multi_turn.track_resolved_topics(question, answer) if self.multi_turn else []
                for topic in topics:
                    self.long_term_memory.track_interest(user_id, topic)
            except Exception as e:
                print(f"  [GraphRAG] Long-term memory error (no critico): {e}")

        # ── Explicabilidad: agregar explicacion del retrieval ──
        if _HAS_AGENTIC and self.explainer and resultados:
            try:
                explanation = self.explainer.explain_retrieval(question, resultados)
                # Solo agregar si la respuesta no es muy larga
                if len(answer) < 3000:
                    answer += "\n\n" + self.explainer.format_explanation(explanation)
            except Exception as e:
                print(f"  [GraphRAG] Explicabilidad error (no critico): {e}")

        # Trackear llamada LLM
        prompt_tokens = response.usage.prompt_tokens if response.usage else 0
        completion_tokens = response.usage.completion_tokens if response.usage else 0
        self.obs.track_llm_call(
            trace_id, provider_used, "chat_completion",
            prompt_tokens, completion_tokens,
            t_llm_end - t_llm_start
        )

        self.history.append({"role": "user", "content": question})
        self.history.append({"role": "assistant", "content": answer})

        # ── Guardar en cache semantico ──
        self._guardar_cache_semantico(question, answer, provider_used)
        if self.memoria:
            cache_type = "procedimiento" if any(
                kw in question.lower()
                for kw in ["procedimiento", "pafa", "peop", "pgc", "pco", "pwhs", "pcp"]
            ) else "general"
            self.memoria.cache_set(
                question, answer,
                modelo=provider_used,
                tokens_input=prompt_tokens,
                tokens_output=completion_tokens,
                cache_type=cache_type,
            )

        # Cerrar traza
        self.obs.end_trace(trace_id, answer)

        # ── Actualizar FAQ existente si la respuesta fue generada y hay FAQ stale ──
        try:
            if answer and len(answer) > 20:
                self._actualizar_faq_si_existe(question, answer, resultados)
        except Exception as e:
            print(f"  [GraphRAG] Error actualizando FAQ stale: {e}")

        return answer, resultados

    def ask_stream(self, question: str, modo_rapido: bool | None = None):
        """Version streaming de ask(). Genera tokens uno a uno.

        Yields:
            (token_text, provider_used, resultados)
            El primer yield tiene token="" y provider="" con los resultados.
            Los siguientes yields tienen tokens de texto.
            El ultimo yield tiene token=None para senalar fin.
        """
        # ── Guardrail de entrada: governance ──
        if self.governance:
            ok, reason = self.governance.validate_input(question)
            if not ok:
                safe = self.governance.safe_response(reason)
                print(f"  [GraphRAG] Entrada bloqueada por governance: {reason}")
                yield safe, "governance", []
                return

        # ── Content moderation de entrada ──
        if self.moderation:
            mod_result = self.moderation.moderate(question)
            if mod_result.get("blocked"):
                safe = (
                    f"Tu mensaje fue bloqueado por content moderation. "
                    f"Categoria: {mod_result.get('category', 'N/A')}. "
                    f"Por favor, mantén la conversación enfocada en calidad HSEQ."
                )
                print(f"  [GraphRAG] Entrada bloqueada por moderation: {mod_result.get('category')}")
                yield safe, "moderation", []
                return
            question = mod_result.get("filtered_text", question)

        # ── FAQ precargada: respuestas instantáneas para preguntas frecuentes ──
        faq = self.buscar_faq_precargada(question, threshold=0.90)
        if faq:
            print(f"  [GraphRAG] FAQ HIT ({faq['match']}): respuesta precargada")
            yield "", "faq", []
            yield faq["respuesta"], "faq", []
            yield None, "faq", []
            return

        # ── Cache semantico: buscar si ya respondimos esta pregunta ──
        cached = self._buscar_cache_semantico(question, threshold=0.92)
        if not cached and self.memoria:
            cached = self.memoria.cache_semantic_lookup(question)
        if cached:
            print(f"  [GraphRAG] Cache HIT (match: {cached.get('match_type', 'exact')}, sim: {cached.get('similarity', 'N/A')})")
            yield "", "cache", []
            yield cached["respuesta"], "cache", []
            yield None, "cache", []
            return

        # ── Self-RAG: determinar si necesita retrieval ──
        needs_retrieval = self._needs_retrieval(question)

        trace_id = self.obs.start_trace(question)

        if not needs_retrieval:
            print(f"\n  [GraphRAG] Self-RAG: respondiendo sin retrieval")
            confidence = {"nivel": "alto", "score": 1.0, "razon": "Respuesta directa"}
            resultados = []
        else:
            print(f"\n  [GraphRAG] Recuperando documentos...")
            t_rec_start = time.time()
            resultados = self.retrieve(question, top_k=TOP_K_FINAL * 2, modo_rapido=modo_rapido)
            print(f"  [GraphRAG] Retrieve completo: {len(resultados)} resultados ({time.time()-t_rec_start:.2f}s)")

            n_before = len(resultados)
            resultados = self._filtrar_obsoletos(resultados)
            n_obsoletos = n_before - len(resultados)
            resultados = resultados[:TOP_K_FINAL]
            t_rec_end = time.time()

            self.obs.track_retrieval(
                trace_id, question, len(resultados), n_obsoletos,
                t_rec_end - t_rec_start
            )

            print(f"  [GraphRAG] {len(resultados)} documentos vigentes recuperados:")
            for i, r in enumerate(resultados):
                print(f"    {i+1}. {r['codigo']} (total={r['score_total']:.3f} "
                      f"sem={r['score_semantico']:.2f} lex={r['score_lexical']:.2f} "
                      f"grafo={r['score_grafo']:.2f}) - {r['nombre'][:50]}")

            # ── Confidence Score ──
            confidence = self._calculate_confidence(resultados)
            print(f"  [GraphRAG] Confidence: {confidence['nivel']} ({confidence['score']:.3f})")

        glosario_ctx = glosario_para_contexto(question)

        contexto_parts = []
        for i, r in enumerate(resultados):
            grafo = r.get("grafo", {})
            grafo_str = ""
            if grafo.get("procesos"):
                grafo_str += f"Proceso: {', '.join(grafo['procesos'])}\n"
            if grafo.get("temas"):
                grafo_str += f"Tema: {', '.join(grafo['temas'])}\n"
            if grafo.get("docs_relacionados"):
                rels = [f"{d['codigo']} ({d['relation']})" for d in grafo['docs_relacionados'][:3]]
                grafo_str += f"Documentos relacionados: {', '.join(rels)}\n"

            resumen = self.get_resumen(r["codigo"])
            resumen_str = ""
            if resumen and resumen.get("resumen"):
                resumen_str = f"Resumen ejecutivo: {resumen['resumen']}\n"
                if resumen.get("proposito"):
                    resumen_str += f"Propósito: {resumen['proposito']}\n"
                if resumen.get("alcance"):
                    resumen_str += f"Alcance: {resumen['alcance']}\n"
                if resumen.get("palabras_clave"):
                    resumen_str += f"Palabras clave: {resumen['palabras_clave']}\n"

            contexto_parts.append(
                f"--- Documento {i+1}: {r['codigo']} ---\n"
                f"Nombre: {r['nombre']}\n"
                f"Estado: {r['estado']}\n"
                f"{grafo_str}{resumen_str}"
                f"Contenido:\n{r['texto'][:2000]}\n"
            )

        contexto = "\n".join(contexto_parts)

        if glosario_ctx:
            contexto = glosario_ctx + "\n\n" + contexto

        if any(w in question.lower() for w in ["venc", "vigente", "caduc", "actual", "vigencia"]):
            alertas = self.alertas_vencimiento(solo_vencidos=True)
            if alertas:
                alertas_str = "\nALERTAS DE VENCIMIENTO:\n"
                for a in alertas[:5]:
                    alertas_str += f"- {a['codigo']}: {a['estado_alerta']} ({a['dias_restantes']} días) - {a['nombre'][:50]}\n"
                contexto = alertas_str + "\n" + contexto

        system_prompt = SYSTEM_PROMPT_CALIDAD

        skills_ctx = _load_relevant_skills(question)
        skills_activados = []
        if skills_ctx:
            system_prompt = system_prompt + skills_ctx
            skills_activados = [s.strip() for s in skills_ctx.split("=== SKILL:")[1:]]
            skills_activados = [s.split("===")[0].strip() for s in skills_activados]
            print(f"  [GraphRAG] Skills activados: {len(skills_activados)}")
            self.obs.track_skills(trace_id, skills_activados)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Contexto:\n{contexto}\n\nPregunta: {question}"},
        ]

        if self.history:
            messages = [messages[0]] + self.history[-6:] + [messages[1]]

        print(f"  [GraphRAG] Consultando LLM (streaming)...")
        t_llm_start = time.time()

        # Yield inicial con los resultados (para que la UI los muestre)
        yield "", "", resultados

        full_answer = ""
        provider_used = ""
        try:
            for token, provider in self.llm.chat_stream(
                messages=messages,
                temperature=0.2,
            ):
                provider_used = provider
                full_answer += token
                yield token, provider, None
        except RuntimeError as e:
            print(f"  [GraphRAG] Error: todos los proveedores fallaron")
            raise

        t_llm_end = time.time()

        # ── Guardrail de salida: governance (PII, credenciales) ──
        # Nota: en streaming, el filtrado se hace al final sobre la respuesta completa
        if self.governance:
            ok_out, reason_out = self.governance.validate_output(full_answer)
            if not ok_out:
                full_answer = self.governance.safe_response(reason_out)
                print(f"  [GraphRAG] Salida bloqueada por governance: {reason_out}")
            else:
                full_answer = self.governance._filter_pii(full_answer)

        # ── Content moderation de salida ──
        if self.moderation:
            mod_out = self.moderation.moderate(full_answer)
            if mod_out.get("blocked"):
                full_answer = self.governance.safe_response("content_moderation_output") if self.governance else "Respuesta bloqueada por content moderation."
                print(f"  [GraphRAG] Salida bloqueada por moderation")
            else:
                full_answer = mod_out.get("filtered_text", full_answer)

        self.history.append({"role": "user", "content": question})
        self.history.append({"role": "assistant", "content": full_answer})

        # ── Hallucination Detection (streaming) ──
        if resultados:
            hallucination_result = self._detect_hallucination(full_answer, resultados)
            if hallucination_result["hallucination"]:
                print(f"  [GraphRAG] Hallucination detectada: {hallucination_result['claims_no_sustentados']} claims no sustentados")
                yield f"\n\n---\n*Confianza: {confidence['nivel']} | Claims verificados: {hallucination_result['claims_verificados']} | Sustentados: {hallucination_result['claims_verificados'] - hallucination_result['claims_no_sustentados']}*", provider_used, None
            else:
                print(f"  [GraphRAG] Hallucination check OK: {hallucination_result['claims_verificados']} claims verificados")
                yield f"\n\n---\n*Confianza: {confidence['nivel']} | Claims verificados: {hallucination_result['claims_verificados']}*", provider_used, None
        else:
            yield f"\n\n---\n*Confianza: {confidence['nivel']}*", provider_used, None

        # ── Guardar en cache semantico ──
        self._guardar_cache_semantico(question, full_answer, provider_used)
        if self.memoria:
            cache_type = "procedimiento" if any(
                kw in question.lower()
                for kw in ["procedimiento", "pafa", "peop", "pgc", "pco", "pwhs", "pcp"]
            ) else "general"
            self.memoria.cache_set(
                question, full_answer,
                modelo=provider_used,
                tokens_input=0, tokens_output=0,
                cache_type=cache_type,
            )

        # ── Registrar uso para indicadores ──
        self.registrar_uso(
            getattr(self, '_current_username', 'anon'),
            getattr(self, '_current_role', 'usuario'),
            getattr(self, '_current_area', ''),
            question, resultados, provider_used,
            cached=provider_used == "cache"
        )

        self.obs.end_trace(trace_id, full_answer)

        # ── Latency recording (observabilidad avanzada) ──
        if _HAS_OBS_ADV:
            try:
                total_ms = (time.time() - t_rec_start) * 1000 if needs_retrieval else 0
                record_latency("ask_stream_total", total_ms, self.conn)
                record_latency("ask_stream_llm", (t_llm_end - t_llm_start) * 1000, self.conn)
                if needs_retrieval:
                    record_latency("ask_stream_retrieval", (t_rec_end - t_rec_start) * 1000, self.conn)
            except Exception as e:
                print(f"  [GraphRAG] Latency recording error (stream, no critico): {e}")

        # Senal de fin
        yield None, provider_used, None

        # ── Actualizar FAQ existente si la respuesta fue generada ──
        try:
            if full_answer and len(full_answer) > 20:
                self._actualizar_faq_si_existe(question, full_answer, resultados)
        except Exception as e:
            print(f"  [GraphRAG] Error actualizando FAQ stale (stream): {e}")

    # ──────────────────────────────────────────────
    # Feedback del usuario
    # ──────────────────────────────────────────────

    def guardar_feedback(self, pregunta: str, respuesta: str, feedback: str,
                         comentario: str = "", resultados: list[dict] | None = None,
                         fuente: str = "") -> bool:
        """Guarda feedback del usuario (thumbs up/down) en SQLite.
        feedback: 'positive' o 'negative'
        Actualiza contadores de FAQ y estadisticas de documentos para reranking.
        """
        try:
            import hashlib, math
            from datetime import datetime

            # 1. Guardar feedback general del usuario
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS feedback_usuario (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pregunta TEXT,
                    respuesta TEXT,
                    feedback TEXT,
                    comentario TEXT,
                    timestamp TEXT DEFAULT (datetime('now', 'localtime'))
                )
            """)
            self.conn.execute("""
                INSERT INTO feedback_usuario (pregunta, respuesta, feedback, comentario)
                VALUES (?, ?, ?, ?)
            """, (pregunta[:500], respuesta[:2000], feedback, comentario[:500]))

            # 2. Actualizar contadores de FAQ si la respuesta proviene de una FAQ
            if fuente == "faq" or True:
                # Buscar FAQ por pregunta exacta o por respuesta
                q_norm = re.sub(r"\s+", " ", pregunta.strip().lower())
                qhash = hashlib.sha256(q_norm.encode("utf-8")).hexdigest()[:32]
                faq_row = self.conn.execute(
                    "SELECT id FROM faq_precargadas WHERE pregunta_hash = ?",
                    (qhash,)
                ).fetchone()
                if not faq_row and respuesta:
                    faq_row = self.conn.execute(
                        "SELECT id FROM faq_precargadas WHERE respuesta = ? LIMIT 1",
                        (respuesta[:2000],)
                    ).fetchone()

                if faq_row:
                    faq_id = faq_row[0]
                    col = "feedback_positivo" if feedback == "positive" else "feedback_negativo"
                    self.conn.execute(f"""
                        UPDATE faq_precargadas
                        SET {col} = {col} + 1,
                            activa = CASE
                                WHEN feedback_negativo + CASE ? WHEN 'negative' THEN 1 ELSE 0 END >
                                     feedback_positivo + CASE ? WHEN 'positive' THEN 1 ELSE 0 END
                                THEN 0 ELSE activa END
                        WHERE id = ?
                    """, (feedback, feedback, faq_id))
                    self.conn.commit()
                    print(f"  [GraphRAG] Feedback {feedback} registrado para FAQ id={faq_id}")

            # 3. Guardar feedback por documento para reranking
            if resultados:
                for r in resultados:
                    codigo = r.get("codigo")
                    if not codigo:
                        continue
                    self.conn.execute("""
                        INSERT INTO feedback_documentos (pregunta, respuesta, codigo, feedback)
                        VALUES (?, ?, ?, ?)
                    """, (pregunta[:500], respuesta[:2000], codigo, feedback))

                    # Upsert estadisticas agregadas por documento
                    self.conn.execute("""
                        INSERT INTO doc_feedback_stats (codigo, positivo, negativo, total, score_boost, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(codigo) DO UPDATE SET
                            positivo = positivo + excluded.positivo,
                            negativo = negativo + excluded.negativo,
                            total = total + excluded.total,
                            updated_at = excluded.updated_at
                    """, (
                        codigo,
                        1 if feedback == "positive" else 0,
                        1 if feedback == "negative" else 0,
                        1,
                        0.0,
                        datetime.now().isoformat()
                    ))

                # Recalcular score_boost para documentos afectados
                for r in resultados:
                    codigo = r.get("codigo")
                    if not codigo:
                        continue
                    stats = self.conn.execute(
                        "SELECT positivo, negativo FROM doc_feedback_stats WHERE codigo = ?", (codigo,)
                    ).fetchone()
                    if stats:
                        pos, neg = stats
                        boost = math.log((pos + 1.0) / (neg + 1.0))
                        boost = max(-0.5, min(0.5, boost))  # limitar rango
                        self.conn.execute(
                            "UPDATE doc_feedback_stats SET score_boost = ? WHERE codigo = ?",
                            (boost, codigo)
                        )

            self.conn.commit()
            return True
        except Exception as e:
            print(f"  [GraphRAG] Error guardando feedback: {e}")
            return False

    def obtener_feedback_stats(self) -> dict:
        """Obtiene estadisticas de feedback del usuario."""
        try:
            rows = self.conn.execute("""
                SELECT feedback, COUNT(*) as count
                FROM feedback_usuario
                GROUP BY feedback
            """).fetchall()
            stats = {"positive": 0, "negative": 0, "total": 0}
            for row in rows:
                fb, count = row
                stats[fb] = count
                stats["total"] += count
            return stats
        except Exception:
            return {"positive": 0, "negative": 0, "total": 0}

    # ──────────────────────────────────────────────
    # Chat con historial persistente (SQLite)
    # ──────────────────────────────────────────────

    def init_chat_history_table(self):
        """Crea la tabla de historial de chat si no existe."""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_historial (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                documentos_json TEXT,
                provider TEXT,
                confidence TEXT,
                hallucination TEXT,
                timestamp TEXT DEFAULT (datetime('now', 'localtime'))
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_chat_session
            ON chat_historial (session_id, timestamp)
        """)
        self.conn.commit()

    def guardar_mensaje_chat(self, session_id: str, role: str, content: str,
                             documentos: list = None, provider: str = "",
                             confidence: dict = None, hallucination: dict = None) -> bool:
        """Guarda un mensaje del chat en el historial persistente."""
        import json as _json
        try:
            self.init_chat_history_table()
            docs_json = _json.dumps(documentos, ensure_ascii=False) if documentos else None
            conf_json = _json.dumps(confidence, ensure_ascii=False) if confidence else None
            hall_json = _json.dumps(hallucination, ensure_ascii=False) if hallucination else None
            self.conn.execute("""
                INSERT INTO chat_historial
                (session_id, role, content, documentos_json, provider, confidence, hallucination)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (session_id, role, content[:5000], docs_json, provider, conf_json, hall_json))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"  [GraphRAG] Error guardando mensaje chat: {e}")
            return False

    def cargar_historial_chat(self, session_id: str, limit: int = 50) -> list[dict]:
        """Carga el historial de chat de una sesion."""
        import json as _json
        try:
            self.init_chat_history_table()
            rows = self.conn.execute("""
                SELECT role, content, documentos_json, provider, confidence, hallucination, timestamp
                FROM chat_historial
                WHERE session_id = ?
                ORDER BY id ASC
                LIMIT ?
            """, (session_id, limit)).fetchall()

            mensajes = []
            for row in rows:
                msg = {
                    "role": row[0],
                    "content": row[1],
                    "timestamp": row[6],
                }
                if row[2]:
                    try:
                        msg["documentos"] = _json.loads(row[2])
                    except Exception:
                        pass
                if row[3]:
                    msg["provider"] = row[3]
                if row[4]:
                    try:
                        msg["confidence"] = _json.loads(row[4])
                    except Exception:
                        pass
                if row[5]:
                    try:
                        msg["hallucination"] = _json.loads(row[5])
                    except Exception:
                        pass
                mensajes.append(msg)
            return mensajes
        except Exception as e:
            print(f"  [GraphRAG] Error cargando historial: {e}")
            return []

    def listar_sesiones_chat(self, limit: int = 20) -> list[dict]:
        """Lista todas las sesiones de chat con su ultimo mensaje."""
        try:
            self.init_chat_history_table()
            rows = self.conn.execute("""
                SELECT session_id,
                       COUNT(*) as msg_count,
                       MIN(timestamp) as primera,
                       MAX(timestamp) as ultima,
                       (SELECT content FROM chat_historial ch2
                        WHERE ch2.session_id = chat_historial.session_id
                        AND ch2.role = 'user'
                        ORDER BY ch2.id ASC LIMIT 1) as primera_pregunta
                FROM chat_historial
                GROUP BY session_id
                ORDER BY ultima DESC
                LIMIT ?
            """, (limit,)).fetchall()

            sesiones = []
            for row in rows:
                sesiones.append({
                    "session_id": row[0],
                    "msg_count": row[1],
                    "primera": row[2],
                    "ultima": row[3],
                    "primera_pregunta": (row[4] or "")[:80],
                })
            return sesiones
        except Exception as e:
            print(f"  [GraphRAG] Error listando sesiones: {e}")
            return []

    def eliminar_sesion_chat(self, session_id: str) -> bool:
        """Elimina todos los mensajes de una sesion."""
        try:
            self.conn.execute("DELETE FROM chat_historial WHERE session_id = ?", (session_id,))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"  [GraphRAG] Error eliminando sesion: {e}")
            return False

    # ──────────────────────────────────────────────
    # Audit trail completo
    # ──────────────────────────────────────────────

    def init_audit_table(self):
        """Crea la tabla de audit trail enriquecido."""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_trail (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT DEFAULT (datetime('now', 'localtime')),
                session_id TEXT,
                user_id TEXT,
                pregunta TEXT,
                respuesta TEXT,
                documentos_json TEXT,
                provider TEXT,
                confidence_nivel TEXT,
                confidence_score REAL,
                hallucination_score REAL,
                hallucination_claims INTEGER,
                retrieval_time REAL,
                llm_time REAL,
                total_time REAL,
                tokens_input INTEGER,
                tokens_output INTEGER,
                cost_usd REAL,
                blocked BOOLEAN DEFAULT 0,
                block_reason TEXT,
                feedback TEXT
            )
        """)
        self.conn.commit()

    def log_audit(self, session_id: str, pregunta: str, respuesta: str,
                  documentos: list = None, provider: str = "",
                  confidence: dict = None, hallucination: dict = None,
                  retrieval_time: float = 0, llm_time: float = 0,
                  total_time: float = 0, tokens_input: int = 0,
                  tokens_output: int = 0, cost_usd: float = 0,
                  blocked: bool = False, block_reason: str = "",
                  user_id: str = "default") -> bool:
        """Registra una interaccion completa en el audit trail."""
        import json as _json
        try:
            self.init_audit_table()
            docs_json = _json.dumps(
                [{"codigo": d.get("codigo", ""), "nombre": d.get("nombre", "")[:80],
                  "score": d.get("score_total", d.get("score", 0))}
                 for d in (documentos or [])],
                ensure_ascii=False
            )
            conf_nivel = confidence.get("nivel", "") if confidence else ""
            conf_score = confidence.get("score", 0.0) if confidence else 0.0
            hall_score = hallucination.get("score", 1.0) if hallucination else 1.0
            hall_claims = hallucination.get("claims_verificados", 0) if hallucination else 0

            self.conn.execute("""
                INSERT INTO audit_trail
                (session_id, user_id, pregunta, respuesta, documentos_json, provider,
                 confidence_nivel, confidence_score, hallucination_score, hallucination_claims,
                 retrieval_time, llm_time, total_time, tokens_input, tokens_output,
                 cost_usd, blocked, block_reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (session_id, user_id, pregunta[:1000], respuesta[:3000], docs_json,
                  provider, conf_nivel, conf_score, hall_score, hall_claims,
                  retrieval_time, llm_time, total_time, tokens_input, tokens_output,
                  cost_usd, blocked, block_reason))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"  [GraphRAG] Error audit trail: {e}")
            return False

    def obtener_audit_trail(self, limit: int = 50, session_id: str = "") -> list[dict]:
        """Obtiene registros del audit trail."""
        import json as _json
        try:
            self.init_audit_table()
            if session_id:
                rows = self.conn.execute("""
                    SELECT timestamp, session_id, user_id, pregunta, respuesta,
                           documentos_json, provider, confidence_nivel, confidence_score,
                           hallucination_score, hallucination_claims,
                           retrieval_time, llm_time, total_time,
                           tokens_input, tokens_output, cost_usd, blocked, block_reason
                    FROM audit_trail
                    WHERE session_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                """, (session_id, limit)).fetchall()
            else:
                rows = self.conn.execute("""
                    SELECT timestamp, session_id, user_id, pregunta, respuesta,
                           documentos_json, provider, confidence_nivel, confidence_score,
                           hallucination_score, hallucination_claims,
                           retrieval_time, llm_time, total_time,
                           tokens_input, tokens_output, cost_usd, blocked, block_reason
                    FROM audit_trail
                    ORDER BY id DESC
                    LIMIT ?
                """, (limit,)).fetchall()

            registros = []
            for row in rows:
                reg = {
                    "timestamp": row[0], "session_id": row[1], "user_id": row[2],
                    "pregunta": row[3], "respuesta": row[4],
                    "provider": row[6], "confidence_nivel": row[7],
                    "confidence_score": row[8], "hallucination_score": row[9],
                    "hallucination_claims": row[10],
                    "retrieval_time": row[11], "llm_time": row[12], "total_time": row[13],
                    "tokens_input": row[14], "tokens_output": row[15],
                    "cost_usd": row[16], "blocked": bool(row[17]), "block_reason": row[18],
                }
                if row[5]:
                    try:
                        reg["documentos"] = _json.loads(row[5])
                    except Exception:
                        reg["documentos"] = []
                registros.append(reg)
            return registros
        except Exception as e:
            print(f"  [GraphRAG] Error obteniendo audit: {e}")
            return []

    # ──────────────────────────────────────────────
    # Evaluacion automatica de respuestas (RAGAS-like)
    # ──────────────────────────────────────────────

    def evaluar_respuesta(self, pregunta: str, respuesta: str, documentos: list[dict]) -> dict:
        """Evaluacion automatica de calidad de respuesta (RAGAS-like).
        Metricas:
        - faithfulness: la respuesta esta sustentada en los documentos?
        - relevance: la respuesta es relevante a la pregunta?
        - context_recall: los documentos cubren la informacion necesaria?
        - context_precision: los documentos son precisos (no ruido)?
        Retorna: {faithfulness, relevance, context_recall, context_precision, score_total}
        """
        if not documentos or not respuesta:
            return {
                "faithfulness": 0.0, "relevance": 0.0,
                "context_recall": 0.0, "context_precision": 0.0,
                "score_total": 0.0, "evaluacion": "sin_datos",
            }

        texto_docs = " ".join(d.get("texto", d.get("content", "")) for d in documentos).lower()
        respuesta_lower = respuesta.lower()
        pregunta_lower = pregunta.lower()

        # 1. Faithfulness: % de palabras de la respuesta que estan en los documentos
        resp_tokens = re.findall(r'[a-záéíóúñ]{4,}', respuesta_lower)
        resp_tokens = [t for t in resp_tokens if t not in {
            "este", "esta", "estos", "estas", "para", "como", "pero", "solo",
            "tambien", "ademas", "segun", "cuando", "donde", "porque", "entonces"
        }]
        if resp_tokens:
            faith_matches = sum(1 for t in resp_tokens if t in texto_docs)
            faithfulness = faith_matches / len(resp_tokens)
        else:
            faithfulness = 0.5

        # 2. Relevance: overlap de keywords entre pregunta y respuesta
        preg_tokens = set(re.findall(r'[a-záéíóúñ]{4,}', pregunta_lower))
        preg_tokens = {t for t in preg_tokens if t not in {"este", "esta", "para", "como", "pero"}}
        resp_token_set = set(re.findall(r'[a-záéíóúñ]{4,}', respuesta_lower))
        if preg_tokens:
            relevance = len(preg_tokens & resp_token_set) / len(preg_tokens)
        else:
            relevance = 0.5

        # 3. Context recall: % de keywords de la pregunta cubiertas por los documentos
        if preg_tokens:
            context_recall = sum(1 for t in preg_tokens if t in texto_docs) / len(preg_tokens)
        else:
            context_recall = 0.5

        # 4. Context precision: % de documentos recuperados que comparten keywords con la pregunta
        docs_relevantes = 0
        for d in documentos:
            doc_text = d.get("texto", d.get("content", "")).lower()
            doc_tokens = set(re.findall(r'[a-záéíóúñ]{4,}', doc_text))
            if preg_tokens & doc_tokens:
                docs_relevantes += 1
        context_precision = docs_relevantes / len(documentos) if documentos else 0

        # Score total (promedio ponderado)
        score_total = (
            0.35 * faithfulness
            + 0.25 * relevance
            + 0.25 * context_recall
            + 0.15 * context_precision
        )

        # Evaluacion cualitativa
        if score_total > 0.7:
            evaluacion = "excelente"
        elif score_total > 0.5:
            evaluacion = "buena"
        elif score_total > 0.3:
            evaluacion = "regular"
        else:
            evaluacion = "deficiente"

        return {
            "faithfulness": round(faithfulness, 3),
            "relevance": round(relevance, 3),
            "context_recall": round(context_recall, 3),
            "context_precision": round(context_precision, 3),
            "score_total": round(score_total, 3),
            "evaluacion": evaluacion,
            "docs_relevantes": docs_relevantes,
            "docs_total": len(documentos),
        }

    # ──────────────────────────────────────────────
    # Citation linking: enriquecer respuesta con citas clickeables
    # ──────────────────────────────────────────────

    def enriquecer_citas(self, respuesta: str, documentos: list[dict]) -> str:
        """Convierte codigos de documentos en la respuesta en citas clickeables.
        Ej: 'Segun PGC-16-15...' -> 'Segun [PGC-16-15](#doc-PGC-16-15)...'
        """
        if not documentos:
            return respuesta

        codigos = {d.get("codigo", "") for d in documentos if d.get("codigo")}
        enriquecida = respuesta

        for codigo in codigos:
            if codigo and codigo in enriquecida:
                # Reemplazar el codigo por un link markdown
                link = f"[{codigo}](#{codigo})"
                enriquecida = enriquecida.replace(codigo, link, 1)  # solo la primera ocurrencia

        return enriquecida

    # ──────────────────────────────────────────────
    # Exploración del grafo
    # ──────────────────────────────────────────────

    # ──────────────────────────────────────────────
    # Comparador de versiones de documentos
    # ──────────────────────────────────────────────

    def buscar_versiones(self, nombre: str = "", proceso: str = "") -> list[dict]:
        """Busca documentos que tienen multiples versiones (mismo nombre, diferentes codigos).
        Retorna grupos de versiones.
        """
        if nombre:
            rows = self.conn.execute("""
                SELECT codigo, nombre, estado, estado_desc, proceso_nom,
                       tipo_documento, fecha_elaboracion, fecha_publicacion,
                       fecha_obsoleto, texto_length
                FROM procedimientos
                WHERE nombre LIKE ?
                ORDER BY fecha_elaboracion
            """, (f"%{nombre}%",)).fetchall()
        elif proceso:
            rows = self.conn.execute("""
                SELECT codigo, nombre, estado, estado_desc, proceso_nom,
                       tipo_documento, fecha_elaboracion, fecha_publicacion,
                       fecha_obsoleto, texto_length
                FROM procedimientos
                WHERE proceso_nom LIKE ?
                ORDER BY nombre, fecha_elaboracion
            """, (f"%{proceso}%",)).fetchall()
        else:
            # Buscar todos los grupos con multiples versiones
            rows = self.conn.execute("""
                SELECT codigo, nombre, estado, estado_desc, proceso_nom,
                       tipo_documento, fecha_elaboracion, fecha_publicacion,
                       fecha_obsoleto, texto_length
                FROM procedimientos
                WHERE nombre IN (
                    SELECT nombre FROM procedimientos
                    GROUP BY nombre HAVING COUNT(*) > 1
                )
                ORDER BY nombre, fecha_elaboracion
            """).fetchall()

        # Agrupar por nombre
        grupos = {}
        for row in rows:
            nombre_doc = row[1]
            if nombre_doc not in grupos:
                grupos[nombre_doc] = []
            grupos[nombre_doc].append({
                "codigo": row[0],
                "nombre": row[1],
                "estado": row[2],
                "estado_desc": row[3],
                "proceso_nom": row[4],
                "tipo_documento": row[5],
                "fecha_elaboracion": row[6],
                "fecha_publicacion": row[7],
                "fecha_obsoleto": row[8],
                "texto_length": row[9],
            })

        # Solo retornar grupos con mas de 1 version
        resultado = []
        for nombre_doc, versiones in grupos.items():
            if len(versiones) > 1:
                resultado.append({
                    "nombre": nombre_doc,
                    "num_versiones": len(versiones),
                    "versiones": versiones,
                })

        return resultado

    def comparar_documentos(self, codigo1: str, codigo2: str) -> dict:
        """Compara dos documentos y retorna las diferencias.
        Usa difflib para generar un diff linea por linea.
        """
        import difflib

        doc1 = self.get_documento(codigo1)
        doc2 = self.get_documento(codigo2)

        if not doc1:
            return {"error": f"No se encontro el documento {codigo1}"}
        if not doc2:
            return {"error": f"No se encontro el documento {codigo2}"}

        texto1 = doc1.get("texto", "")
        texto2 = doc2.get("texto", "")

        lineas1 = texto1.splitlines()
        lineas2 = texto2.splitlines()

        # Diff unificado
        diff = list(difflib.unified_diff(
            lineas1, lineas2,
            fromfile=f"{codigo1} ({doc1.get('estado_desc', '')})",
            tofile=f"{codigo2} ({doc2.get('estado_desc', '')})",
            lineterm="",
        ))

        # Estadisticas
        agregadas = sum(1 for l in diff if l.startswith("+") and not l.startswith("+++"))
        eliminadas = sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))
        modificadas = min(agregadas, eliminadas)

        # Similaridad
        ratio = difflib.SequenceMatcher(None, texto1, texto2).ratio()

        # Diff lado a lado (para HTML)
        side_by_side = []
        matcher = difflib.SequenceMatcher(None, lineas1, lineas2)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                for i in range(i1, i2):
                    side_by_side.append({"tipo": "igual", "linea": lineas1[i]})
            elif tag == "replace":
                for i in range(i1, i2):
                    side_by_side.append({"tipo": "eliminada", "linea": lineas1[i]})
                for j in range(j1, j2):
                    side_by_side.append({"tipo": "agregada", "linea": lineas2[j]})
            elif tag == "delete":
                for i in range(i1, i2):
                    side_by_side.append({"tipo": "eliminada", "linea": lineas1[i]})
            elif tag == "insert":
                for j in range(j1, j2):
                    side_by_side.append({"tipo": "agregada", "linea": lineas2[j]})

        return {
            "doc1": {
                "codigo": codigo1,
                "nombre": doc1.get("nombre", ""),
                "estado": doc1.get("estado_desc", ""),
                "fecha_publicacion": doc1.get("fecha_publicacion", ""),
                "texto_length": len(texto1),
            },
            "doc2": {
                "codigo": codigo2,
                "nombre": doc2.get("nombre", ""),
                "estado": doc2.get("estado_desc", ""),
                "fecha_publicacion": doc2.get("fecha_publicacion", ""),
                "texto_length": len(texto2),
            },
            "similitud": ratio,
            "lineas_agregadas": agregadas,
            "lineas_eliminadas": eliminadas,
            "lineas_modificadas": modificadas,
            "diff_unificado": "\n".join(diff),
            "diff_lado_a_lado": side_by_side,
        }

    # ──────────────────────────────────────────────
    # Dashboard de metricas en tiempo real
    # ──────────────────────────────────────────────

    def dashboard_metricas(self) -> dict:
        """Obtiene metricas detalladas para el dashboard interactivo."""
        # Traces por dia
        traces_por_dia = self.conn.execute("""
            SELECT DATE(timestamp) as fecha,
                   COUNT(*) as traces,
                   SUM(total_tokens) as tokens,
                   SUM(costo_usd) as costo,
                   AVG(latencia_total) as latencia_avg,
                   AVG(latencia_recuperacion) as latencia_rec,
                   AVG(latencia_llm) as latencia_llm
            FROM finops_traces
            GROUP BY DATE(timestamp)
            ORDER BY fecha
        """).fetchall()

        # Llamadas por modelo
        por_modelo = self.conn.execute("""
            SELECT modelo,
                   COUNT(*) as llamadas,
                   SUM(prompt_tokens) as prompt_tokens,
                   SUM(completion_tokens) as completion_tokens,
                   SUM(total_tokens) as total_tokens,
                   SUM(costo_usd) as costo,
                   AVG(latencia) as latencia_avg
            FROM finops_llm_calls
            GROUP BY modelo
            ORDER BY llamadas DESC
        """).fetchall()

        # Traces recientes (ultimas 20)
        traces_recientes = self.conn.execute("""
            SELECT timestamp, pregunta, modelo, total_tokens,
                   costo_usd, latencia_total, documentos_recuperados,
                   skills_activados, obsoletos_filtrados
            FROM finops_traces
            ORDER BY id DESC
            LIMIT 20
        """).fetchall()

        # Distribucion de latencia
        latencia_dist = self.conn.execute("""
            SELECT
                CASE
                    WHEN latencia_total < 5 THEN '0-5s'
                    WHEN latencia_total < 15 THEN '5-15s'
                    WHEN latencia_total < 30 THEN '15-30s'
                    WHEN latencia_total < 60 THEN '30-60s'
                    WHEN latencia_total < 120 THEN '60-120s'
                    ELSE '120s+'
                END as rango,
                COUNT(*) as count
            FROM finops_traces
            GROUP BY rango
            ORDER BY MIN(latencia_total)
        """).fetchall()

        # Tokens por dia (prompt vs completion)
        tokens_por_dia = self.conn.execute("""
            SELECT DATE(timestamp) as fecha,
                   SUM(prompt_tokens) as prompt,
                   SUM(completion_tokens) as completion
            FROM finops_traces
            GROUP BY DATE(timestamp)
            ORDER BY fecha
        """).fetchall()

        # Feedback stats
        fb_stats = self.obtener_feedback_stats()

        return {
            "traces_por_dia": [
                {"fecha": r[0], "traces": r[1], "tokens": r[2],
                 "costo": r[3] or 0, "latencia_avg": r[4] or 0,
                 "latencia_rec": r[5] or 0, "latencia_llm": r[6] or 0}
                for r in traces_por_dia
            ],
            "por_modelo": [
                {"modelo": r[0], "llamadas": r[1], "prompt_tokens": r[2],
                 "completion_tokens": r[3], "total_tokens": r[4],
                 "costo": r[5] or 0, "latencia_avg": r[6] or 0}
                for r in por_modelo
            ],
            "traces_recientes": [
                {"timestamp": r[0], "pregunta": r[1][:80], "modelo": r[2],
                 "tokens": r[3], "costo": r[4] or 0, "latencia": r[5] or 0,
                 "documentos": r[6], "skills": r[7], "obsoletos": r[8]}
                for r in traces_recientes
            ],
            "latencia_dist": [
                {"rango": r[0], "count": r[1]} for r in latencia_dist
            ],
            "tokens_por_dia": [
                {"fecha": r[0], "prompt": r[1], "completion": r[2]}
                for r in tokens_por_dia
            ],
            "feedback": fb_stats,
        }

    def grafo_stats(self) -> dict:
        """Estadísticas del grafo."""
        tipos = defaultdict(int)
        for n in self.graph.nodes:
            tipos[self.graph.nodes[n].get("type", "?")] += 1

        return {
            "nodos": self.graph.number_of_nodes(),
            "aristas": self.graph.number_of_edges(),
            "por_tipo": dict(tipos),
            "documentos": len(self.codigos),
            "embeddings": len(self.embedding_codigos),
        }

    def explorar_nodo(self, nodo_id: str) -> dict:
        """Explora un nodo del grafo y sus vecinos."""
        if nodo_id not in self.graph:
            return {"error": f"Nodo '{nodo_id}' no existe"}

        node_data = self.graph.nodes[nodo_id]
        vecinos = []
        for neighbor in self.graph.neighbors(nodo_id):
            n_data = self.graph.nodes[neighbor]
            edge = self.graph.get_edge_data(nodo_id, neighbor) or {}
            vecinos.append({
                "nodo": neighbor,
                "tipo": n_data.get("type", ""),
                "nombre": n_data.get("nombre", ""),
                "relacion": edge.get("relation", ""),
            })

        return {
            "nodo": nodo_id,
            "tipo": node_data.get("type", ""),
            "nombre": node_data.get("nombre", ""),
            "vecinos": vecinos,
        }

    def listar_temas(self):
        """Lista los temas del grafo."""
        temas = [n for n in self.graph.nodes if self.graph.nodes[n].get("type") == "tema"]
        print(f"\n  Temas en el grafo ({len(temas)}):")
        for t in sorted(temas):
            data = self.graph.nodes[t]
            docs_count = sum(
                1 for nb in self.graph.neighbors(t)
                if self.graph.nodes[nb].get("type") == "documento"
            )
            palabras = data.get("palabras_clave", [])
            print(f"    {t}: {data.get('nombre', '?')} ({docs_count} docs)")
            if palabras:
                print(f"       Palabras: {', '.join(palabras[:5])}")

    # ──────────────────────────────────────────────
    # Resúmenes ejecutivos
    # ──────────────────────────────────────────────

    def get_resumen(self, codigo: str) -> dict | None:
        """Obtiene el resumen ejecutivo de un documento."""
        row = self.conn.execute("""
            SELECT resumen, palabras_clave, proposito, alcance
            FROM resumenes WHERE codigo = ?
        """, (codigo,)).fetchone()
        if not row:
            return None
        return {
            "resumen": row[0],
            "palabras_clave": row[1],
            "proposito": row[2],
            "alcance": row[3],
        }

    def get_documento(self, codigo: str) -> dict | None:
        """Obtiene el documento completo con todos sus metadatos para el visor."""
        row = self.conn.execute("""
            SELECT codigo, nombre, proceso_nom, tipo_documento, estado_desc,
                   fecha_publicacion, vigencia_dias, contenido_texto
            FROM procedimientos WHERE codigo = ?
        """, (codigo,)).fetchone()
        if not row:
            return None

        doc = {
            "codigo": row[0],
            "nombre": row[1],
            "proceso": row[2],
            "tipo_documento": row[3],
            "estado": row[4],
            "fecha_publicacion": row[5],
            "vigencia_dias": row[6],
            "texto": row[7] or "",
        }

        # Resumen si existe
        resumen = self.get_resumen(codigo)
        if resumen:
            doc["resumen"] = resumen.get("resumen", "")
            doc["proposito"] = resumen.get("proposito", "")
            doc["alcance"] = resumen.get("alcance", "")
            doc["palabras_clave"] = resumen.get("palabras_clave", "")

        # Contexto del grafo
        grafo = self._get_graph_context(codigo)
        if grafo:
            doc["grafo_procesos"] = grafo.get("procesos", [])
            doc["grafo_temas"] = grafo.get("temas", [])
            doc["grafo_usuarios"] = grafo.get("usuarios", [])
            doc["docs_relacionados"] = grafo.get("docs_relacionados", [])

        # Alerta de vencimiento si aplica
        try:
            alerta = self.conn.execute("""
                SELECT dias_restantes, estado_alerta, fecha_vencimiento
                FROM alertas_vencimiento WHERE codigo = ?
            """, (codigo,)).fetchone()
            if alerta:
                doc["dias_restantes"] = alerta[0]
                doc["estado_alerta"] = alerta[1]
                doc["fecha_vencimiento"] = alerta[2]
        except Exception:
            pass

        return doc

    def buscar_documentos(self, query: str = "", top_k: int = 20) -> list[dict]:
        """Busca documentos por codigo o nombre. Para el visor de documentos."""
        if query:
            rows = self.conn.execute("""
                SELECT codigo, nombre, proceso_nom, tipo_documento, estado_desc
                FROM procedimientos
                WHERE codigo LIKE ? OR nombre LIKE ? OR proceso_nom LIKE ?
                ORDER BY codigo
                LIMIT ?
            """, (f"%{query}%", f"%{query}%", f"%{query}%", top_k)).fetchall()
        else:
            rows = self.conn.execute("""
                SELECT codigo, nombre, proceso_nom, tipo_documento, estado_desc
                FROM procedimientos
                ORDER BY codigo
                LIMIT ?
            """, (top_k,)).fetchall()

        return [
            {
                "codigo": r[0],
                "nombre": r[1],
                "proceso": r[2],
                "tipo_documento": r[3],
                "estado": r[4],
            }
            for r in rows
        ]

    def buscar_resumenes(self, query: str, top_k: int = 5) -> list[dict]:
        """Busca resúmenes por palabras clave."""
        rows = self.conn.execute("""
            SELECT r.codigo, r.resumen, r.palabras_clave, r.proposito, r.alcance,
                   p.nombre, p.proceso_nom, p.estado_desc
            FROM resumenes r
            JOIN procedimientos p ON r.codigo = p.codigo
            WHERE r.resumen LIKE ? OR r.palabras_clave LIKE ? OR p.nombre LIKE ?
            LIMIT ?
        """, (f"%{query}%", f"%{query}%", f"%{query}%", top_k * 2)).fetchall()

        resultados = []
        query_lower = query.lower()
        for r in rows:
            score = 0
            if query_lower in (r[1] or "").lower():
                score += 3
            if query_lower in (r[2] or "").lower():
                score += 2
            if query_lower in (r[5] or "").lower():
                score += 1
            resultados.append({
                "codigo": r[0],
                "resumen": r[1],
                "palabras_clave": r[2],
                "proposito": r[3],
                "alcance": r[4],
                "nombre": r[5],
                "proceso": r[6],
                "estado": r[7],
                "score": score,
            })
        resultados.sort(key=lambda x: -x["score"])
        return resultados[:top_k]

    # ──────────────────────────────────────────────
    # Tabla jerárquica
    # ──────────────────────────────────────────────

    def tabla_jerarquica(self, proceso: str = None) -> dict:
        """Devuelve la tabla de contenido jerárquica."""
        jerarquia_path = Path(__file__).parent.parent / "tabla_jerarquica.json"
        if not jerarquia_path.exists():
            return {"error": "Tabla jerárquica no generada. Ejecuta generar_resumenes.py"}

        data = json.loads(jerarquia_path.read_text(encoding="utf-8"))
        if proceso:
            # Filtrar por proceso
            proc_lower = proceso.lower()
            filtrado = {}
            for key, val in data.items():
                if proc_lower in (val.get("nombre") or "").lower() or proc_lower in key.lower():
                    filtrado[key] = val
            return filtrado
        return data

    # ──────────────────────────────────────────────
    # Alertas de vencimiento
    # ──────────────────────────────────────────────

    def alertas_vencimiento(self, solo_vencidos: bool = False) -> list[dict]:
        """Devuelve documentos vencidos o por vencer."""
        if solo_vencidos:
            rows = self.conn.execute("""
                SELECT codigo, nombre, proceso, fecha_publicacion, vigencia_dias,
                       fecha_vencimiento, dias_restantes, estado_alerta
                FROM alertas_vencimiento
                WHERE estado_alerta IN ('VENCIDO', 'POR_VENCER_30')
                ORDER BY dias_restantes
            """).fetchall()
        else:
            rows = self.conn.execute("""
                SELECT codigo, nombre, proceso, fecha_publicacion, vigencia_dias,
                       fecha_vencimiento, dias_restantes, estado_alerta
                FROM alertas_vencimiento
                ORDER BY dias_restantes
            """).fetchall()

        return [
            {
                "codigo": r[0], "nombre": r[1], "proceso": r[2],
                "fecha_publicacion": r[3], "vigencia_dias": r[4],
                "fecha_vencimiento": r[5], "dias_restantes": r[6],
                "estado_alerta": r[7],
            }
            for r in rows
        ]

    # ──────────────────────────────────────────────
    # Glosario
    # ──────────────────────────────────────────────

    def buscar_glosario(self, query: str) -> list[dict]:
        """Busca términos del glosario relevantes a la consulta."""
        return buscar_termino(query)

    # ──────────────────────────────────────────────
    # Mejoras extras: Red teaming, HITL, Change log
    # ──────────────────────────────────────────────

    def ejecutar_red_team(self) -> dict:
        """Ejecuta pruebas de red teaming contra el agente.
        Usa los ataques definidos en RED_TEAM_ATTACKS."""
        if not _HAS_MEJORAS_EXTRAS:
            return {"error": "mejoras_extras no disponible"}
        print(f"  [GraphRAG] Ejecutando red teaming ({len(RED_TEAM_ATTACKS)} ataques)...")
        results = run_red_team_test(self.ask, RED_TEAM_ATTACKS)
        save_red_team_results(self.conn, results)
        print(f"  [GraphRAG] Red teaming: {results['passed']}/{results['total']} bloqueados "
              f"(rate={results['blocked_rate']:.1%})")
        if results["vulnerabilities"]:
            print(f"  [GraphRAG] VULNERABILIDADES: {len(results['vulnerabilities'])}")
            for v in results["vulnerabilities"]:
                print(f"    - [{v['category']}] {v['attack']}: {v['description']}")
        return results

    def get_red_team_summary(self) -> dict:
        """Resumen de resultados de red teaming historicos."""
        if not _HAS_MEJORAS_EXTRAS:
            return {"error": "mejoras_extras no disponible"}
        return get_red_team_summary(self.conn)

    def submit_user_feedback(self, session_id: str, user_id: str,
                              question: str, answer: str, rating: int,
                              feedback_type: str = "", comment: str = "",
                              corrected_answer: str = "") -> int:
        """Registra feedback del usuario sobre una respuesta (Human-in-the-loop).

        Args:
            rating: 1=negativo, 2=neutral, 3=positivo
            feedback_type: 'correcta', 'incorrecta', 'incompleta', 'irrelevante', 'alucinacion'
            corrected_answer: respuesta corregida por el usuario (para fine-tuning)
        """
        if not _HAS_MEJORAS_EXTRAS:
            return -1
        return submit_feedback(self.conn, session_id, user_id, question, answer,
                                rating, feedback_type, comment, corrected_answer)

    def get_feedback_stats(self, days: int = 30) -> dict:
        """Estadisticas de feedback de usuarios."""
        if not _HAS_MEJORAS_EXTRAS:
            return {"error": "mejoras_extras no disponible"}
        return get_feedback_stats(self.conn, days)

    def get_training_dataset(self) -> list[dict]:
        """Obtiene dataset de entrenamiento generado por feedback de usuarios."""
        if not _HAS_MEJORAS_EXTRAS:
            return []
        return get_training_dataset(self.conn, status="approved")

    def export_training_dataset(self, output_path: Path) -> dict:
        """Exporta dataset de entrenamiento en formato JSONL para fine-tuning."""
        if not _HAS_MEJORAS_EXTRAS:
            return {"error": "mejoras_extras no disponible"}
        return export_training_dataset(self.conn, output_path)

    def review_feedback(self, feedback_id: int, expert_id: str,
                         approved: bool, notes: str = ""):
        """Revision experta de un feedback (para aprobar/rechazar correcciones)."""
        if not _HAS_MEJORAS_EXTRAS:
            return
        review_feedback(self.conn, feedback_id, expert_id, approved, notes)

    def get_bias_stats(self, days: int = 30) -> dict:
        """Estadisticas de bias detection."""
        if not _HAS_MEJORAS_EXTRAS:
            return {"error": "mejoras_extras no disponible"}
        return get_bias_stats(self.conn, days)

    def get_historial_cambios(self, codigo: str, limit: int = 50) -> list[dict]:
        """Obtiene el historial de cambios de un documento."""
        if not _HAS_MEJORAS_EXTRAS:
            return []
        return obtener_historial_cambios(self.conn, codigo, limit)

    def get_versiones_documento(self, codigo: str) -> list[dict]:
        """Obtiene todas las versiones de un documento."""
        if not _HAS_MEJORAS_EXTRAS:
            return []
        return obtener_versiones_documento(self.conn, codigo)

    def get_diffs_documento(self, codigo: str) -> list[dict]:
        """Obtiene los diffs entre versiones de un documento."""
        if not _HAS_MEJORAS_EXTRAS:
            return []
        return obtener_diffs_documento(self.conn, codigo)

    def get_change_log_stats(self, days: int = 30) -> dict:
        """Estadisticas del change log."""
        if not _HAS_MEJORAS_EXTRAS:
            return {"error": "mejoras_extras no disponible"}
        return get_change_log_stats(self.conn, days)

    def sincronizar_cambios_integra(self, integra_conn=None) -> dict:
        """Sincroniza cambios desde PROCEDIMIENTOSCAMBIO de Integr@."""
        if not _HAS_MEJORAS_EXTRAS:
            return {"error": "mejoras_extras no disponible"}
        return sincronizar_cambios_desde_integra(self.conn, integra_conn)


# ──────────────────────────────────────────────
# CLI interactivo
# ──────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  AGENTE DE CALIDAD - INTEGRA")
    print("  Consultor: calidad, SOPs, NC, CAPA, auditorías")
    print("  Graph RAG: grafo + TF-IDF + embeddings")
    print("  LLM: OpenAI → Mistral → Ollama → Groq → Gemini (fallback)")
    print("=" * 60)

    rag = GraphRAG()

    print("\n  Comandos:")
    print("    /stats         - Estadísticas del grafo")
    print("    /temas         - Lista temas detectados")
    print("    /nodo <id>     - Explora un nodo del grafo")
    print("    /retrieve <q>  - Solo recuperación (sin LLM)")
    print("    /jerarquia     - Tabla jerárquica de procesos")
    print("    /jerarquia <p> - Tabla filtrada por proceso")
    print("    /vencidos      - Documentos vencidos/por vencer")
    print("    /resumen <cod> - Resumen ejecutivo de un documento")
    print("    /glosario <q>  - Buscar términos del glosario")
    print("    /finops        - Dashboard de costos y tokens")
    print("    salir          - Termina\n")

    while True:
        try:
            user = input("Tú: ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not user:
            continue
        if user.lower() in ("salir", "exit", "quit"):
            break

        if user == "/stats":
            stats = rag.grafo_stats()
            print(f"\n  Grafo: {stats['nodos']} nodos, {stats['aristas']} aristas")
            print(f"  Documentos: {stats['documentos']}, Embeddings: {stats['embeddings']}")
            print(f"  Por tipo: {stats['por_tipo']}\n")
            continue

        if user == "/temas":
            rag.listar_temas()
            continue

        if user.startswith("/nodo "):
            nodo = user.split(" ", 1)[1]
            info = rag.explorar_nodo(nodo)
            print(json.dumps(info, ensure_ascii=False, indent=2))
            continue

        if user.startswith("/retrieve "):
            query = user.split(" ", 1)[1]
            resultados = rag.retrieve(query, top_k=5)
            print(f"\n  Resultados:")
            for i, r in enumerate(resultados):
                print(f"    {i+1}. {r['codigo']} (total={r['score_total']:.3f}) - {r['nombre'][:60]}")
                print(f"       sem={r['score_semantico']:.2f} lex={r['score_lexical']:.2f} grafo={r['score_grafo']:.2f}")
            continue

        if user == "/jerarquia":
            jerarquia = rag.tabla_jerarquica()
            if "error" in jerarquia:
                print(f"\n  {jerarquia['error']}")
            else:
                print(f"\n  Tabla jerárquica ({len(jerarquia)} procesos):")
                for key, val in sorted(jerarquia.items(), key=lambda x: -x[1]["total_docs"]):
                    print(f"    📁 {val['nombre']} ({val['total_docs']} docs)")
                    for tipo, tipo_data in sorted(val["tipos"].items(), key=lambda x: -x[1]["total"]):
                        print(f"       📄 {tipo} ({tipo_data['total']})")
            continue

        if user.startswith("/jerarquia "):
            proc = user.split(" ", 1)[1]
            jerarquia = rag.tabla_jerarquica(proceso=proc)
            if not jerarquia:
                print(f"\n  No se encontró el proceso '{proc}'")
            else:
                for key, val in jerarquia.items():
                    print(f"\n  📁 {val['nombre']} ({val['total_docs']} docs)")
                    for tipo, tipo_data in val["tipos"].items():
                        print(f"     📄 {tipo} ({tipo_data['total']})")
                        for doc in tipo_data["documentos"][:10]:
                            print(f"        {doc['codigo']} | {doc['estado_desc']} | {doc['nombre'][:50]}")
            continue

        if user == "/vencidos":
            alertas = rag.alertas_vencimiento(solo_vencidos=True)
            if not alertas:
                print("\n  No hay documentos vencidos ni por vencer. ✅")
            else:
                print(f"\n  Documentos vencidos/por vencer ({len(alertas)}):")
                for a in alertas[:20]:
                    icono = "🔴" if a["estado_alerta"] == "VENCIDO" else "🟡"
                    dias = a["dias_restantes"]
                    dias_str = f"vencido hace {abs(dias)} días" if dias < 0 else f"vence en {dias} días"
                    print(f"    {icono} {a['codigo']} | {dias_str} | {a['nombre'][:40]}")
            continue

        if user.startswith("/resumen "):
            codigo = user.split(" ", 1)[1].strip()
            resumen = rag.get_resumen(codigo)
            if not resumen:
                print(f"\n  No hay resumen para '{codigo}'. Ejecuta generar_resumenes.py primero.")
            else:
                print(f"\n  📋 Resumen ejecutivo: {codigo}")
                print(f"     Resumen: {resumen['resumen']}")
                print(f"     Propósito: {resumen['proposito']}")
                print(f"     Alcance: {resumen['alcance']}")
                print(f"     Palabras clave: {resumen['palabras_clave']}")
            continue

        if user.startswith("/glosario "):
            query = user.split(" ", 1)[1]
            terminos = rag.buscar_glosario(query)
            if not terminos:
                print(f"\n  No se encontraron términos del glosario para '{query}'")
            else:
                print(f"\n  📖 Glosario ({len(terminos)} términos):")
                for t in terminos:
                    print(f"    {t['termino']}")
                    print(f"      Categoría: {t['categoria']}")
                    print(f"      Definición: {t['definicion']}")
            continue

        if user == "/finops":
            rag.obs.print_dashboard()
            continue

        # Pregunta normal → Graph RAG
        try:
            answer, resultados = rag.ask(user)
            print(f"\nAgente: {answer}\n")
        except Exception as e:
            print(f"\n  Error: {type(e).__name__}: {e}\n")


if __name__ == "__main__":
    main()
